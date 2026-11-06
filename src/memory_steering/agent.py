"""Agent runner: one agent, one ticket, one tool loop.

The runner sends the system prompt, the opening message and the agent's tools,
runs each tool call through AgentTools and returns the result, and stops when
the agent has produced its required output (a note, or a decision for the
Approver). It knows nothing about the experiment: prompts come from step 5 and
the order of agents from the episode runner (step 6). The model platform is
behind backends.py.

One tool call at a time: if a response holds several tool calls, only the
first is run; the others get an error result saying so. That way a note is
never written in the same response as the query whose result it would depend
on (the platform has no setting to turn parallel calls off).

Limits (from config):
- max_tool_turns: model calls per agent per ticket.
- max_output_retries: extra model calls allowed after a response that calls
  no tool (e.g. cut off at the output limit, refusal). The model is asked to
  continue with a tool.
A turn that ends without the required output is returned with a failure reason;
the caller logs it and carries on.
"""

import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from memory_steering.backends import Conversation, ToolResult, open_conversation
from memory_steering.config import CONFIG
from memory_steering.tools import AgentTools, ToolCall

NO_TOOL_NUDGE = "Please continue by calling one of your tools."
ONE_AT_A_TIME = "Not run: call one tool at a time, and wait for its result before the next call."


class ModelCall(BaseModel):
    """One request to the model and its response, as logged."""

    agent: str
    ticket_number: int
    call_index: int
    model: str
    stop_reason: str | None
    content: Any  # the model's message as returned
    input_tokens: int
    output_tokens: int
    seconds: float


class AgentResult(BaseModel):
    agent: str
    ticket_number: int
    done: bool
    failure: str | None  # why the agent ended without its required output
    model_calls: list[ModelCall]
    tool_calls: list[ToolCall]
    input_tokens: int
    output_tokens: int


@dataclass
class AgentRun:
    """Inputs for one agent on one ticket."""

    system: str
    opening: str  # first user message: the ticket and, where shown, team memory
    tools: AgentTools
    model: str = CONFIG.model
    max_tool_turns: int = CONFIG.max_tool_turns
    max_output_retries: int = CONFIG.max_output_retries
    conversation: Conversation | None = field(default=None, repr=False)  # set by run_agent; full transcript


async def run_agent(client: Any, run: AgentRun) -> AgentResult:
    tools = run.tools
    convo = open_conversation(client, run.model, run.system, run.opening, tools.specs())
    run.conversation = convo
    model_calls: list[ModelCall] = []
    retries_left = run.max_output_retries
    failure: str | None = None

    while not tools.done:
        if len(model_calls) >= run.max_tool_turns:
            failure = f"reached {run.max_tool_turns} model calls without finishing"
            break
        start = time.monotonic()
        reply = await convo.send()
        model_calls.append(
            ModelCall(
                agent=tools.agent,
                ticket_number=tools.ticket_number,
                call_index=len(model_calls),
                model=reply.model,
                stop_reason=reply.stop_reason,
                content=reply.content,
                input_tokens=reply.input_tokens,
                output_tokens=reply.output_tokens,
                seconds=round(time.monotonic() - start, 3),
            )
        )

        if not reply.tool_uses:
            if retries_left == 0:
                failure = f"no tool call (stop_reason={reply.stop_reason}) and no retries left"
                break
            retries_left -= 1
            convo.add_text(NO_TOOL_NUDGE)
            continue

        first, *rest = reply.tool_uses
        output, is_error = tools.call(first.name, first.input)
        results = [ToolResult(first.id, output, is_error)]
        results += [ToolResult(use.id, ONE_AT_A_TIME, True) for use in rest]
        convo.add_tool_results(results)

    return AgentResult(
        agent=tools.agent,
        ticket_number=tools.ticket_number,
        done=tools.done,
        failure=None if tools.done else failure,
        model_calls=model_calls,
        tool_calls=tools.calls,
        input_tokens=sum(c.input_tokens for c in model_calls),
        output_tokens=sum(c.output_tokens for c in model_calls),
    )
