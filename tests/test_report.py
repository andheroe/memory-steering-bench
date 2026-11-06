"""The results viewer builds from a run and embeds every episode."""

import asyncio
import json
import re

from memory_steering.experiment import load_scenarios, planned_episodes, run_experiment
from memory_steering.report import build_report
from tests.test_scoring import FakeTeam


def test_report_embeds_results_and_episodes(tmp_path):
    scenarios = load_scenarios()
    pairs = planned_episodes(scenarios, {"S001"}, {"no_attack-none-neutral", "attack-attribution-neutral"})
    asyncio.run(run_experiment("rep", "fake-model", pairs, client=FakeTeam(), runs_dir=tmp_path))
    html = build_report(tmp_path / "rep").read_text()
    assert "/*__DATA__*/" not in html
    data = json.loads(re.search(r"const DATA = (.*?);\n", html).group(1).replace("<\\/", "</"))
    assert set(data["episodes"]) == {"S001__no_attack-none-neutral", "S001__attack-attribution-neutral"}
    attack = data["episodes"]["S001__attack-attribution-neutral"]
    assert [t["agent"] for t in attack["turns"]] == ["hr", "security", "approver", "security", "approver"]
    assert attack["turns"][0]["attacker"] and attack["turns"][0]["prompt"] in data["prompts"]
    assert attack["turns"][0]["steps"][0]["tool"]["name"] == "query_hr_db"
    assert len(attack["memory"]) == 3
