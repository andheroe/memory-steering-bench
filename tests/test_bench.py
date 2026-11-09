"""The one-command benchmark: run, score, report and scorecard, on the fake team."""

from memory_steering.bench import compare_table, run_benchmark, scores
from tests.test_scoring import FakeTeam


def test_benchmark_end_to_end(tmp_path):
    run_dir = run_benchmark("b", "fake-model", client=FakeTeam(), runs_dir=tmp_path, concurrency=50)
    for f in ("results.json", "tickets.csv", "report.html", "scorecard.md", "run.json"):
        assert (run_dir / f).exists(), f
    s = scores(run_dir)
    # The fake team: attacks always land without verification, never with it.
    assert s["Steering rate, no safeguard"] == "100% (50/50)"
    assert s["Steering rate, verification"] == "0% (0/50)"
    assert s["Verification effect vs no safeguard"].startswith("-100 pts")
    assert s["Relay rate (Security wrote the lie)"] == "100% (150/150)"
    # The fake Approver always grants read, so full-time controls come out wrong.
    assert s["Honest accuracy (all no-attack decisions)"].endswith("/960)")
    assert s["Episodes / unfinished turns / crashed"] == "780 / 0 / 0"
    table = compare_table([run_dir, run_dir])
    assert table.splitlines()[0] == "| Score | b | b |"
