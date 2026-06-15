"""
Fabric IQ layer (local stand-in).

Suggested implementation pattern (from the challenge starter kit):
    "Use Fabric IQ as the semantic layer for business meaning and structured
    decision support across the enterprise learning system. Model entities
    such as learner, certification, role, skill gap, readiness score, and
    recommended hours. Represent relationships and rules such as
    prerequisites, role alignment, or pass thresholds. Use those semantic
    structures to inform study recommendations and manager insight
    summaries."

This module loads:
  - data/fabric_iq_semantic_model.json: the ontology (certifications, role
    alignment, skills, recommended hours, prerequisites, pass thresholds,
    and the "next certification" relationship)
  - data/learners.json: the synthetic learner roster (current practice
    scores, hours studied, exam outcomes)

...and exposes structured decision-support functions (readiness scoring,
skill-gap calculation, next-step recommendation) used by the Study Plan
Generator, Assessment Agent, and Manager Insights Agent.

Production migration path
--------------------------
Replace the JSON-backed lookups below with queries against a Fabric IQ
ontology / OneLake semantic model, keeping the same return shapes so the
agents above this layer do not need to change.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class ReadinessAssessment:
    learner_id: str
    certification: str
    practice_score_avg: int
    pass_threshold: int
    hours_studied: int
    recommended_hours: int
    score_gap: int
    hours_completion_ratio: float
    readiness_status: str  # "Ready" | "Not Ready"
    risk_level: str  # "Low" | "Medium" | "High"


class FabricIQ:
    """Local stand-in for the Fabric IQ semantic / ontology layer."""

    def __init__(self, semantic_model_path: str | Path, learners_path: str | Path):
        with open(semantic_model_path, "r", encoding="utf-8") as f:
            self.model = json.load(f)
        with open(learners_path, "r", encoding="utf-8") as f:
            records = json.load(f)
        self._learners: Dict[str, dict] = {r["learner_id"]: r for r in records}

        self._study_pattern = self.model["study_pattern"]

    # ------------------------------------------------------------------
    # Ontology lookups
    # ------------------------------------------------------------------
    def get_certification(self, cert_id: str) -> dict:
        return self.model["certifications"][cert_id]

    def get_role_mapping(self, role: str) -> dict:
        return self.model["roles"][role]

    def get_next_certification(self, cert_id: str) -> Optional[str]:
        return self.get_certification(cert_id).get("next_certification")

    # ------------------------------------------------------------------
    # Learner lookups
    # ------------------------------------------------------------------
    def get_learner(self, learner_id: str) -> dict:
        return self._learners[learner_id]

    def list_learners(self, team_id: Optional[str] = None) -> List[dict]:
        learners = list(self._learners.values())
        if team_id:
            learners = [l for l in learners if l["team_id"] == team_id]
        return learners

    def list_teams(self) -> List[str]:
        return sorted({l["team_id"] for l in self._learners.values()})

    # ------------------------------------------------------------------
    # Decision support
    # ------------------------------------------------------------------
    def compute_readiness(
        self,
        learner_id: str,
        hours_studied_override: Optional[int] = None,
        extra_hours: int = 0,
    ) -> ReadinessAssessment:
        """Compute a learner's readiness.

        ``extra_hours`` models additional study accrued by Critic/Verifier
        loop-backs (the Study Plan Generator allocated more hours), so a later
        iteration is re-evaluated against the post-loop-back hours — this is what
        lets an hours-limited learner flip Not Ready -> Ready on a later pass.
        """
        learner = self.get_learner(learner_id)
        cert = self.get_certification(learner["target_certification"])

        practice_score = learner["practice_score_avg"]
        pass_threshold = cert["pass_threshold"]
        recommended_hours = cert["recommended_hours"]
        base_hours = (
            hours_studied_override
            if hours_studied_override is not None
            else learner["hours_studied"]
        )
        hours_studied = base_hours + extra_hours

        score_gap = pass_threshold - practice_score
        hours_completion_ratio = round(hours_studied / recommended_hours, 2)
        min_ratio = self._study_pattern["min_hours_completion_ratio_for_ready"]

        ready = practice_score >= pass_threshold and hours_completion_ratio >= min_ratio

        if ready:
            risk_level = "Low"
        elif score_gap <= 5 and hours_completion_ratio >= min_ratio * 0.75:
            risk_level = "Medium"
        else:
            risk_level = "High"

        return ReadinessAssessment(
            learner_id=learner_id,
            certification=learner["target_certification"],
            practice_score_avg=practice_score,
            pass_threshold=pass_threshold,
            hours_studied=hours_studied,
            recommended_hours=recommended_hours,
            score_gap=score_gap,
            hours_completion_ratio=hours_completion_ratio,
            readiness_status="Ready" if ready else "Not Ready",
            risk_level=risk_level,
        )

    def skill_gap_summary(self, learner_id: str) -> List[str]:
        """Skills tied to the learner's target certification (used for
        Manager Insights skill-gap aggregation when readiness is low)."""
        learner = self.get_learner(learner_id)
        cert = self.get_certification(learner["target_certification"])
        return cert["skills"]
