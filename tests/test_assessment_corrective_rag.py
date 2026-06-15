"""
Tests for the Assessment Agent's corrective-RAG loop + validation gate.

All deterministic and network/LLM-free: the groundedness heuristic is pure
term-overlap, and corrective re-retrieval is exercised with an in-process stub.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.agents import assessment_agent as aa
from src.agents.base import MockChatClient
from src.iq_layers.fabric_iq import FabricIQ
from src.iq_layers.foundry_iq import RetrievalResult

DATA = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture
def fabric_iq() -> FabricIQ:
    return FabricIQ(DATA / "fabric_iq_semantic_model.json", DATA / "learners.json")


# --- deterministic groundedness heuristic ----------------------------------
def test_groundedness_high_for_on_topic_passage():
    q = "What is the core purpose of API Development in the context of AZ-204?"
    passage = "Designing, building and securing RESTful APIs; API versioning and API Management."
    assert aa.groundedness_score(q, passage) >= aa.GROUNDEDNESS_THRESHOLD
    assert aa.is_grounded(q, passage)


def test_groundedness_zero_for_off_topic_passage():
    q = "What is the core purpose of API Development in the context of AZ-204?"
    passage = "Quarterly budget review and travel reimbursement meeting notes."
    assert aa.groundedness_score(q, passage) == 0.0
    assert not aa.is_grounded(q, passage)


def test_groundedness_zero_for_empty_passage():
    assert aa.groundedness_score("anything about storage", "") == 0.0


# --- validation gate: drop ungrounded when no corrective source -------------
def _resources_one_empty() -> list[dict]:
    return [
        {
            "source": "az204_guide",
            "section": "Skill Area: API Development",
            "snippet": "Designing, building and securing RESTful APIs; API versioning and API Management.",
            "score": 0.9, "source_tier": "synthetic-internal", "source_url": None,
        },
        {
            "source": "az204_guide",
            "section": "Skill Area: Storage",
            "snippet": "",  # empty -> ungrounded
            "score": 0.1, "source_tier": "synthetic-internal", "source_url": None,
        },
    ]


def test_gate_drops_ungrounded_without_corrective(fabric_iq):
    result = aa.run(
        "L-1001", _resources_one_empty(), {"remaining_hours_target": 6},
        fabric_iq, MockChatClient(), iteration=1, foundry_iq=None,
    )
    v = result["validation"]
    assert v["generated"] == 2
    assert v["emitted"] == 1
    assert v["dropped"] == 1
    assert v["corrective_retrieval_used"] is False
    assert v["all_emitted_grounded"] is True
    assert all("groundedness" in q and "source_tier" in q for q in result["practice_questions"])


def test_gate_recovers_ungrounded_with_corrective(fabric_iq):
    class StubFoundry:
        def query(self, query_text, top_k=3):
            return [
                RetrievalResult(
                    source="az204_guide",
                    section="Skill Area: Storage",
                    text="Azure Storage accounts, blob storage, storage redundancy and storage security.",
                    score=0.8,
                )
            ]

    result = aa.run(
        "L-1001", _resources_one_empty(), {"remaining_hours_target": 6},
        fabric_iq, MockChatClient(), iteration=1, foundry_iq=StubFoundry(),
    )
    v = result["validation"]
    assert v["corrective_retrieval_used"] is True
    assert v["corrective_recovered"] == 1
    assert v["emitted"] == 2
    assert v["dropped"] == 0


# --- drift detection -------------------------------------------------------
def test_drift_flags_uncovered_skills():
    skills = ["API Development", "Azure Functions", "Storage", "Authentication"]
    resources = [
        {"section": "Skill Area: API Development",
         "snippet": "RESTful versioning and request validation and response caching."},
    ]
    drift = aa._detect_drift(skills, [], resources)
    assert drift["drift_flag"] is True
    assert "Azure Functions" in drift["drift_skills"]
    assert "Storage" in drift["drift_skills"]
    assert "API Development" not in drift["drift_skills"]  # covered by the section


def test_no_drift_when_all_skills_covered():
    skills = ["API Development", "Storage"]
    resources = [
        {"section": "Skill Area: API Development", "snippet": "API design."},
        {"section": "Skill Area: Storage", "snippet": "Storage accounts."},
    ]
    drift = aa._detect_drift(skills, [], resources)
    assert drift["drift_flag"] is False
    assert drift["drift_skills"] == []


# --- the corrective loop must not touch the readiness loop-back budget ------
def test_loopback_cap_respected(fabric_iq):
    # L-1009 is below the practice threshold, so it stays Not Ready even after
    # the loop-back adds hours: it loops back at iteration 1 but not at the cap (2).
    res_at_1 = aa.run("L-1009", _resources_one_empty(), {"remaining_hours_target": 6},
                      fabric_iq, MockChatClient(), iteration=1)
    res_at_2 = aa.run("L-1009", _resources_one_empty(), {"remaining_hours_target": 6},
                      fabric_iq, MockChatClient(), iteration=2)
    assert res_at_1["loop_back"] is True
    assert res_at_2["loop_back"] is False  # MAX_ITERATIONS guard holds


def test_loopback_flips_hours_limited_learner(fabric_iq):
    # L-1005 has a passing practice score but is short on hours; the loop-back's
    # extra hours flip it Not Ready (iter 1) -> Ready (iter 2). This is fix #1.
    res_at_1 = aa.run("L-1005", _resources_one_empty(), {"remaining_hours_target": 6},
                      fabric_iq, MockChatClient(), iteration=1)
    res_at_2 = aa.run("L-1005", _resources_one_empty(), {"remaining_hours_target": 6},
                      fabric_iq, MockChatClient(), iteration=2)
    assert res_at_1["readiness"]["readiness_status"] == "Not Ready"
    assert res_at_2["readiness"]["readiness_status"] == "Ready"
