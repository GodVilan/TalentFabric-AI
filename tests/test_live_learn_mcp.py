"""
Opt-in LIVE tests against the real Microsoft Learn MCP endpoint.

Deselected by default (see conftest). Run in a networked environment with:

    pytest -m live

These verify the actual server contract, complementing the network-free
mocked-transport tests in test_learn_mcp.py.
"""

from __future__ import annotations

import pytest

from src.config import LearnMCPConfig
from src.iq_layers.learn_mcp import LearnMCPClient
from src.iq_layers.provenance import MICROSOFT_LEARN_PUBLIC

# The live path needs the optional `mcp` SDK. If it isn't importable, skip with
# a clear reason rather than failing with a misleading empty-results assertion
# (the client deliberately swallows the ImportError and degrades to []).
pytest.importorskip("mcp", reason="install the MCP SDK (pip install mcp) to run live tests")

pytestmark = pytest.mark.live


def _client() -> LearnMCPClient:
    cfg = LearnMCPConfig(
        enabled=True,
        endpoint="https://learn.microsoft.com/api/mcp",
        max_token_budget=4000,
        cache_ttl_hours=24,
    )
    return LearnMCPClient(config=cfg, use_cache=False)


def test_live_search_returns_public_chunks():
    chunks = _client().search("Azure Functions triggers and bindings")
    assert chunks, "expected live results from Microsoft Learn"
    assert all(c.source_tier == MICROSOFT_LEARN_PUBLIC for c in chunks)
    assert any(c.source_url and "learn.microsoft.com" in c.source_url for c in chunks)


def test_live_code_sample_search():
    samples = _client().code_search("Azure Functions HTTP trigger", language="python")
    # Code samples may be sparse for some queries, but the call must not raise.
    assert isinstance(samples, list)
