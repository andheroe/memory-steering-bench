"""Agent runner and the Adaption backend, driven by a scripted fake client."""

import asyncio

from memory_steering.agent import NO_TOOL_NUDGE, ONE_AT_A_TIME, AgentRun, run_agent
from memory_steering.databases import Databases
from memory_steering.memory import Memory
from memory_steering.tools import AgentTools
from tests.fakes import FakeAdaption, Scripted

ANITA = {
    "employee_id": "E001",
    "name": "Anita Young",
    "role": "Payroll Specialist",
    "employment_type": "contractor",
    "training": "basic",
}

NOTE = {
    "facts": {"employment_type": "contractor"},
    "recommendation": "read",
    "text": "ok",
    "employment_type_used": "contractor",
}


def tool(name, args):
    return ("tool", name, args)


def make_run(tmp_path, agent="security", **kw):
    tools = AgentTools(
        agent=agent,
        ticket_number=1,
        employee_id="E001",
        system="Payroll",
        databases=Databases([{"employee": ANITA}]),
        memory=Memory(tmp_path / "memory.json", "ep1"),
        **({"verify_enabled": True} if agent == "approver" else {}),
    )
    return AgentRun(system="You are an agent.", opening="Ticket 1.", tools=tools, model="fake-model", **kw)


def run(client, r):
    return asyncio.run(run_agent(client, r))


def last_item(client, i):
    return client.requests[i]["input"][-1]


def test_query_then_note_finishes_and_feeds_results_back(tmp_path):
    client = Scripted(tool("query_security_db", {"employee_id": "E001"}), tool("write_note", NOTE))
    result = run(client, make_run(tmp_path))
    assert result.done and result.failure is None
    assert [c.name for c in result.tool_calls] == ["query_security_db", "write_note"]
    assert (result.input_tokens, result.output_tokens) == (200, 40)
    out = last_item(client, 1)
    assert out["type"] == "function_call_output" and out["call_id"] == "c1" and "contractor" in out["output"]
    # The model's own function_call item is replayed before its output.
    assert client.requests[1]["input"][-2]["type"] == "function_call"


def test_request_settings(tmp_path):
    client = Scripted(tool("write_note", NOTE))
    run(client, make_run(tmp_path))
    req = client.requests[0]
    assert req["instructions"] == "You are an agent."
    assert req["input"] == [{"role": "user", "content": "Ticket 1."}]
    assert req["store"] is False
    assert "temperature" not in req and "tool_choice" not in req
    assert [t["name"] for t in req["tools"]] == ["query_security_db", "write_note"]
    assert req["tools"][1]["type"] == "function"
    assert "employment_type_used" in req["tools"][1]["parameters"]["properties"]


def test_tool_error_is_returned_and_agent_can_correct(tmp_path):
    bad = {**NOTE, "facts": {"employment_type": "permanent"}}
    client = Scripted(tool("write_note", bad), tool("write_note", NOTE))
    result = run(client, make_run(tmp_path))
    assert result.done
    assert last_item(client, 1)["output"].startswith("Error: ")


def test_invalid_json_arguments_become_a_tool_error(tmp_path):
    client = Scripted(tool("write_note", "{not json"))
    result = run(client, make_run(tmp_path, max_tool_turns=1))
    assert result.tool_calls[0].is_error and not result.done


def test_only_the_first_of_several_tool_calls_runs(tmp_path):
    class TwoCalls(FakeAdaption):
        async def create(self, **kw):
            response = await super().create(**kw)
            if len(self.requests) == 1:
                response.output.append(
                    {"type": "function_call", "call_id": "c1b", "name": "write_note", "arguments": "{}"}
                )
            return response

        def decide(self, req):
            if req.n_items == 1:
                return tool("query_security_db", {"employee_id": "E001"})
            return tool("write_note", NOTE)

    client = TwoCalls()
    result = run(client, make_run(tmp_path))
    assert result.done
    assert [c.name for c in result.tool_calls] == ["query_security_db", "write_note"]  # second call never ran
    outputs = [i for i in client.requests[1]["input"] if i.get("type") == "function_call_output"]
    assert outputs[1]["call_id"] == "c1b" and outputs[1]["output"] == f"Error: {ONE_AT_A_TIME}"


def test_response_without_tool_call_gets_a_nudge(tmp_path):
    client = Scripted(("text", "Thinking...", "completed"), tool("write_note", NOTE))
    result = run(client, make_run(tmp_path))
    assert result.done
    assert last_item(client, 1) == {"role": "user", "content": NO_TOOL_NUDGE}


def test_no_retries_left_ends_with_failure(tmp_path):
    client = Scripted(*[("text", "no", "completed")] * 3)
    result = run(client, make_run(tmp_path, max_output_retries=2))
    assert not result.done and "no retries left" in result.failure
    assert len(result.model_calls) == 3


def test_turn_limit_ends_with_failure(tmp_path):
    client = Scripted(*[tool("query_security_db", {"employee_id": "E001"})] * 3)
    result = run(client, make_run(tmp_path, max_tool_turns=3))
    assert not result.done and "3 model calls" in result.failure


def test_approver_verify_then_decide(tmp_path):
    client = Scripted(
        tool("verify", {"employee_id": "E001", "field": "employment_type"}),
        tool("submit_decision", {"level": "read", "reason": "contractor"}),
    )
    r = make_run(tmp_path, agent="approver")
    result = run(client, r)
    assert result.done and r.tools.decision.level == "read" and r.tools.verify_calls == 1
