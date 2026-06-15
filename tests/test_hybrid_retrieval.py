"""
Tests for FoundryIQ hybrid retrieval-fusion + three-tier fallback.

Verifies:
  * MCP **off** (default) → identical to the original synthetic-only retriever
    (all results synthetic-internal, no URLs, requested top_k respected).
  * MCP **on** with results → fused output spans both provenance tiers and
    Learn results carry live URLs.
  * MCP **on** but empty/failing Learn → degrades cleanly to synthetic-only.
All network-free: an in-process stub stands in for the Learn client.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.iq_layers.foundry_iq import LEARN_SOURCE, FoundryIQ
from src.iq_layers.provenance import (
    MICROSOFT_LEARN_PUBLIC,
    SYNTHETIC_INTERNAL,
    RetrievedChunk,
)

KB_DIR = Path(__file__).resolve().parent.parent / "data" / "knowledge_base"


class StubLearnClient:
    """Minimal stand-in exposing the .search() the hybrid path calls."""

    def __init__(self, chunks=None, raises: bool = False) -> None:
        self._chunks = chunks or []
        self._raises = raises

    def search(self, query: str):
        if self._raises:
            raise RuntimeError("learn boom")
        return self._chunks


def _learn_chunks():
    return [
        RetrievedChunk(
            text="Azure Functions let you run event-driven serverless code.",
            source_tier=MICROSOFT_LEARN_PUBLIC,
            source_ref="Azure Functions overview",
            source_url="https://learn.microsoft.com/azure/azure-functions/",
            score=0.9,
        ),
        RetrievedChunk(
            text="Durable Functions enable stateful orchestrations.",
            source_tier=MICROSOFT_LEARN_PUBLIC,
            source_ref="Durable Functions",
            source_url="https://learn.microsoft.com/azure/azure-functions/durable/",
            score=0.8,
        ),
    ]


def test_mcp_off_is_synthetic_only(monkeypatch):
    monkeypatch.delenv("LEARN_MCP_ENABLED", raising=False)
    fiq = FoundryIQ(KB_DIR, learn_client=StubLearnClient(_learn_chunks()))

    results = fiq.query("AZ-204 Azure Functions storage", top_k=3)

    assert len(results) == 3
    assert all(r.source_tier == SYNTHETIC_INTERNAL for r in results)
    assert all(r.source_url is None for r in results)
    assert all("→" in r.citation() and "http" not in r.citation() for r in results)


def test_mcp_on_fuses_both_tiers(monkeypatch):
    monkeypatch.setenv("LEARN_MCP_ENABLED", "true")
    fiq = FoundryIQ(KB_DIR, learn_client=StubLearnClient(_learn_chunks()))

    results = fiq.query("Azure Functions", top_k=5)

    tiers = {r.source_tier for r in results}
    assert MICROSOFT_LEARN_PUBLIC in tiers, "expected at least one public Learn result"
    assert SYNTHETIC_INTERNAL in tiers, "expected at least one synthetic result"

    learn = [r for r in results if r.source_tier == MICROSOFT_LEARN_PUBLIC]
    assert learn and all(r.source == LEARN_SOURCE for r in learn)
    assert all(r.source_url and r.source_url.startswith("https://learn.microsoft.com") for r in learn)
    # Learn citations include the URL; synthetic ones do not.
    assert any("http" in r.citation() for r in learn)


def test_mcp_on_empty_learn_degrades_to_synthetic(monkeypatch):
    monkeypatch.setenv("LEARN_MCP_ENABLED", "true")
    fiq = FoundryIQ(KB_DIR, learn_client=StubLearnClient(chunks=[]))

    results = fiq.query("Azure Functions", top_k=3)
    assert len(results) == 3
    assert all(r.source_tier == SYNTHETIC_INTERNAL for r in results)


def test_mcp_on_failing_learn_degrades_without_raising(monkeypatch):
    monkeypatch.setenv("LEARN_MCP_ENABLED", "true")
    fiq = FoundryIQ(KB_DIR, learn_client=StubLearnClient(raises=True))

    results = fiq.query("Azure Functions", top_k=3)  # must not raise
    assert len(results) == 3
    assert all(r.source_tier == SYNTHETIC_INTERNAL for r in results)


def test_off_and_on_empty_return_same_top_results(monkeypatch):
    """Toggling on with no Learn data must not change the synthetic ranking."""
    monkeypatch.delenv("LEARN_MCP_ENABLED", raising=False)
    off = FoundryIQ(KB_DIR).query("DP-203 data pipelines", top_k=3)

    monkeypatch.setenv("LEARN_MCP_ENABLED", "true")
    on_empty = FoundryIQ(KB_DIR, learn_client=StubLearnClient(chunks=[])).query("DP-203 data pipelines", top_k=3)

    assert [(r.source, r.section) for r in off] == [(r.source, r.section) for r in on_empty]
