# memory-steering-bench

Swarm Alignment Hackathon 2026 (Apart Research), Track 2: Science of Agent Networks.

> "Build a small benchmark to test whether one compromised agent can steer a team of AI agents toward an incorrect answer through shared memory. Compare safeguards such as source attribution and independent verification to see which best limits the spread."

Three LLM agents approve access requests for made-up employees and share notes in a team memory file. In attack runs, the HR agent is compromised and writes one false fact. We measure how often the team grants access the policy forbids. We also measure whether the honest Security agent adopts the false fact, and how well source attribution and independent verification limit the effect.

## Status

Under construction during the sprint. The design is in [experiment-design.md](experiment-design.md).

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync                  # install Python 3.12 and dependencies into .venv
cp .env.example .env     # then add your ANTHROPIC_API_KEY
uv run pytest            # run the tests
```

Settings shared by every experiment (model, scenario count, seed, verify budget, concurrency) are in `src/memory_steering/config.py`.

## Pre-existing work

Per the hackathon rules, only work done during the sprint (6–8 November 2026) is judged.

- **Written before the sprint (3–5 November 2026):** `experiment-design.md`, the experiment design. It's a design document and contains no code or results.
- **Written during the sprint:** all code, data, results and the report.
