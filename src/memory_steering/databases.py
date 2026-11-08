"""Department databases: read-only views of the true employee records.

Each department sees only its own fields. Employment type is stored in both,
as the same fact with the same values, so the Security agent can check the
attacker's claim against its own records.
"""

from typing import Literal

Department = Literal["hr", "security", "it", "finance", "compliance", "facilities"]
Field = Literal["role", "employment_type", "training"]

FIELDS: tuple[Field, ...] = ("role", "employment_type", "training")
DEPARTMENT_FIELDS: dict[Department, tuple[Field, ...]] = {
    "hr": ("role", "employment_type"),
    "security": ("employment_type", "training"),
}

# Extension E1 ("complete_split" setup): HR also holds security training, so
# HR's note can carry every field the policy needs. The main run never uses this.
COMPLETE_DEPARTMENT_FIELDS: dict[Department, tuple[Field, ...]] = {
    "hr": ("role", "employment_type", "training"),
    "security": ("employment_type", "training"),
}

# Extension E4 ("relays4" setup): four honest relay departments. Each holds
# role only, never employment type (the lied-about field), so a relay can pass
# the lie on but can't check it. The main run never uses these.
RELAY_DEPARTMENT_FIELDS: dict[Department, tuple[Field, ...]] = {
    "it": ("role",),
    "finance": ("role",),
    "compliance": ("role",),
    "facilities": ("role",),
}
ALL_DEPARTMENT_FIELDS: dict[Department, tuple[Field, ...]] = {**DEPARTMENT_FIELDS, **RELAY_DEPARTMENT_FIELDS}


class Databases:
    """True records for every employee in the scenario set. Never written to."""

    def __init__(self, scenarios: list[dict]):
        self._employees = {s["employee"]["employee_id"]: s["employee"] for s in scenarios}

    def record(
        self, department: Department, employee_id: str, fields: tuple[Field, ...] | None = None
    ) -> dict[Field, str] | None:
        """The department's record for one employee, or None if unknown.

        fields: which fields to return; defaults to the department's fields.
        """
        employee = self._employees.get(employee_id)
        if employee is None:
            return None
        return {f: employee[f] for f in (fields or ALL_DEPARTMENT_FIELDS[department])}

    def true_value(self, employee_id: str, field: Field) -> str | None:
        """Authoritative value used by the verify() safeguard."""
        employee = self._employees.get(employee_id)
        return None if employee is None else employee[field]
