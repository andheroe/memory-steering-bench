"""Model access through the Adaption Labs platform (hosted open-weight models).

The agent runner only sees a Conversation: send() returns a Reply with the
tool calls the model made, and add_tool_results() / add_text() extend the
conversation. AdaptionConversation keeps the history in the Responses API
format: the system prompt goes in `instructions`, the rest is replayed as
`input` items on every call (nothing is stored server-side).

Request settings:
- tool_choice is left at the default ("auto"). The platform has no setting
  that requires some tool call, so a model can answer in plain text; the
  runner then asks it to continue with a tool (bounded retries).
- The platform has no setting to turn off parallel tool calls either; the
  runner runs only the first tool call of a response (see agent.py).
- No temperature or other sampling setting is sent: each model uses its
  default.
"""

import json
from dataclasses import dataclass
from typing import Any, Protocol

# Generous so reasoning models (hidden reasoning counts as output) aren't cut
# off before the tool call. Normal turns use far less.
MAX_OUTPUT_TOKENS = 4096


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
    content: Any  # the model's output items as returned, for the log
    model: str
    input_tokens: int
    output_tokens: int


class Conversation(Protocol):
    messages: list[dict]

    async def send(self) -> Reply: ...
    def add_tool_results(self, results: list[ToolResult]) -> None: ...
    def add_text(self, text: str) -> None: ...


def _parse_arguments(arguments: str | None) -> dict:
    """Tool arguments arrive as a JSON string. Invalid JSON becomes an empty
    input, which the tool rejects with an error the model sees."""
    try:
        parsed = json.loads(arguments or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _dump(item: Any) -> dict:
    return item.model_dump(exclude_none=True) if hasattr(item, "model_dump") else dict(item)


class AdaptionConversation:
    def __init__(self, client: Any, model: str, system: str, opening: str, tools: list[dict]):
        self.client, self.model, self.system = client, model, system
        self.tools = [
            {"type": "function", "name": t["name"], "description": t["description"], "parameters": t["input_schema"]}
            for t in tools
        ]
        self.messages: list[dict] = [{"role": "user", "content": opening}]

    async def send(self) -> Reply:
        response = await self.client.responses.create(
            model=self.model,
            instructions=self.system,
            input=list(self.messages),  # snapshot: later appends must not change this request
            tools=self.tools,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            store=False,
        )
        items = [_dump(i) for i in response.output]
        self.messages.extend(items)
        stop = response.status
        if getattr(response, "incomplete_details", None) is not None:
            stop += f":{_dump(response.incomplete_details).get('reason', '')}"
        usage = response.usage
        return Reply(
            tool_uses=[
                ToolUse(i["call_id"], i["name"], _parse_arguments(i.get("arguments")))
                for i in items
                if i.get("type") == "function_call"
            ],
            stop_reason=stop,
            content=items,
            model=getattr(response, "model", self.model),
            input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
        )

    def add_tool_results(self, results: list[ToolResult]) -> None:
        for r in results:
            self.messages.append(
                {
                    "type": "function_call_output",
                    "call_id": r.tool_use_id,
                    "output": f"Error: {r.output}" if r.is_error else r.output,
                }
            )

    def add_text(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})


def open_conversation(client: Any, model: str, system: str, opening: str, tools: list[dict]) -> Conversation:
    return AdaptionConversation(client, model, system, opening, tools)


def make_client() -> Any:
    """The real async client. Imported lazily so tests need no API key."""
    from adaption import AsyncAdaption

    from memory_steering.config import api_key

    return AsyncAdaption(api_key=api_key(), max_retries=5)  # SDK retries rate limits and 5xx
