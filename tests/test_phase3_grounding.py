"""
Tests for Phase 3: Study Plan Learn-module grounding + Manager Insights
grounded next-certification recommendation. All network-free (stubbed FoundryIQ).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agents import manager_insights_agent, study_plan_generator
from src.agents.base import MockChatClient
from src.iq_layers.fabric_iq import FabricIQ
from src.iq_layers.foundry_iq import RetrievalResult

DATA = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture
def fabric_iq() -> FabricIQ:
    return FabricIQ(DATA / "fabric_iq_semantic_model.json", DATA / "learners.json")


class StubFoundry:
    def __init__(self, results):
        self._results = results

    def query(self, query_text, top_k=3):
        return self._results


def _learn_modules():
    return [
        RetrievalResult(
            source="microsoft-learn",
            section="Develop Azure Functions",
            text="Create and deploy Azure Functions with storage bindings. This module takes 45 minutes.",
            score=0.0,
            source_tier="microsoft-learn-public",
            source_url="https://learn.microsoft.com/training/modules/develop-azure-functions/",
        ),
        RetrievalResult(
            source="microsoft-learn",
            section="Manage APIs with API Management",
            text="Publish, secure and monitor APIs. Estimated 1 hour.",
            score=0.0,
            source_tier="microsoft-learn-public",
            source_url="https://learn.microsoft.com/training/modules/api-management/",
        ),
    ]


# --- Study Plan Generator --------------------------------------------------
def test_study_plan_off_is_ontology_only(fabric_iq, monkeypatch):
    monkeypatch.delenv("LEARN_MCP_ENABLED", raising=False)
    plan = study_plan_generator.run(
        "L-1001", fabric_iq, MockChatClient(), foundry_iq=StubFoundry(_learn_modules())
    )["plan"]

    assert "learn_modules" not in plan
    assert all("learn_reference" not in m for m in plan["milestones"])


def test_study_plan_on_grounds_milestones_in_learn(fabric_iq, monkeypatch):
    monkeypatch.setenv("LEARN_MCP_ENABLED", "true")
    plan = study_plan_generator.run(
        "L-1001", fabric_iq, MockChatClient(), foundry_iq=StubFoundry(_learn_modules())
    )["plan"]

    assert plan["learn_modules"], "expected Learn module references"
    assert all(m["url"].startswith("https://learn.microsoft.com") for m in plan["learn_modules"])
    assert any("learn_reference" in m for m in plan["milestones"]), "expected ≥1 grounded milestone"
    # 45 min + 60 min = 105 min ≈ 1.8h
    assert plan["learn_estimated_hours"] == pytest.approx(1.8, abs=0.1)
    assert "hours_reconciliation" in plan


def test_study_plan_on_without_learn_results_degrades(fabric_iq, monkeypatch):
    monkeypatch.setenv("LEARN_MCP_ENABLED", "true")
    plan = study_plan_generator.run(
        "L-1001", fabric_iq, MockChatClient(), foundry_iq=StubFoundry([])
    )["plan"]
    assert "learn_modules" not in plan
    assert all("learn_reference" not in m for m in plan["milestones"])


# --- Manager Insights ------------------------------------------------------
def _ready_learner_results():
    return [
        {
            "learner_id": "L-1009",
            "role": "Cloud Engineer",
            "assessment": {
                "readiness": {"readiness_status": "Ready", "risk_level": "Low"},
                "recommended_next_certification": "AZ-305",
            },
            "engagement": {"schedule": {"capacity_flag": False}},
        }
    ]


def test_manager_off_has_no_learn_citation(fabric_iq, monkeypatch):
    monkeypatch.delenv("LEARN_MCP_ENABLED", raising=False)
    report = manager_insights_agent.run(
        "TEAM-C", _ready_learner_results(), fabric_iq, MockChatClient()
    )["report"]
    assert report["recommended_next_steps"]
    assert all("learn_reference" not in s for s in report["recommended_next_steps"])


def test_manager_on_grounds_next_cert(fabric_iq, monkeypatch):
    monkeypatch.setenv("LEARN_MCP_ENABLED", "true")
    stub = StubFoundry([
        RetrievalResult(
            source="microsoft-learn",
            section="AZ-305 certification path",
            text="Designing Microsoft Azure Infrastructure Solutions.",
            score=0.0,
            source_tier="microsoft-learn-public",
            source_url="https://learn.microsoft.com/credentials/certifications/azure-solutions-architect/",
        )
    ])
    result = manager_insights_agent.run(
        "TEAM-C", _ready_learner_results(), fabric_iq, MockChatClient(), foundry_iq=stub
    )
    steps = result["report"]["recommended_next_steps"]
    assert steps[0]["learn_reference"]["url"].startswith("https://learn.microsoft.com")


def test_manager_report_never_exposes_individual_scores(fabric_iq, monkeypatch):
    monkeypatch.setenv("LEARN_MCP_ENABLED", "true")
    stub = StubFoundry([])
    report = manager_insights_agent.run(
        "TEAM-C", _ready_learner_results(), fabric_iq, MockChatClient(), foundry_iq=stub
    )["report"]
    blob = json.dumps(report).lower()
    assert "practice_score" not in blob
    assert "practice_score_avg" not in blob


# --- Engagement Agent must remain Work-IQ-only -----------------------------
def test_engagement_agent_has_no_mcp_coupling():
    src = (Path(__file__).resolve().parent.parent / "src" / "agents" / "engagement_agent.py").read_text()
    assert "learn_mcp" not in src
    assert "get_learn_mcp_config" not in src
