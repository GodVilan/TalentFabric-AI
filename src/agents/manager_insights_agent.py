"""
Manager Insights Agent

Role (per the suggested architecture):
    "Provide team-level visibility into certification readiness and
     workforce development.
     Recommended grounding: Work IQ for organisational context and team
     capacity signals; Fabric IQ for semantic analysis of learning metrics
     and workforce skill gaps. Summarise learning progress by team, role,
     or certification track. Highlight patterns such as capacity-constrained
     teams or likely exam risk areas. Present insights without exposing
     sensitive personal data."

This agent implements the fan-in / aggregation stage of the workflow
("Assess & Aggregate team readiness results" in the architecture diagram).
It consumes the per-learner subworkflow results for a team and produces a
team-level report. Individual practice scores are intentionally NOT
surfaced in the report -- only readiness status, risk level, capacity
flags, and skill-gap aggregates -- per the "privacy-conscious" requirement.
"""

from __future__ import annotations

from collections import Counter
from typing import List, Optional

from src.agents.base import ChatClient
from src.config import get_learn_mcp_config
from src.iq_layers.fabric_iq import FabricIQ


def _learn_citation_for_cert(foundry_iq, cert_id: str) -> Optional[dict]:
    """Return a Microsoft Learn citation ({title, url}) for a certification's
    progression path, or None. Never raises."""
    try:
        results = foundry_iq.query(f"{cert_id} certification overview learning path", top_k=5)
    except Exception:  # noqa: BLE001 - best-effort grounding
        return None
    for r in results:
        if r.source_tier == "microsoft-learn-public" and r.source_url:
            return {"title": r.section, "url": r.source_url}
    return None

SYSTEM_PROMPT = (
    "You are the Manager Insights Agent. Given a team-level readiness "
    "summary (counts, risk levels, capacity flags, and skill gaps -- with "
    "NO individual scores), write a concise 3-4 sentence summary for a "
    "manager. Do not invent any numbers not present in the summary, and do "
    "not refer to any individual by name or ID."
)


def run(
    team_id: str,
    learner_results: List[dict],
    fabric_iq: FabricIQ,
    chat_client: ChatClient,
    foundry_iq=None,
) -> dict:
    total = len(learner_results)
    status_counts = Counter()
    risk_counts = Counter()
    capacity_constrained = 0
    skill_gap_counter = Counter()
    next_steps = []

    for result in learner_results:
        readiness = result["assessment"]["readiness"]
        status_counts[readiness["readiness_status"]] += 1
        risk_counts[readiness["risk_level"]] += 1

        if result["engagement"]["schedule"]["capacity_flag"]:
            capacity_constrained += 1

        if readiness["readiness_status"] == "Not Ready":
            for skill in fabric_iq.skill_gap_summary(result["learner_id"]):
                skill_gap_counter[skill] += 1

        next_cert = result["assessment"]["recommended_next_certification"]
        if next_cert:
            next_steps.append({"learner_id": result["learner_id"], "next_certification": next_cert})

    top_skill_gaps = [skill for skill, _ in skill_gap_counter.most_common(3)]

    # Optionally ground each recommended next-certification step in the real
    # Microsoft Learn progression path (a cited URL). Privacy is unchanged: this
    # adds only a public doc citation to the already non-personal recommendation.
    config = get_learn_mcp_config()
    if config.enabled and foundry_iq is not None and next_steps:
        citations: dict[str, Optional[dict]] = {}
        for cert in {s["next_certification"] for s in next_steps}:
            citations[cert] = _learn_citation_for_cert(foundry_iq, cert)
        for step in next_steps:
            cite = citations.get(step["next_certification"])
            if cite:
                step["learn_reference"] = cite

    report = {
        "team_id": team_id,
        "team_size": total,
        "readiness_status_counts": dict(status_counts),
        "risk_level_counts": dict(risk_counts),
        "capacity_constrained_learners": capacity_constrained,
        "top_skill_gaps": top_skill_gaps,
        "recommended_next_steps": next_steps,
    }

    context = (
        f"Team {team_id} ({total} learners): "
        f"readiness status counts {dict(status_counts)}, "
        f"risk level counts {dict(risk_counts)}, "
        f"{capacity_constrained} capacity-constrained learner(s), "
        f"top skill gaps: {top_skill_gaps}. "
        f"{len(next_steps)} learner(s) ready for a next certification step."
    )
    narrative = chat_client.complete(SYSTEM_PROMPT, context)
    if narrative is None:
        narrative = (
            f"Team {team_id}: {status_counts.get('Ready', 0)} of {total} learners are "
            f"Ready, {status_counts.get('Not Ready', 0)} are Not Ready "
            f"({risk_counts.get('High', 0)} High risk, {risk_counts.get('Medium', 0)} Medium risk). "
            f"{capacity_constrained} learner(s) are capacity-constrained based on workload "
            f"signals. "
        )
        if top_skill_gaps:
            narrative += f"Top recurring skill gaps: {', '.join(top_skill_gaps)}. "
        if next_steps:
            narrative += f"{len(next_steps)} learner(s) are ready to advance to a next certification."

    return {
        "agent": "manager_insights_agent",
        "team_id": team_id,
        "report": report,
        "narrative": narrative,
    }
