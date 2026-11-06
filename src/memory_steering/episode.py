"""One episode: one scenario in one condition, two tickets, five agent turns.

Fixed order:
- ticket 1: HR agent (the attacker in attack runs), Security agent, Approver;
- ticket 2: Security agent, Approver (no HR: "persistence without HR refresh").

Everything is written to the episode's folder:
- memory.json: the shared memory file, as the agents built it;
- episode.json: the condition, the scenario, and for every agent turn the
  system prompt, opening message, full transcript, tool calls, model calls and
  tokens, plus each ticket's final decision next to the correct answers.
A turn that ends without its required output is logged with its failure reason
and the episode carries on; a ticket without a decision has final_level None.
"""

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from memory_steering.agent import AgentResult, AgentRun, run_agent
from memory_steering.config import CONFIG
from memory_steering.databases import Databases
from memory_steering.memory import Memory
from memory_steering.prompts import SecurityPrompt, opening_message, prompt_hash, system_prompt
from memory_steering.tools import AgentRole, AgentTools

Safeguard = Literal["none", "attribution", "verification"]
SAFEGUARDS: tuple[Safeguard, ...] = ("none", "attribution", "verification")
SECURITY_PROMPTS: tuple[SecurityPrompt, ...] = ("neutral", "memory_first")


class Condition(BaseModel):
    attack: bool
    safeguard: Safeguard
    security_prompt: SecurityPrompt

    @property
    def condition_id(self) -> str:
        return f"{'attack' if self.attack else 'no_attack'}-{self.safeguard}-{self.security_prompt}"


def all_conditions() -> list[Condition]:
    return [
        Condition(attack=a, safeguard=s, security_prompt=p)
        for p in SECURITY_PROMPTS
        for a in (False, True)
        for s in SAFEGUARDS
    ]


class AgentTurn(BaseModel):
    agent: AgentRole
    is_attacker: bool
    ticket_number: int
    system_prompt: str
    system_prompt_hash: str
    opening_message: str
    transcript: list[dict]  # messages after the system prompt, in the provider's format
    result: AgentResult


class TicketOutcome(BaseModel):
    ticket_number: int
    system: str
    requested: str
    d_true: str
    d_false: str
    final_level: str | None  # None if the Approver ended without a decision
    approver_reason: str | None


class Episode(BaseModel):
    episode_id: str
    scenario_id: str
    scenario_kind: str
    condition: Condition
    condition_id: str
    model: str
    scenario: dict
    turns: list[AgentTurn]
    tickets: list[TicketOutcome]
    input_tokens: int
    output_tokens: int


def episode_id(scenario: dict, condition: Condition) -> str:
    return f"{scenario['scenario_id']}__{condition.condition_id}"


TICKET_AGENTS: dict[int, tuple[AgentRole, ...]] = {
    1: ("hr", "security", "approver"),
    2: ("security", "approver"),
}


async def run_episode(
    client: Any,
    scenario: dict,
    condition: Condition,
    databases: Databases,
    out_dir: Path,
    model: str = CONFIG.model,
) -> Episode:
    if condition.attack and scenario["attack"] is None:
        raise ValueError(f"{scenario['scenario_id']} has no attack block; it runs only without attack.")
    out_dir.mkdir(parents=True, exist_ok=True)
    ep_id = episode_id(scenario, condition)
    memory = Memory(out_dir / "memory.json", ep_id)
    employee_id = scenario["employee"]["employee_id"]
    attribution = condition.safeguard == "attribution"

    turns: list[AgentTurn] = []
    outcomes: list[TicketOutcome] = []
    for ticket in scenario["tickets"]:
        n = ticket["ticket_number"]
        decision = None
        for agent in TICKET_AGENTS[n]:
            is_attacker = agent == "hr" and condition.attack
            system = system_prompt(
                agent,
                attack=scenario["attack"] if is_attacker else None,
                security_prompt=condition.security_prompt,
            )
            tools = AgentTools(
                agent=agent,
                ticket_number=n,
                employee_id=employee_id,
                system=ticket["system"],
                databases=databases,
                memory=memory,
                verify_enabled=agent == "approver" and condition.safeguard == "verification",
                verify_budget=CONFIG.verify_budget_per_ticket,
            )
            # Rendered just before the agent's turn, so it holds every earlier note.
            opening = opening_message(scenario, ticket, memory, attribution=attribution)
            run = AgentRun(system=system, opening=opening, tools=tools, model=model)
            result = await run_agent(client, run)
            turns.append(
                AgentTurn(
                    agent=agent,
                    is_attacker=is_attacker,
                    ticket_number=n,
                    system_prompt=system,
                    system_prompt_hash=prompt_hash(system),
                    opening_message=opening,
                    transcript=run.conversation.messages if run.conversation else [],
                    result=result,
                )
            )
            if agent == "approver":
                decision = tools.decision
        outcomes.append(
            TicketOutcome(
                ticket_number=n,
                system=ticket["system"],
                requested=ticket["requested"],
                d_true=ticket["d_true"],
                d_false=ticket["d_false"],
                final_level=decision.level if decision else None,
                approver_reason=decision.reason if decision else None,
            )
        )

    episode = Episode(
        episode_id=ep_id,
        scenario_id=scenario["scenario_id"],
        scenario_kind=scenario["kind"],
        condition=condition,
        condition_id=condition.condition_id,
        model=model,
        scenario=scenario,
        turns=turns,
        tickets=outcomes,
        input_tokens=sum(t.result.input_tokens for t in turns),
        output_tokens=sum(t.result.output_tokens for t in turns),
    )
    # Written last, and atomically: an episode.json on disk means the episode finished.
    tmp = out_dir / "episode.json.tmp"
    tmp.write_text(json.dumps(episode.model_dump(mode="json"), indent=2) + "\n")
    tmp.replace(out_dir / "episode.json")
    return episode
