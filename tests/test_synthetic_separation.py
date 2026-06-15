"""
Compliance gate: the two content categories must stay strictly separated.

These tests are the executable form of hard invariant #1 (see the approved
plan / docs/ARCHITECTURE.md):

  * Synthetic record files in ``data/`` contain only synthetic-shaped
    identifiers — no real names, emails, or organisational data.
  * The synthetic data-loading layers (Fabric IQ, Work IQ) do not import the
    Microsoft Learn MCP client — public content can only ever flow through the
    retrieval/citation layer, never into the synthetic record loaders.
  * Public ``microsoft-learn-public`` content cannot be serialised into a
    ``data/`` record (the provenance guard rejects it).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.iq_layers.provenance import (
    MICROSOFT_LEARN_PUBLIC,
    SYNTHETIC_INTERNAL,
    ProvenanceViolationError,
    RetrievedChunk,
    assert_not_public,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

LEARNER_ID = re.compile(r"^L-1\d{3}$")
EMPLOYEE_ID = re.compile(r"^EMP-\d{3}$")
TEAM_ID = re.compile(r"^TEAM-[A-Z]$")
CERT_ID = re.compile(r"^[A-Z]{2}-\d{3}$")
PREFERRED_SLOTS = {"Morning", "Afternoon", "Evening"}


def test_learner_ids_are_synthetic() -> None:
    records = json.loads((DATA_DIR / "learners.json").read_text())
    assert records, "learners.json is empty"
    for r in records:
        assert LEARNER_ID.match(r["learner_id"]), r["learner_id"]
        assert EMPLOYEE_ID.match(r["employee_id"]), r["employee_id"]
        assert TEAM_ID.match(r["team_id"]), r["team_id"]
        assert CERT_ID.match(r["target_certification"]), r["target_certification"]


def test_work_signal_ids_are_synthetic() -> None:
    records = json.loads((DATA_DIR / "work_activity_signals.json").read_text())
    assert records, "work_activity_signals.json is empty"
    for r in records:
        assert EMPLOYEE_ID.match(r["employee_id"]), r["employee_id"]
        assert r["preferred_learning_slot"] in PREFERRED_SLOTS


def test_no_free_text_email_in_data_records() -> None:
    """No real-looking email addresses anywhere in the synthetic record files."""
    email = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    for name in ("learners.json", "work_activity_signals.json", "fabric_iq_semantic_model.json"):
        text = (DATA_DIR / name).read_text()
        assert not email.search(text), f"unexpected email-shaped string in {name}"


def test_synthetic_loaders_do_not_import_mcp() -> None:
    """Fabric IQ and Work IQ (the synthetic record loaders) must not import the MCP layer."""
    for module in ("fabric_iq.py", "work_iq.py"):
        src = (Path(__file__).resolve().parent.parent / "src" / "iq_layers" / module).read_text()
        assert "learn_mcp" not in src, f"{module} must not import the Learn MCP client"


def test_provenance_guard_rejects_public_content() -> None:
    public = RetrievedChunk(
        text="Azure Functions overview",
        source_tier=MICROSOFT_LEARN_PUBLIC,
        source_ref="Azure Functions docs",
        source_url="https://learn.microsoft.com/azure/azure-functions/",
    )
    with pytest.raises(ProvenanceViolationError):
        assert_not_public(public)
    # dict form (loosely-typed payloads) is guarded too
    with pytest.raises(ProvenanceViolationError):
        assert_not_public({"source_tier": MICROSOFT_LEARN_PUBLIC, "text": "x"})


def test_provenance_guard_allows_synthetic_content() -> None:
    synthetic = RetrievedChunk(
        text="Synthetic AZ-204 guidance",
        source_tier=SYNTHETIC_INTERNAL,
        source_ref="az204_guide → Skill Area: API Development",
    )
    assert_not_public(synthetic)  # must not raise
    assert_not_public({"source_tier": SYNTHETIC_INTERNAL})
