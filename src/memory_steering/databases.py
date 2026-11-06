"""Department databases: read-only views of the true employee records.

Each department sees only its own fields. Employment type is stored in both,
as the same fact with the same values, so the Security agent can check the
attacker's claim against its own records.
"""

from typing import Literal

Department = Literal["hr", "security"]
Field = Literal["role", "employment_type", "training"]

FIELDS: tuple[Field, ...] = ("role", "employment_type", "training")
DEPARTMENT_FIELDS: dict[Department, tuple[Field, ...]] = {
    "hr": ("role", "employment_type"),
    "security": ("employment_type", "training"),
}


class Databases:
    """True records for every employee in the scenario set. Never written to."""

    def __init__(self, scenarios: list[dict]):
        self._employees = {s["employee"]["employee_id"]: s["employee"] for s in scenarios}

    def record(self, department: Department, employee_id: str) -> dict[Field, str] | None:
        """The department's record for one employee, or None if unknown."""
        employee = self._employees.get(employee_id)
        if employee is None:
            return None
        return {f: employee[f] for f in DEPARTMENT_FIELDS[department]}

    def true_value(self, employee_id: str, field: Field) -> str | None:
        """Authoritative value used by the verify() safeguard."""
        employee = self._employees.get(employee_id)
        return None if employee is None else employee[field]
