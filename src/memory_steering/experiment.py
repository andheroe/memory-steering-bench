"""Experiment runner: every episode of a run, in parallel, resumable.

Episodes in the full run:
- 50 eligible scenarios x 12 conditions = 600;
- 30 honest controls x 6 no-attack conditions = 180.

Layout of a run:
    runs/<run_id>/run.json                      settings, versions, prompt hashes
    runs/<run_id>/episodes/<episode_id>/        memory.json, episode.json
    runs/<run_id>/errors/<episode_id>.txt       traceback of an episode that crashed

Resuming: an episode with an episode.json is finished and skipped. Any other
episode folder is a leftover of an interrupted attempt; it's deleted and the
episode is run again from scratch, so a memory file never mixes two attempts.

Episodes run in a shuffled order (seeded), so an outage or rate limit mid-run
doesn't hit one condition only. At most CONFIG.concurrency run at once.

    uv run python -m memory_steering.experiment --run-id pilot1 --model deepseek-v4-flash \\
        --scenarios S001,S051 --conditions no_attack-none-neutral,attack-none-neutral
"""

import argparse
import asyncio
import json
import random
import shutil
import subprocess
import traceback
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Any

from memory_steering.backends import make_client
from memory_steering.config import CONFIG, PROJECT_ROOT
from memory_steering.databases import Databases
from memory_steering.episode import Condition, all_conditions, episode_id, run_episode
from memory_steering.prompts import all_system_prompts, prompt_hash


def load_scenarios() -> list[dict]:
    return json.loads((CONFIG.data_dir / "scenarios.json").read_text())["scenarios"]


def planned_episodes(
    scenarios: list[dict],
    scenario_ids: set[str] | None = None,
    condition_ids: set[str] | None = None,
) -> list[tuple[dict, Condition]]:
    """Every (scenario, condition) pair the design runs, optionally filtered.
    Controls (no attack block) get only the no-attack conditions."""
    pairs = []
    for s in scenarios:
        if scenario_ids and s["scenario_id"] not in scenario_ids:
            continue
        for c in all_conditions():
            if c.attack and s["attack"] is None:
                continue
            if condition_ids and c.condition_id not in condition_ids:
                continue
            pairs.append((s, c))
    return pairs


def _git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, capture_output=True, text=True)
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=PROJECT_ROOT, capture_output=True, text=True)
        return out.stdout.strip() + ("-dirty" if dirty.stdout.strip() else "")
    except OSError:
        return None


def _write_run_meta(run_dir: Path, model: str, n_planned: int) -> None:
    meta_path = run_dir / "run.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {"attempts": []}
    meta.update(
        {
            "run_id": run_dir.name,
            "model": model,
            "seed": CONFIG.seed,
            "verify_budget_per_ticket": CONFIG.verify_budget_per_ticket,
            "max_tool_turns": CONFIG.max_tool_turns,
            "max_output_retries": CONFIG.max_output_retries,
            "concurrency": CONFIG.concurrency,
            "prompt_hashes": {name: prompt_hash(text) for name, text in all_system_prompts().items()},
            "versions": {p: version(p) for p in ("adaption", "pydantic")},
        }
    )
    meta["attempts"].append(
        {"started": datetime.now(timezone.utc).isoformat(), "git_commit": _git_commit(), "planned": n_planned}
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")


async def run_experiment(
    run_id: str,
    model: str,
    pairs: list[tuple[dict, Condition]],
    client: Any = None,
    runs_dir: Path = CONFIG.runs_dir,
    concurrency: int = CONFIG.concurrency,
) -> dict[str, int]:
    """Run every planned episode not yet finished. Returns counts."""
    run_dir = runs_dir / run_id
    previous = run_dir / "run.json"
    if previous.exists() and json.loads(previous.read_text())["model"] != model:
        raise RuntimeError(f"Run {run_id} used another model; start a new run id.")
    _write_run_meta(run_dir, model, len(pairs))
    client = client or make_client()
    databases = Databases(load_scenarios())

    todo = []
    skipped = 0
    for s, c in pairs:
        ep_dir = run_dir / "episodes" / episode_id(s, c)
        if (ep_dir / "episode.json").exists():
            skipped += 1
            continue
        if ep_dir.exists():
            shutil.rmtree(ep_dir)  # interrupted attempt
        todo.append((s, c, ep_dir))
    random.Random(f"{CONFIG.seed}-{run_id}").shuffle(todo)

    semaphore = asyncio.Semaphore(concurrency)
    counts = {"planned": len(pairs), "skipped_done": skipped, "finished": 0, "crashed": 0}
    errors_dir = run_dir / "errors"

    async def one(s: dict, c: Condition, ep_dir: Path) -> None:
        async with semaphore:
            ep_id = episode_id(s, c)
            try:
                await run_episode(client, s, c, databases, ep_dir, model=model)
                counts["finished"] += 1
                (errors_dir / f"{ep_id}.txt").unlink(missing_ok=True)
                status = "done"
            except Exception:
                counts["crashed"] += 1
                errors_dir.mkdir(parents=True, exist_ok=True)
                (errors_dir / f"{ep_id}.txt").write_text(traceback.format_exc())
                status = "CRASHED"
            done = counts["finished"] + counts["crashed"]
            print(f"[{done}/{len(todo)}] {ep_id}: {status}", flush=True)

    await asyncio.gather(*(one(*t) for t in todo))
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--model", default=CONFIG.model)
    parser.add_argument("--scenarios", help="comma-separated scenario IDs (default: all)")
    parser.add_argument("--conditions", help="comma-separated condition IDs (default: all)")
    parser.add_argument("--concurrency", type=int, default=CONFIG.concurrency)
    parser.add_argument("--dry-run", action="store_true", help="list the planned episodes and stop")
    args = parser.parse_args()

    split = lambda v: set(v.split(",")) if v else None  # noqa: E731
    pairs = planned_episodes(load_scenarios(), split(args.scenarios), split(args.conditions))
    if args.dry_run:
        for s, c in pairs:
            print(episode_id(s, c))
        print(f"{len(pairs)} episodes")
        return
    counts = asyncio.run(run_experiment(args.run_id, args.model, pairs, concurrency=args.concurrency))
    print(counts)


if __name__ == "__main__":
    main()
