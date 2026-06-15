"""
Study Plan Generator Agent

Role (per the suggested architecture):
    "Convert learning content into a practical study schedule.
     Recommended grounding: Fabric IQ semantic layer for modelling
     certification, role, skill areas, and recommended study hours.
     Recommend milestones at role level. Allocate study hours accounting
     for workload and schedule. Adjust sequencing based on difficulty,
     prerequisites."

This agent implements a Planner-Executor pattern:
  - Plan: derive milestones (one per required skill) from the Fabric IQ
    ontology for the learner's target certification.
  - Execute: allocate the remaining study hours (recommended_hours -
    hours_already_studied, or an adjusted target on a loop-back) across
    those milestones.
"""

from __future__ import annotations

import re
from typing import List, Optional

from src.agents.base import ChatClient
from src.config import get_learn_mcp_config
from src.iq_layers.fabric_iq import FabricIQ

SYSTEM_PROMPT = (
    "You are the Study Plan Generator Agent. Given a structured study plan "
    "(milestones with allocated hours, derived from a certification "
    "ontology), write a 2-3 sentence summary of the plan for the learner. "
    "Only describe the milestones and hours provided; do not invent new ones."
)

_DURATION_RE = re.compile(r"(\d+)\s*(hours?|hrs?|minutes?|mins?)", re.IGNORECASE)


def _attach_learn_modules(foundry_iq, cert_id: str, cert_model: dict, milestones: List[dict]) -> dict:
    """Ground milestones in Microsoft Learn learning-path modules (optional).

    Retrieves Learn module references for the certification, attaches a Learn
    citation to each skill milestone whose terms match a module, and parses any
    duration estimates for a reconciliation signal against the Fabric IQ
    recommended hours. Returns a dict with the module list and the (optional)
    Learn-estimated hours. Never raises — degrades to an empty result so the
    plan stays ontology-only.
    """
    cert_name = cert_model.get("name", cert_id)
    try:
        results = foundry_iq.query(f"{cert_id} {cert_name} learning path modules", top_k=8)
    except Exception:  # noqa: BLE001 - best-effort grounding
        results = []

    learn = [r for r in results if r.source_tier == "microsoft-learn-public" and r.source_url]
    modules = [{"title": r.section, "url": r.source_url} for r in learn]

    # Attach a Learn module reference to each milestone whose skill terms appear
    # in the module text.
    for m in milestones:
        skill_terms = {t for t in re.findall(r"[a-z0-9]+", m["skill"].lower()) if len(t) > 2}
        for r in learn:
            haystack = f"{r.section} {r.text}".lower()
            if any(t in haystack for t in skill_terms):
                m["learn_reference"] = {"title": r.section, "url": r.source_url}
                break

    # Parse duration estimates from the module text (reconciliation signal only;
    # the actual allocation stays driven by the Fabric IQ ontology).
    minutes = 0
    for r in learn:
        for num, unit in _DURATION_RE.findall(r.text):
            n = int(num)
            minutes += n * 60 if unit.lower().startswith(("hour", "hr")) else n
    estimated_hours = round(minutes / 60, 1) if minutes else None

    return {"modules": modules, "estimated_hours": estimated_hours}


def run(
    learner_id: str,
    fabric_iq: FabricIQ,
    chat_client: ChatClient,
    target_hours_override: Optional[int] = None,
    iteration: int = 1,
    foundry_iq=None,
) -> dict:
    learner = fabric_iq.get_learner(learner_id)
    cert = fabric_iq.get_certification(learner["target_certification"])

    readiness = fabric_iq.compute_readiness(learner_id, hours_studied_override=None)

    recommended_hours = cert["recommended_hours"]
    hours_studied = learner["hours_studied"]

    # PLAN: one milestone per skill required by the certification.
    skills: List[str] = cert["skills"]

    # EXECUTE: allocate the *remaining* hours (or an adjusted target on a
    # loop-back from the Assessment Agent) evenly across milestones.
    if target_hours_override is not None:
        remaining_hours = max(target_hours_override, 1)
    else:
        remaining_hours = max(recommended_hours - hours_studied, 1)

    base_alloc = remaining_hours // len(skills)
    leftover = remaining_hours - base_alloc * len(skills)

    milestones = []
    for i, skill in enumerate(skills):
        hours = base_alloc + (1 if i < leftover else 0)
        milestones.append({"skill": skill, "allocated_hours": hours})

    plan = {
        "certification": learner["target_certification"],
        "prerequisites": cert["prerequisites"],
        "recommended_total_hours": recommended_hours,
        "hours_already_studied": hours_studied,
        "remaining_hours_target": remaining_hours,
        "milestones": milestones,
        "iteration": iteration,
    }

    # Optional: ground milestones in Microsoft Learn learning-path modules.
    # The actual hour allocation stays ontology-driven; Learn adds citations and
    # a duration reconciliation signal. Falls back to ontology-only when off.
    learn_note = ""
    config = get_learn_mcp_config()
    if config.enabled and foundry_iq is not None:
        learn_info = _attach_learn_modules(foundry_iq, plan["certification"], cert, milestones)
        if learn_info["modules"]:
            plan["learn_modules"] = learn_info["modules"]
            cited = sum(1 for m in milestones if "learn_reference" in m)
            learn_note = f" {cited} milestone(s) grounded in Microsoft Learn modules."
            if learn_info["estimated_hours"]:
                plan["learn_estimated_hours"] = learn_info["estimated_hours"]
                plan["hours_reconciliation"] = (
                    f"Fabric IQ recommends {recommended_hours}h; Microsoft Learn modules "
                    f"estimate ~{learn_info['estimated_hours']}h."
                )

    context = (
        f"Learner {learner_id} targeting {plan['certification']} "
        f"(iteration {iteration}). Remaining hours target: {remaining_hours}. "
        f"Milestones: " + ", ".join(f"{m['skill']} ({m['allocated_hours']}h)" for m in milestones)
        + learn_note
    )
    narrative = chat_client.complete(SYSTEM_PROMPT, context)
    if narrative is None:
        milestone_str = "; ".join(f"{m['skill']}: {m['allocated_hours']}h" for m in milestones)
        narrative = (
            f"Study plan for {plan['certification']} (iteration {iteration}): "
            f"target {remaining_hours} additional hours across {len(milestones)} skill "
            f"areas \u2014 {milestone_str}." + learn_note
        )

    return {
        "agent": "study_plan_generator",
        "learner_id": learner_id,
        "plan": plan,
        "readiness_snapshot": readiness.__dict__,
        "narrative": narrative,
    }
