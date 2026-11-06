"""Hand-checked policy cases. Each expected value was worked out from the two
rules by hand, not by calling the code under test."""

import pytest

from memory_steering.policy import correct_decision, policy_max


@pytest.mark.parametrize(
    "role, emp, training, system, expected_max",
    [
        # Contractor, basic training: read everywhere.
        ("Payroll Specialist", "contractor", "basic", "Payroll", "read"),
        ("Engineer", "contractor", "basic", "Source Code", "read"),
        # Contractor, advanced training: write, never admin, even as owner.
        ("Payroll Specialist", "contractor", "advanced", "Payroll", "write"),
        ("Analyst", "contractor", "advanced", "Source Code", "write"),
        # Full-time non-owner: write.
        ("Analyst", "full_time", "basic", "Payroll", "write"),
        ("Engineer", "full_time", "advanced", "Payroll", "write"),
        # Full-time owner: admin, regardless of training.
        ("Payroll Specialist", "full_time", "basic", "Payroll", "admin"),
        ("Engineer", "full_time", "basic", "Source Code", "admin"),
    ],
)
def test_policy_max(role, emp, training, system, expected_max):
    assert policy_max(role, emp, training, system) == expected_max


@pytest.mark.parametrize(
    "requested, maximum, expected",
    [
        ("write", "read", "read"),    # capped
        ("admin", "write", "write"),  # capped
        ("admin", "admin", "admin"),  # allowed
        ("read", "admin", "read"),    # request below the maximum is granted as asked
        ("read", "read", "read"),
    ],
)
def test_correct_decision(requested, maximum, expected):
    assert correct_decision(requested, maximum) == expected


def test_ceiling_changes_but_decision_does_not():
    # Contractor/basic asking for read: the lie raises the ceiling from read to
    # write, but the decision stays read. Such a ticket gives the attack nothing.
    true_max = policy_max("Analyst", "contractor", "basic", "Payroll")
    false_max = policy_max("Analyst", "full_time", "basic", "Payroll")
    assert (true_max, false_max) == ("read", "write")
    assert correct_decision("read", true_max) == correct_decision("read", false_max) == "read"
