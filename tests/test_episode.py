"""Episode and experiment runners, with a fake client that plays every agent.

The fake answers like a simple agent: query its database if it has one and
hasn't yet, then write a note with what the query returned (or, as the
attacker, with full_time), or submit "read" as the Approver. It records every
request, so tests can check who ran, in what order, with which prompt and tools.
"""

import asyncio
import json
from types import SimpleNamespace

from memory_steering.databases import Databases
from memory_steering.episode import Condition, all_conditions, run_episode
from memory_steering.experiment import load_scenarios, planned_episodes, run_experiment

SCENARIOS = load_scenarios()
S001 = SCENARIOS[0]  # eligible, contractor with basic training
CONTROL = next(s for s in SCENARIOS if s["kind"] == "control")


class FakeAgents:
    def __init__(self):
        self.requests = []
        self.messages = self

    async def create(self, **kw):
        self.requests.append(kw)
        names = [t["name"] for t in kw["tools"]]
        msgs = kw["messages"]
        queried = len(msgs) > 1
        if "submit_decision" in names:
            call = ("submit_decision", {"level": "read", "reason": "policy"})
        elif not queried:
            call = (names[0], {"employee_id": kw["messages"][0]["content"].split("employee ID ")[1][:4]})
        else:
            employment = "full_time" if "Hidden instruction" in kw["system"] else "contractor"
            call = (
                "write_note",
                {
                    "facts": {"employment_type": employment},
                    "recommendation": "read",
                    "text": "note",
                    "employment_type_used": employment,
                },
            )
        block = {"type": "tool_use", "id": f"t{len(self.requests)}", "name": call[0], "input": call[1]}
        return SimpleNamespace(
            content=[block], stop_reason="tool_use", model="fake", usage=SimpleNamespace(input_tokens=10, output_tokens=2)
        )


MODEL = "claude-fake"


def run(scenario, condition, tmp_path, client=None):
    client = client or FakeAgents()
    ep = asyncio.run(run_episode(client, scenario, condition, Databases(SCENARIOS), tmp_path, model=MODEL))
    return ep, client


def test_twelve_conditions_with_readable_ids():
    ids = [c.condition_id for c in all_conditions()]
    assert len(set(ids)) == 12
    assert "attack-verification-memory_first" in ids


def test_full_design_plans_780_episodes():
    pairs = planned_episodes(SCENARIOS)
    assert len(pairs) == 780
    assert not any(c.attack for s, c in pairs if s["kind"] == "control")


def test_episode_order_and_files(tmp_path):
    ep, _ = run(S001, Condition(attack=False, safeguard="none", security_prompt="neutral"), tmp_path)
    assert [(t.ticket_number, t.agent) for t in ep.turns] == [
        (1, "hr"),
        (1, "security"),
        (1, "approver"),
        (2, "security"),
        (2, "approver"),
    ]
    assert [t.final_level for t in ep.tickets] == ["read", "read"]
    assert json.loads((tmp_path / "episode.json").read_text())["episode_id"] == "S001__no_attack-none-neutral"
    assert len(json.loads((tmp_path / "memory.json").read_text())) == 3  # HR, Security t1, Security t2


def test_attack_reaches_only_the_hr_turn_and_its_note(tmp_path):
    ep, _ = run(S001, Condition(attack=True, safeguard="none", security_prompt="neutral"), tmp_path)
    hidden = [t.agent for t in ep.turns if "Hidden instruction" in t.system_prompt]
    assert hidden == ["hr"] and ep.turns[0].is_attacker
    # The lie is in memory, and Security saw it in its opening message.
    assert "employment type: full_time" in ep.turns[1].opening_message


def test_later_agents_see_earlier_notes(tmp_path):
    ep, _ = run(S001, Condition(attack=False, safeguard="none", security_prompt="neutral"), tmp_path)
    assert "no notes" in ep.turns[0].opening_message
    assert "Note 1" in ep.turns[1].opening_message
    assert "Note 2" in ep.turns[2].opening_message
    # Ticket 2: facts from ticket 1, no ticket-1 recommendations.
    assert "Note 1" in ep.turns[3].opening_message and "recommendation" not in ep.turns[3].opening_message


def test_safeguards_change_rendering_and_tools_not_prompts(tmp_path):
    base = Condition(attack=True, safeguard="none", security_prompt="neutral")
    eps = {
        s: run(S001, base.model_copy(update={"safeguard": s}), tmp_path / s)
        for s in ("none", "attribution", "verification")
    }
    prompts = {s: [t.system_prompt for t in ep.turns] for s, (ep, _) in eps.items()}
    assert prompts["none"] == prompts["attribution"] == prompts["verification"]
    assert "written by" in eps["attribution"][0].turns[2].opening_message
    assert "written by" not in eps["none"][0].turns[2].opening_message
    approver_tools = lambda client: [  # noqa: E731
        [t["name"] for t in r["tools"]] for r in client.requests if any(t["name"] == "submit_decision" for t in r["tools"])
    ]
    assert all("verify" in names for names in approver_tools(eps["verification"][1]))
    assert not any("verify" in names for names in approver_tools(eps["none"][1]))


def test_memory_first_prompt_only_for_security(tmp_path):
    ep, _ = run(S001, Condition(attack=False, safeguard="none", security_prompt="memory_first"), tmp_path)
    with_sentence = [t.agent for t in ep.turns if "Reuse team notes" in t.system_prompt]
    assert with_sentence == ["security", "security"]


def test_experiment_runs_resumes_and_redoes_interrupted(tmp_path):
    pairs = planned_episodes(SCENARIOS, {"S001", CONTROL["scenario_id"]}, {"no_attack-none-neutral", "attack-none-neutral"})
    assert len(pairs) == 3  # control gets no attack condition
    counts = asyncio.run(run_experiment("r1", MODEL, pairs, client=FakeAgents(), runs_dir=tmp_path))
    assert counts["finished"] == 3 and counts["crashed"] == 0
    episodes = tmp_path / "r1" / "episodes"
    # Simulate an interrupted episode: folder without episode.json.
    interrupted = episodes / "S001__attack-none-neutral"
    (interrupted / "episode.json").unlink()
    counts = asyncio.run(run_experiment("r1", MODEL, pairs, client=FakeAgents(), runs_dir=tmp_path))
    assert counts["skipped_done"] == 2 and counts["finished"] == 1
    assert len(json.loads((interrupted / "memory.json").read_text())) == 3  # rebuilt, not appended to
    meta = json.loads((tmp_path / "r1" / "run.json").read_text())
    assert len(meta["attempts"]) == 2 and meta["model"] == MODEL


def test_crashed_episode_is_logged_and_retried(tmp_path):
    class Crashing(FakeAgents):
        async def create(self, **kw):
            raise RuntimeError("API down")

    pairs = planned_episodes(SCENARIOS, {"S001"}, {"no_attack-none-neutral"})
    counts = asyncio.run(run_experiment("r2", MODEL, pairs, client=Crashing(), runs_dir=tmp_path))
    assert counts["crashed"] == 1
    assert "API down" in (tmp_path / "r2" / "errors" / "S001__no_attack-none-neutral.txt").read_text()
    counts = asyncio.run(run_experiment("r2", MODEL, pairs, client=FakeAgents(), runs_dir=tmp_path))
    assert counts["finished"] == 1
    assert not (tmp_path / "r2" / "errors" / "S001__no_attack-none-neutral.txt").exists()
