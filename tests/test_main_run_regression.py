"""Regression test: the default setup must reproduce the main run exactly.

Extensions (team size, split query tools, new lies, new attacker tactics) are
added as opt-in settings. With the defaults, every agent must still see exactly
what it saw in runs/main: the same system prompts, scenarios, opening messages
(ticket + rendered team memory, with and without attribution labels), tools and
experiment settings. If one of these tests fails, a change has reached the
original design; agree it with the team before running anything.
"""

import hashlib
import json
from pathlib import Path

import pytest

from memory_steering.config import CONFIG, PROJECT_ROOT
from memory_steering.databases import Databases
from memory_steering.memory import Memory
from memory_steering.prompts import all_system_prompts, opening_message, prompt_hash, system_prompt
from memory_steering.scenarios import generate
from memory_steering.scoring import compute_metrics, load_episodes, ticket_table
from memory_steering.tools import AgentTools

MAIN = PROJECT_ROOT / "runs" / "main"

pytestmark = pytest.mark.skipif(not (MAIN / "run.json").exists(), reason="runs/main is not present")

# Fingerprints of the tool definitions each agent was given in the main run.
# Tool definitions weren't logged per episode, so they are pinned here
# (computed from commit 960d19b, the commit the main run used).
TOOL_SPEC_HASHES = {
    "hr": "94910f4743de",
    "security": "bb64aaf6bcbf",
    "approver": "996e9993dab7",
    "approver+verify": "c1cd86ca495d",
}


def _run_meta() -> dict:
    return json.loads((MAIN / "run.json").read_text())


def _episodes() -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted((MAIN / "episodes").glob("*/episode.json"))]


def _tool_specs(agent: str, verify: bool = False) -> list[dict]:
    tools = AgentTools(
        agent=agent,
        ticket_number=1,
        employee_id="E001",
        system="Payroll",
        databases=Databases([]),
        memory=None,  # not used by specs()
        verify_enabled=verify,
    )
    return tools.specs()


def _spec_hash(specs: list[dict]) -> str:
    return hashlib.sha256(json.dumps(specs, sort_keys=True).encode()).hexdigest()[:12]


def test_settings_match_main_run():
    meta = _run_meta()
    assert CONFIG.model == meta["model"]
    assert CONFIG.seed == meta["seed"]
    assert CONFIG.verify_budget_per_ticket == meta["verify_budget_per_ticket"]
    assert CONFIG.max_tool_turns == meta["max_tool_turns"]
    assert CONFIG.max_output_retries == meta["max_output_retries"]


def test_system_prompts_match_main_run():
    current = {name: prompt_hash(text) for name, text in all_system_prompts().items()}
    assert current == _run_meta()["prompt_hashes"]


def test_scenarios_match_main_run():
    on_disk = json.loads((CONFIG.data_dir / "scenarios.json").read_text())
    assert json.loads(json.dumps(generate())) == on_disk


def test_tool_definitions_match_main_run():
    current = {
        "hr": _spec_hash(_tool_specs("hr")),
        "security": _spec_hash(_tool_specs("security")),
        "approver": _spec_hash(_tool_specs("approver")),
        "approver+verify": _spec_hash(_tool_specs("approver", verify=True)),
    }
    assert current == TOOL_SPEC_HASHES


def test_scoring_reproduces_main_run_results():
    """Re-scoring the main run with the current code gives the committed
    results.json (all metrics; health is checked separately by its own fields)."""
    committed = json.loads((MAIN / "results.json").read_text())
    tickets = ticket_table(load_episodes(MAIN))
    current = json.loads(json.dumps(compute_metrics(tickets), default=str))
    committed.pop("health")
    assert current == committed


def test_every_logged_turn_is_reproduced(tmp_path: Path):
    """For every turn of every main-run episode, rebuild the team memory as it
    stood before that turn and check that the current code gives the agent the
    same system prompt and the same opening message, word for word."""
    scenarios = {s["scenario_id"]: s for s in json.loads((CONFIG.data_dir / "scenarios.json").read_text())["scenarios"]}
    episodes = _episodes()
    assert len(episodes) == 780

    for ep in episodes:
        cond = ep["condition"]
        scenario = ep["scenario"]
        assert scenario == scenarios[ep["scenario_id"]]
        notes = json.loads((MAIN / "episodes" / ep["episode_id"] / "memory.json").read_text())
        written = 0  # notes in memory before the current turn
        for turn in ep["turns"]:
            expected_prompt = system_prompt(
                turn["agent"],
                attack=scenario["attack"] if turn["is_attacker"] else None,
                security_prompt=cond["security_prompt"],
            )
            assert turn["system_prompt"] == expected_prompt, ep["episode_id"]

            path = tmp_path / "memory.json"
            path.write_text(json.dumps(notes[:written]))
            memory = Memory(path, ep["episode_id"])
            ticket = next(t for t in scenario["tickets"] if t["ticket_number"] == turn["ticket_number"])
            rendered = opening_message(scenario, ticket, memory, attribution=cond["safeguard"] == "attribution")
            assert turn["opening_message"] == rendered, (ep["episode_id"], turn["agent"], turn["ticket_number"])

            if turn["agent"] != "approver" and turn["result"]["done"]:
                written += 1
        assert written == len(notes), ep["episode_id"]
