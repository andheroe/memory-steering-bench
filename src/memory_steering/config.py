"""Experiment settings in one place.

Values that change what the experiment measures (model, scenario count, seed,
verify budget) live here so they can be frozen with the code after the pilot.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Config:
    # Model used for every agent (HR, attacker, Security, Approver).
    # The provider follows from the name: "claude-..." is Anthropic, else OpenAI.
    model: str = "claude-haiku-5-5"

    # Scenario generation.
    # Attack-eligible scenarios run in all 12 conditions; honest controls only
    # in the 6 no-attack conditions, to measure accuracy on varied answers.
    n_scenarios: int = 50
    n_control_scenarios: int = 30
    seed: int = 20261106

    # Safeguard: at most this many verify() calls per ticket.
    verify_budget_per_ticket: int = 1

    # Agent runner limits.
    max_tool_turns: int = 8
    max_output_retries: int = 2

    # Parallel episodes in flight.
    concurrency: int = 8

    # Where generated data and run logs go.
    data_dir: Path = PROJECT_ROOT / "data"
    runs_dir: Path = PROJECT_ROOT / "runs"


CONFIG = Config()


KEY_VARIABLES = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}


def api_key(provider: str) -> str:
    """Return the provider's API key from the environment or .env, or fail clearly."""
    variable = KEY_VARIABLES[provider]
    key = os.environ.get(variable)
    if not key:
        raise RuntimeError(f"{variable} is not set. Copy .env.example to .env and add your key.")
    return key
