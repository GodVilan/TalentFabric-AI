"""
Engagement Agent

Role (per the suggested architecture):
    "Keep the learner progressing.
     Recommended grounding: Work IQ to understand work context,
     communication patterns, and preferred timing. Suggest appropriate
     times for reminders based on work rhythm. Adapt engagement to
     individual workload and focus windows. Avoid one-size-fits-all
     reminder behaviour across a diverse team."

This agent consumes the Study Plan Generator's remaining-hours target and
the learner's Work IQ signals to produce a concrete weekly schedule
(session length, slot, and number of sessions per week), and raises a
capacity_flag that the Manager Insights Agent uses for team-level risk
reporting.
"""

from __future__ import annotations

import math

from src.agents.base import ChatClient
from src.iq_layers.work_iq import WorkIQ

SYSTEM_PROMPT = (
    "You are the Engagement Agent. Given a learner's weekly study schedule "
    "(derived from their workload signals), write a short, supportive "
    "2-sentence message describing when and how often they should study. "
    "Keep the tone encouraging and privacy-conscious; do not reference raw "
    "calendar data, only the resulting recommendation."
)


def run(employee_id: str, plan: dict, fabric_iq_learner: dict, work_iq: WorkIQ, chat_client: ChatClient) -> dict:
    remaining_hours = plan["remaining_hours_target"]
    recommendation = work_iq.recommend_study_window(employee_id)

    session_minutes = recommendation.session_length_minutes
    sessions_per_week = max(1, math.ceil((remaining_hours * 60) / session_minutes / 4))
    # (assumes ~4 weeks of runway; rounds up to whole sessions per week)

    schedule = {
        "recommended_slot": recommendation.recommended_slot,
        "session_length_minutes": session_minutes,
        "sessions_per_week": sessions_per_week,
        "capacity_flag": recommendation.capacity_flag,
        "rationale": recommendation.rationale,
    }

    context = (
        f"Recommended {sessions_per_week} session(s)/week, {session_minutes} minutes each, "
        f"in the {recommendation.recommended_slot} slot. Rationale: {recommendation.rationale}"
    )
    narrative = chat_client.complete(SYSTEM_PROMPT, context)
    if narrative is None:
        narrative = (
            f"Plan: {sessions_per_week} session(s) per week of {session_minutes} minutes, "
            f"scheduled in your {recommendation.recommended_slot.lower()} slot. "
            f"{recommendation.rationale}"
        )

    return {
        "agent": "engagement_agent",
        "employee_id": employee_id,
        "schedule": schedule,
        "narrative": narrative,
    }
