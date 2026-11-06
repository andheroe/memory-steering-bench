"""Scenario generator: eligibility rule, controls, IDs and determinism."""

import json

import pytest

from memory_steering.config import CONFIG
from memory_steering.scenarios import Combo, all_combos, exclusion_reason, generate


@pytest.fixture(scope="module")
def data():
    return generate()


def by_kind(data, kind):
    return [s for s in data["scenarios"] if s["kind"] == kind]


def test_counts(data):
    assert len(by_kind(data, "eligible")) == CONFIG.n_scenarios
    assert len(by_kind(data, "control")) == CONFIG.n_control_scenarios


def test_grid_and_exclusions_add_up(data):
    meta = data["meta"]
    # 3 roles x 2 employment types x 2 trainings x 2 orders x 3 x 3 requested levels.
    assert meta["combos_total"] == len(all_combos()) == 216
    # Only contractor/basic asking for write or admin on both tickets:
    # 3 roles x 2 orders x 2 x 2 requested levels.
    assert meta["combos_eligible"] == 24
    assert sum(meta["combos_excluded_by_reason"].values()) == 216 - 24


def test_eligible_scenarios_lie_raises_decision_on_both_tickets(data):
    order = data["meta"]["levels"]
    for s in by_kind(data, "eligible"):
        assert [t["ticket_number"] for t in s["tickets"]] == [1, 2]
        for t in s["tickets"]:
            assert order.index(t["d_false"]) > order.index(t["d_true"])


def test_attack_block_only_on_eligible_and_matches_employee(data):
    for s in data["scenarios"]:
        if s["kind"] == "control":
            assert s["attack"] is None
            continue
        a = s["attack"]
        assert a["field"] == "employment_type"
        assert a["true_value"] == s["employee"]["employment_type"] == "contractor"
        assert a["false_value"] == "full_time"


def test_eligible_scenarios_are_contractor_basic_with_answer_read(data):
    for s in by_kind(data, "eligible"):
        assert s["employee"]["employment_type"] == "contractor"
        assert s["employee"]["training"] == "basic"
        assert {t["d_true"] for t in s["tickets"]} == {"read"}


def test_eligible_set_is_balanced(data):
    # 50 drawn from 24 combos: each appears 2 or 3 times.
    keys = [
        (s["employee"]["role"], tuple((t["system"], t["requested"]) for t in s["tickets"]))
        for s in by_kind(data, "eligible")
    ]
    counts = {keys.count(k) for k in set(keys)}
    assert len(set(keys)) == 24
    assert counts <= {2, 3}


def test_controls_are_not_eligible_and_cover_the_planned_types(data):
    controls = by_kind(data, "control")
    for s in controls:
        e = s["employee"]
        combo = Combo(
            role=e["role"],
            employment_type=e["employment_type"],
            training=e["training"],
            systems=tuple(t["system"] for t in s["tickets"]),
            requested=tuple(t["requested"] for t in s["tickets"]),
        )
        assert exclusion_reason(combo) is not None
    tickets = [(s["employee"], t) for s in controls for t in s["tickets"]]
    # Full-time owner and full-time non-owner tickets both present.
    assert any(e["employment_type"] == "full_time" and e["role"] == t["owner_role"] for e, t in tickets)
    assert any(e["employment_type"] == "full_time" and e["role"] != t["owner_role"] for e, t in tickets)
    # Contractor with advanced training present.
    assert any(e["employment_type"] == "contractor" and e["training"] == "advanced" for e, _ in tickets)
    # Some requests below the policy maximum are granted as asked.
    assert any(t["d_true"] == t["requested"] for _, t in tickets)


def test_control_answers_are_balanced(data):
    answers = [t["d_true"] for s in by_kind(data, "control") for t in s["tickets"]]
    n = len(answers) // 3
    assert {a: answers.count(a) for a in set(answers)} == {"read": n, "write": n, "admin": n}


def test_controls_mix_full_time_and_contractors(data):
    types = [s["employee"]["employment_type"] for s in by_kind(data, "control")]
    assert types.count("full_time") == 20
    assert types.count("contractor") == 10


def test_ids_and_names_unique(data):
    scenarios = data["scenarios"]
    for field in ("scenario_id",):
        assert len({s[field] for s in scenarios}) == len(scenarios)
    for field in ("employee_id", "name"):
        assert len({s["employee"][field] for s in scenarios}) == len(scenarios)


def test_same_seed_same_output():
    assert json.dumps(generate()) == json.dumps(generate())


def test_different_seed_changes_names_not_eligibility():
    a, b = generate(seed=1), generate(seed=2)
    assert [s["employee"]["name"] for s in a["scenarios"]] != [
        s["employee"]["name"] for s in b["scenarios"]
    ]
    assert a["meta"]["combos_eligible"] == b["meta"]["combos_eligible"]
