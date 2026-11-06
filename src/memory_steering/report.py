"""Results viewer: one self-contained HTML file per run.

    uv run python -m memory_steering.report <run_id>     # writes runs/<run_id>/report.html

Scores the run (scoring.py), then embeds the results, the ticket table and a
compact copy of every episode into report_template.html. The page has four
levels, each a click deeper:
1. overview: headline numbers and one chart (ticket-1 overgrant rate with and
   without the attack, per safeguard), plus run health;
2. condition: what Security and the Approver did under one safeguard;
3. scenarios: a grid of every scenario x condition, coloured by outcome;
4. episode: one run drawn as a timeline of agent turns with prompts, tool
   calls, notes and decisions.
System prompts are stored once and referenced by hash to keep the file small.
"""

import json
import sys
from pathlib import Path

from memory_steering.config import CONFIG
from memory_steering.scoring import load_episodes, score_run

TEMPLATE = Path(__file__).with_name("report_template.html")


def _text_of(content) -> str:
    """Assistant text in a model call's logged content, for either provider."""
    if isinstance(content, list):  # Anthropic blocks
        return "\n".join(b.get("text", "") for b in content if b.get("type") == "text").strip()
    if isinstance(content, dict):  # OpenAI message
        return (content.get("content") or "").strip()
    return ""


def _has_tool_call(content) -> bool:
    if isinstance(content, list):
        return any(b.get("type") == "tool_use" for b in content)
    if isinstance(content, dict):
        return bool(content.get("tool_calls"))
    return False


def compact_episode(episode: dict, memory: list[dict], prompts: dict[str, str]) -> dict:
    turns = []
    for t in episode["turns"]:
        prompts[t["system_prompt_hash"]] = t["system_prompt"]
        r = t["result"]
        tool_calls = iter(r["tool_calls"])
        steps = []
        for mc in r["model_calls"]:
            step = {
                "text": _text_of(mc["content"]),
                "stop": mc["stop_reason"],
                "tokens": [mc["input_tokens"], mc["output_tokens"]],
                "seconds": mc["seconds"],
            }
            # Parallel tool calls are off: each model call has at most one tool call, in order.
            if _has_tool_call(mc["content"]):
                call = next(tool_calls, None)
                if call:
                    step["tool"] = {k: call[k] for k in ("name", "input", "output", "is_error")}
            steps.append(step)
        turns.append(
            {
                "agent": t["agent"],
                "attacker": t["is_attacker"],
                "ticket": t["ticket_number"],
                "prompt": t["system_prompt_hash"],
                "opening": t["opening_message"],
                "done": r["done"],
                "failure": r["failure"],
                "steps": steps,
            }
        )
    return {
        "id": episode["episode_id"],
        "scenario": episode["scenario"],
        "condition": episode["condition"],
        "model": episode["model"],
        "tickets": episode["tickets"],
        "turns": turns,
        "memory": memory,
        "tokens": [episode["input_tokens"], episode["output_tokens"]],
    }


def build_report(run_dir: Path) -> Path:
    tickets, results = score_run(run_dir)
    prompts: dict[str, str] = {}
    episodes = {}
    for e in load_episodes(run_dir):
        mem_path = run_dir / "episodes" / e["episode_id"] / "memory.json"
        memory = json.loads(mem_path.read_text()) if mem_path.exists() else []
        episodes[e["episode_id"]] = compact_episode(e, memory, prompts)
    data = {
        "run_id": run_dir.name,
        "results": results,
        "tickets": json.loads(tickets.to_json(orient="records")),
        "episodes": episodes,
        "prompts": prompts,
    }
    payload = json.dumps(data, separators=(",", ":"), default=str).replace("</", "<\\/")
    html = TEMPLATE.read_text().replace("/*__DATA__*/null", payload)
    out = run_dir / "report.html"
    out.write_text(html)
    return out


def main() -> None:
    out = build_report(CONFIG.runs_dir / sys.argv[1])
    print(f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
