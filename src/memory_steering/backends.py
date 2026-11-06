"""Model providers: Anthropic and OpenAI behind one small interface.

The agent runner only sees a Conversation: send() returns a Reply with the
tool calls the model made, and add_tool_results() / add_text() extend the
conversation. Each backend keeps the message list in its own provider's format
and translates tool specs, tool calls and token counts.

The provider follows from the model name: "claude-..." is Anthropic, anything
else is OpenAI.

Request settings, the same in both backends:
- every model call must call a tool (Anthropic tool_choice "any", OpenAI
  "required"). Which tool, and whether to query a database first, stays free;
- one tool call per model call (parallel tool calls off), so a note is never
  written in the same call as the query whose result it would depend on;
- no temperature or other sampling settings: each model uses its default.
"""

import json
from dataclasses import dataclass
from typing import Any, Literal, Protocol

Provider = Literal["anthropic", "openai"]

# Generous so that reasoning models (whose hidden reasoning counts as output)
# don't get cut off before the tool call. Normal turns use far less.
MAX_OUTPUT_TOKENS = 4096


def provider_of(model: str) -> Provider:
    return "anthropic" if model.startswith("claude-") else "openai"


@dataclass
class ToolUse:
    id: str
    name: str
    input: dict


@dataclass
class ToolResult:
    tool_use_id: str
    output: str
    is_error: bool


@dataclass
class Reply:
    tool_uses: list[ToolUse]
    stop_reason: str | None
    content: Any  # the model's message as returned, for the log
    model: str
    input_tokens: int
    output_tokens: int


class Conversation(Protocol):
    messages: list[dict]

    async def send(self) -> Reply: ...
    def add_tool_results(self, results: list[ToolResult]) -> None: ...
    def add_text(self, text: str) -> None: ...


def _dump(obj: Any) -> Any:
    return obj.model_dump(exclude_none=True) if hasattr(obj, "model_dump") else obj


class AnthropicConversation:
    def __init__(self, client: Any, model: str, system: str, opening: str, tools: list[dict]):
        self.client, self.model, self.system, self.tools = client, model, system, tools
        self.messages: list[dict] = [{"role": "user", "content": opening}]

    async def send(self) -> Reply:
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=self.system,
            tools=self.tools,
            tool_choice={"type": "any", "disable_parallel_tool_use": True},
            messages=list(self.messages),  # snapshot: later appends must not change this request
        )
        content = [_dump(b) for b in response.content]
        self.messages.append({"role": "assistant", "content": content})
        return Reply(
            tool_uses=[
                ToolUse(b["id"], b["name"], b.get("input") or {})
                for b in content
                if b.get("type") == "tool_use"
            ],
            stop_reason=response.stop_reason,
            content=content,
            model=getattr(response, "model", self.model),
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

    def add_tool_results(self, results: list[ToolResult]) -> None:
        self.messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": r.tool_use_id, "content": r.output, "is_error": r.is_error}
                    for r in results
                ],
            }
        )

    def add_text(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})


class OpenAIConversation:
    """Chat Completions API. Tool errors are marked with an "Error: " prefix,
    since OpenAI tool results have no error flag."""

    def __init__(self, client: Any, model: str, system: str, opening: str, tools: list[dict]):
        self.client, self.model = client, model
        self.tools = [
            {
                "type": "function",
                "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]},
            }
            for t in tools
        ]
        self.messages: list[dict] = [
            {"role": "system", "content": system},
            {"role": "user", "content": opening},
        ]

    async def send(self) -> Reply:
        response = await self.client.chat.completions.create(
            model=self.model,
            max_completion_tokens=MAX_OUTPUT_TOKENS,
            tools=self.tools,
            tool_choice="required",
            parallel_tool_calls=False,
            messages=list(self.messages),
        )
        choice = response.choices[0]
        message = choice.message
        calls = message.tool_calls or []
        self.messages.append(
            {
                "role": "assistant",
                "content": message.content,
                **(
                    {
                        "tool_calls": [
                            {
                                "id": c.id,
                                "type": "function",
                                "function": {"name": c.function.name, "arguments": c.function.arguments},
                            }
                            for c in calls
                        ]
                    }
                    if calls
                    else {}
                ),
            }
        )
        return Reply(
            tool_uses=[ToolUse(c.id, c.function.name, _parse_arguments(c.function.arguments)) for c in calls],
            stop_reason=choice.finish_reason,
            content=_dump(message),
            model=getattr(response, "model", self.model),
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
        )

    def add_tool_results(self, results: list[ToolResult]) -> None:
        for r in results:
            self.messages.append(
                {
                    "role": "tool",
                    "tool_call_id": r.tool_use_id,
                    "content": f"Error: {r.output}" if r.is_error else r.output,
                }
            )

    def add_text(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})


def _parse_arguments(arguments: str) -> dict:
    """OpenAI sends tool arguments as a JSON string. Invalid JSON becomes an
    empty input, which the tool rejects with an error the model sees."""
    try:
        parsed = json.loads(arguments or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def open_conversation(client: Any, model: str, system: str, opening: str, tools: list[dict]) -> Conversation:
    cls = AnthropicConversation if provider_of(model) == "anthropic" else OpenAIConversation
    return cls(client, model, system, opening, tools)


def make_client(model: str) -> Any:
    """The real async client for the model's provider. Imported lazily so tests
    need neither SDK configured nor an API key."""
    from memory_steering.config import api_key

    provider = provider_of(model)
    if provider == "anthropic":
        from anthropic import AsyncAnthropic

        return AsyncAnthropic(api_key=api_key(provider), max_retries=5)  # SDK retries rate limits and 5xx
    from openai import AsyncOpenAI

    return AsyncOpenAI(api_key=api_key(provider), max_retries=5)
