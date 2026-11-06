"""Agent runner and both backends, driven by scripted fake clients: no API calls.

Each fake returns responses shaped like its provider's SDK objects. Scripts are
written provider-neutrally (a tool call, or plain text) and the fake builds the
provider's response from them, so every runner test runs on both providers.
"""

import asyncio
import json
from types import SimpleNamespace

import pytest

from memory_steering.agent import NO_TOOL_NUDGE, AgentRun, run_agent
from memory_steering.backends import provider_of
from memory_steering.databases import Databases
from memory_steering.memory import Memory
from memory_steering.tools import AgentTools

ANITA = {
    "employee_id": "E001",
    "name": "Anita Young",
    "role": "Payroll Specialist",
    "employment_type": "contractor",
    "training": "basic",
}

MODELS = {"anthropic": "claude-haiku-5-5", "openai": "gpt-test"}


def tool(name, input, id="t1"):
    return ("tool", name, input, id)


def text(t, stop="stop"):
    return ("text", t, stop)


class FakeAnthropic:
    def __init__(self, *script):
        self.script, self.requests = list(script), []
        self.messages = self

    async def create(self, **kw):
        self.requests.append(kw)
        step = self.script.pop(0)
        if step[0] == "tool":
            _, name, input, id = step
            blocks, stop = [{"type": "tool_use", "id": id, "name": name, "input": input}], "tool_use"
        else:
            blocks, stop = [{"type": "text", "text": step[1]}], {"stop": "end_turn"}.get(step[2], step[2])
        return SimpleNamespace(
            content=blocks, stop_reason=stop, model="fake", usage=SimpleNamespace(input_tokens=100, output_tokens=20)
        )

    # Provider-neutral views of the recorded requests, for assertions.
    def last_tool_result(self, i):
        block = self.requests[i]["messages"][-1]["content"][0]
        return block["tool_use_id"], block["content"], block["is_error"]

    def last_text(self, i):
        return self.requests[i]["messages"][-1]["content"]

    def tool_names(self, i):
        return [t["name"] for t in self.requests[i]["tools"]]


class FakeOpenAI:
    def __init__(self, *script):
        self.script, self.requests = list(script), []
        self.chat = SimpleNamespace(completions=self)

    async def create(self, **kw):
        self.requests.append(kw)
        step = self.script.pop(0)
        if step[0] == "tool":
            _, name, input, id = step
            call = SimpleNamespace(
                id=id, type="function", function=SimpleNamespace(name=name, arguments=json.dumps(input))
            )
            message, finish = SimpleNamespace(content=None, tool_calls=[call]), "tool_calls"
        else:
            message, finish = SimpleNamespace(content=step[1], tool_calls=None), {"max_tokens": "length"}.get(
                step[2], step[2]
            )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason=finish)],
            model="fake",
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20),
        )

    def last_tool_result(self, i):
        m = self.requests[i]["messages"][-1]
        is_error = m["content"].startswith("Error: ")
        return m["tool_call_id"], m["content"], is_error

    def last_text(self, i):
        return self.requests[i]["messages"][-1]["content"]

    def tool_names(self, i):
        return [t["function"]["name"] for t in self.requests[i]["tools"]]


FAKES = {"anthropic": FakeAnthropic, "openai": FakeOpenAI}


@pytest.fixture(params=["anthropic", "openai"])
def provider(request):
    return request.param


def make_run(tmp_path, provider, agent="security", **kw):
    tools = AgentTools(
        agent=agent,
        ticket_number=1,
        employee_id="E001",
        system="Payroll",
        databases=Databases([{"employee": ANITA}]),
        memory=Memory(tmp_path / "memory.json", "ep1"),
        **({"verify_enabled": True} if agent == "approver" else {}),
    )
    return AgentRun(system="You are an agent.", opening="Ticket 1.", tools=tools, model=MODELS[provider], **kw)


NOTE = {
    "facts": {"employment_type": "contractor"},
    "recommendation": "read",
    "text": "ok",
    "employment_type_used": "contractor",
}


def run(client, r):
    return asyncio.run(run_agent(client, r))


