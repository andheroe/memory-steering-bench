"""One live agent turn against the real API, to check the setup before step 5.

Runs an honest Security agent on scenario S001, ticket 1, with empty memory and
the real (neutral) Security prompt. Confirms the model ID is
accepted, the tool loop round-trips, and prints token use (and cost, where the
price is listed below).

    uv run python scripts/smoke_check.py                  # model from config
    uv run python scripts/smoke_check.py glm-5.2          # any hosted model ID

Needs ADAPTION_API_KEY in .env.
One agent turn: a few thousand tokens at most.
"""

import asyncio
import json
import sys
import tempfile
from pathlib import Path

from memory_steering.agent import AgentRun, run_agent
from memory_steering.backends import make_client
from memory_steering.config import CONFIG
from memory_steering.databases import Databases
from memory_steering.memory import Memory
from memory_steering.prompts import opening_message, system_prompt
from memory_steering.tools import AgentTools

from memory_steering.scoring import PRICE_PER_MTOK


async def main(model: str) -> None:
    scenarios = json.loads((CONFIG.data_dir / "scenarios.json").read_text())["scenarios"]
    s = scenarios[0]
    ticket = s["tickets"][0]
    with tempfile.TemporaryDirectory() as tmp:
        tools = AgentTools(
            agent="security",
            ticket_number=1,
            employee_id=s["employee"]["employee_id"],
            system=ticket["system"],
            databases=Databases(scenarios),
            memory=Memory(Path(tmp) / "memory.json", "smoke"),
        )
        run = AgentRun(
            system=system_prompt("security"),
            opening=opening_message(s, ticket, tools.memory, attribution=False),
            tools=tools,
            model=model,
        )
        result = await run_agent(make_client(), run)

    print(f"model requested: {model}; served: {result.model_calls[0].model}")
    for c in result.model_calls:
        print(f"  call {c.call_index}: stop={c.stop_reason} in={c.input_tokens} out={c.output_tokens} {c.seconds}s")
    for t in result.tool_calls:
        print(f"  tool {t.name}{' (error)' if t.is_error else ''}: {json.dumps(t.input)} -> {t.output}")
    print(f"done={result.done} failure={result.failure}")
    print(f"tokens: in={result.input_tokens} out={result.output_tokens}")
    price = next((p for m, p in PRICE_PER_MTOK.items() if model.startswith(m)), None)
    if price:
        p_in, p_out = price
        print(f"cost: {(result.input_tokens * p_in + result.output_tokens * p_out) / 1e6:.5f} credits")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else CONFIG.model))
