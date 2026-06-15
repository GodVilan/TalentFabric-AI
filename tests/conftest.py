"""
Shared pytest configuration for the TalentFabric AI test suite.

The default suite is **network-free and deterministic**: every test that
touches the Microsoft Learn MCP integration uses a mocked transport. Tests
that hit the real ``learn.microsoft.com`` endpoint are marked ``live`` and are
**deselected by default** — run them explicitly in a networked environment
with ``pytest -m live``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure the project root is importable (so ``import src...`` works) when
# pytest is invoked from anywhere.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "live: hits the real Microsoft Learn MCP endpoint; requires network. "
        "Deselected by default — run with `pytest -m live`.",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip ``live`` tests unless the user explicitly selects them with ``-m live``."""
    markexpr = config.getoption("-m", default="")
    if "live" in markexpr:
        return  # user opted in
    skip_live = pytest.mark.skip(reason="live test — run with `pytest -m live`")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)