def test_provider_follows_model_name():
    assert provider_of("claude-haiku-5-5") == "anthropic"
    assert provider_of("gpt-5.4-mini") == "openai"


def test_query_then_note_finishes_and_feeds_results_back(tmp_path, provider):
    client = FAKES[provider](
        tool("query_security_db", {"employee_id": "E001"}, "a"),
        tool("write_note", NOTE, "b"),
    )
    result = run(client, make_run(tmp_path, provider))
    assert result.done and result.failure is None
    assert [c.name for c in result.tool_calls] == ["query_security_db", "write_note"]
    assert (result.input_tokens, result.output_tokens) == (200, 40)
    # The second request carries the query result back under the right id.
    tool_use_id, content, is_error = client.last_tool_result(1)
    assert tool_use_id == "a" and "contractor" in content and not is_error


def test_anthropic_request_settings(tmp_path):
    client = FakeAnthropic(tool("write_note", NOTE))
    run(client, make_run(tmp_path, "anthropic"))
    req = client.requests[0]
    assert req["tool_choice"] == {"type": "any", "disable_parallel_tool_use": True}
    assert req["system"] == "You are an agent."
    assert "temperature" not in req
    assert client.tool_names(0) == ["query_security_db", "write_note"]


def test_openai_request_settings(tmp_path):
    client = FakeOpenAI(tool("write_note", NOTE))
    run(client, make_run(tmp_path, "openai"))
    req = client.requests[0]
    assert req["tool_choice"] == "required" and req["parallel_tool_calls"] is False
    assert req["messages"][0] == {"role": "system", "content": "You are an agent."}
    assert "temperature" not in req
    assert client.tool_names(0) == ["query_security_db", "write_note"]
    # Same JSON schema as the Anthropic spec, under OpenAI's "parameters" key.
    assert "employment_type_used" in req["tools"][1]["function"]["parameters"]["properties"]


def test_tool_error_is_returned_and_agent_can_correct(tmp_path, provider):
    bad = {**NOTE, "facts": {"employment_type": "permanent"}}
    client = FAKES[provider](tool("write_note", bad, "a"), tool("write_note", NOTE, "b"))
    result = run(client, make_run(tmp_path, provider))
    assert result.done
    assert client.last_tool_result(1)[2]  # the first attempt came back as an error


def test_openai_invalid_json_arguments_become_a_tool_error(tmp_path):
    client = FakeOpenAI(tool("write_note", NOTE, "a"))
    real_create = client.create

    async def broken_then_real(**kw):
        response = await real_create(**kw)
        response.choices[0].message.tool_calls[0].function.arguments = "{not json"
        return response

    client.create = broken_then_real
    client.script.append(tool("write_note", NOTE, "b"))
    result = run(client, make_run(tmp_path, "openai", max_tool_turns=1))
    assert result.tool_calls[0].is_error and not result.done


def test_response_without_tool_call_gets_a_nudge(tmp_path, provider):
    client = FAKES[provider](text("Thinking...", "max_tokens"), tool("write_note", NOTE))
    result = run(client, make_run(tmp_path, provider))
    assert result.done
    assert client.last_text(1) == NO_TOOL_NUDGE


def test_no_retries_left_ends_with_failure(tmp_path, provider):
    client = FAKES[provider](*[text("no")] * 3)
    result = run(client, make_run(tmp_path, provider, max_output_retries=2))
    assert not result.done and "no retries left" in result.failure
    assert len(result.model_calls) == 3


def test_turn_limit_ends_with_failure(tmp_path, provider):
    client = FAKES[provider](*[tool("query_security_db", {"employee_id": "E001"})] * 3)
    result = run(client, make_run(tmp_path, provider, max_tool_turns=3))
    assert not result.done and "3 model calls" in result.failure
    assert len(result.model_calls) == 3


def test_approver_verify_then_decide(tmp_path, provider):
    client = FAKES[provider](
        tool("verify", {"employee_id": "E001", "field": "employment_type"}, "a"),
        tool("submit_decision", {"level": "read", "reason": "contractor"}, "b"),
    )
    r = make_run(tmp_path, provider, agent="approver")
    result = run(client, r)
    assert result.done and r.tools.decision.level == "read" and r.tools.verify_calls == 1
