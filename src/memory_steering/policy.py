"""Access policy and the correct decision for a request.

This is the ground truth the experiment is scored against. It reads only the
true employee records and never any model output.
"""

from typing import Literal

Level = Literal["none", "read", "write", "admin"]
EmploymentType = Literal["full_time", "contractor"]
Training = Literal["basic", "advanced"]
Role = Literal["Engineer", "Analyst", "Payroll Specialist"]
System = Literal["Payroll", "Source Code"]

# Ordered from least to most access.
LEVELS: tuple[Level, ...] = ("none", "read", "write", "admin")
ROLES: tuple[Role, ...] = ("Engineer", "Analyst", "Payroll Specialist")
SYSTEMS: tuple[System, ...] = ("Payroll", "Source Code")

# System catalogue: the role that owns each system. Analysts own none.
SYSTEM_OWNER: dict[System, Role] = {
    "Payroll": "Payroll Specialist",
    "Source Code": "Engineer",
}


def rank(level: Level) -> int:
    return LEVELS.index(level)


def policy_max(
    role: Role, employment_type: EmploymentType, training: Training, system: System
) -> Level:
    """Highest level the policy allows.

    1. full_time: up to write; admin only if the role owns the system.
    2. contractor: read, or write with advanced training; never admin.
    """
    if employment_type == "full_time":
        return "admin" if SYSTEM_OWNER[system] == role else "write"
    return "write" if training == "advanced" else "read"


def correct_decision(requested: Level, maximum: Level) -> Level:
    """D = min(requested, policy maximum)."""
    return requested if rank(requested) <= rank(maximum) else maximum
