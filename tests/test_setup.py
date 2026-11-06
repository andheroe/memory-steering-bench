"""Smoke test: the package imports and the config holds the frozen design values."""

from memory_steering.config import CONFIG


def test_config_matches_design():
    assert CONFIG.model == "deepseek-v4-flash"
    assert CONFIG.n_scenarios == 50
    assert CONFIG.n_control_scenarios == 30
    assert CONFIG.verify_budget_per_ticket == 1


def test_dependencies_import():
    import adaption  # noqa: F401
    import faker  # noqa: F401
    import pandas  # noqa: F401
    import pydantic  # noqa: F401
