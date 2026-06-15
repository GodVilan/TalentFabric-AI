"""
Work IQ layer (local stand-in).

Suggested implementation pattern (from the challenge starter kit):
    "Use the Work IQ concept as the context layer that informs the
    Engagement Agent and any user-specific planning logic. Treat work
    signals such as meetings, focus time, and collaboration load as
    contextual inputs. Use those signals to choose study windows,
    reminder timing, or escalation thresholds. Keep outputs supportive
    and privacy-conscious."

This module loads the synthetic work_activity_signals.json dataset and
exposes the per-employee signals plus a simple, explainable recommendation
function used by the Engagement Agent and (in aggregate, privacy-conscious
form) by the Manager Insights Agent.

Production migration path
--------------------------
Replace `WorkIQ._signals` with a call to the Work IQ API, which derives
equivalent signals (meeting load, focus time, collaboration patterns) from
Microsoft 365 tenant data (Graph calendar, activity signals, etc.).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional


# Capacity thresholds, mirroring data/knowledge_base/workload_insights_report.md
HIGH_MEETING_LOAD_HOURS = 20
LOW_FOCUS_HOURS = 12
GOOD_FOCUS_HOURS = 15


@dataclass
class StudyWindowRecommendation:
    employee_id: str
    recommended_slot: str
    session_length_minutes: int
    capacity_flag: bool
    rationale: str


class WorkIQ:
    """Local stand-in for the Work IQ workplace-signal context layer."""

    def __init__(self, signals_path: str | Path):
        with open(signals_path, "r", encoding="utf-8") as f:
            records = json.load(f)
        self._signals: Dict[str, dict] = {r["employee_id"]: r for r in records}

    def get_signals(self, employee_id: str) -> Optional[dict]:
        return self._signals.get(employee_id)

    def recommend_study_window(self, employee_id: str) -> StudyWindowRecommendation:
        signals = self.get_signals(employee_id)
        if signals is None:
            raise KeyError(f"No Work IQ signals found for {employee_id}")

        meeting_hours = signals["meeting_hours_per_week"]
        focus_hours = signals["focus_hours_per_week"]
        slot = signals["preferred_learning_slot"]

        capacity_flag = meeting_hours > HIGH_MEETING_LOAD_HOURS and focus_hours < LOW_FOCUS_HOURS

        if capacity_flag:
            session_length = 30
            rationale = (
                f"{meeting_hours}h of meetings and only {focus_hours}h of focus time "
                f"this week \u2014 capacity-constrained. Recommending short, frequent "
                f"sessions in the {slot.lower()} slot to avoid disrupting peak work periods."
            )
        elif focus_hours >= GOOD_FOCUS_HOURS:
            session_length = 60
            rationale = (
                f"{focus_hours}h of focus time available \u2014 recommending a single "
                f"focused {60}-minute session in the {slot.lower()} slot."
            )
        else:
            session_length = 45
            rationale = (
                f"Moderate workload ({meeting_hours}h meetings, {focus_hours}h focus). "
                f"Recommending a {45}-minute session in the {slot.lower()} slot."
            )

        return StudyWindowRecommendation(
            employee_id=employee_id,
            recommended_slot=slot,
            session_length_minutes=session_length,
            capacity_flag=capacity_flag,
            rationale=rationale,
        )
