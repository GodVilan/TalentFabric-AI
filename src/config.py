"""
Runtime configuration for TalentFabric AI.

Currently this centralises the Microsoft Learn MCP integration settings. The
single most important value is :data:`LEARN_MCP_ENABLED`, which defaults to
**off** — with it off, the entire system runs on synthetic data only, fully
functional, exactly as it did before the MCP integration existed. This toggle
is the compliance backbone of the two-category content model (see README /
docs/ARCHITECTURE.md).

Values are read from the environment (and a ``.env`` file if python-dotenv is
installed), mirroring the credential-loading pattern in
``src/agents/base.py``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Load .env automatically so settings are picked up whether they are exported
# in the shell or written to a .env file at the project root.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - python-dotenv is optional
    pass

DEFAULT_LEARN_MCP_ENDPOINT = "https://learn.microsoft.com/api/mcp"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class LearnMCPConfig:
    """Resolved Microsoft Learn MCP settings."""

    enabled: bool
    endpoint: str
    max_token_budget: int
    cache_ttl_hours: int

    @property
    def endpoint_with_budget(self) -> str:
        """Endpoint URL with the ``maxTokenBudget`` cost-control query param."""
        sep = "&" if "?" in self.endpoint else "?"
        return f"{self.endpoint}{sep}maxTokenBudget={self.max_token_budget}"


def get_learn_mcp_config() -> LearnMCPConfig:
    """Read the current Learn MCP configuration from the environment.

    Read fresh each call (not cached at import) so tests can flip
    ``LEARN_MCP_ENABLED`` via the environment without reloading the module.
    """
    return LearnMCPConfig(
        enabled=_env_bool("LEARN_MCP_ENABLED", default=False),
        endpoint=os.getenv("LEARN_MCP_ENDPOINT", DEFAULT_LEARN_MCP_ENDPOINT),
        max_token_budget=_env_int("LEARN_MCP_MAX_TOKEN_BUDGET", default=4000),
        cache_ttl_hours=_env_int("LEARN_MCP_CACHE_TTL_HOURS", default=24),
    )
