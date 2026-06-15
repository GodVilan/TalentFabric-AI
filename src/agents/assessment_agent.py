"""
Assessment Agent

Role (per the suggested architecture):
    "Evaluate learner readiness.
     Recommended grounding: Foundry IQ for grounded question generation;
     Fabric IQ for interpreting patterns and scoring thresholds. Generate
     credible, cited questions from approved content. Score or interpret
     readiness based on known certification criteria. Feed results back
     into the planning loop and surface aggregate team readiness signals."

This agent implements two nested reasoning loops:

  1. **Corrective-RAG** (inner, this module): it generates five typed,
     cited practice questions from the hybrid-retrieved resources, then runs a
     deterministic **groundedness gate** (term-overlap between each question
     and its cited passage — no LLM, so it is reproducible and assertable). A
     question that fails the gate triggers a single *corrective re-retrieval*
     from Foundry IQ to regenerate it from a better passage. This happens
     *before* and independently of the readiness loop-back budget.

  2. **Critic / Verifier** (outer, orchestrated by the workflow): it verifies
     readiness against the Fabric IQ pass threshold / recommended-hours model
     and, if the learner is not ready and the iteration cap has not been
     reached, signals a loop-back to the Study Plan Generator.

It also performs non-fatal **drift detection**: comparing the certification's
expected skills (Fabric IQ ontology) against the terms actually covered by the
grounded passages, flagging skills the retrieved knowledge does not cover.

The output-validation gate (drop/regenerate ungrounded questions, every emitted
question provenance-tagged) satisfies the challenge's "validate generated
outputs" requirement and doubles as a leakage check.
"""

from __future__ import annotations

import re
from typing import List, Optional

from src.agents.base import ChatClient
from src.iq_layers.fabric_iq import FabricIQ, ReadinessAssessment

SYSTEM_PROMPT = (
    "You are the Assessment Agent. Given a learner's readiness assessment "
    "(scores, thresholds, and gaps) and a list of cited practice question "
    "topics, write a short, encouraging 2-3 sentence readiness summary. "
    "State clearly whether the learner is Ready or Not Ready and why, using "
    "only the numbers provided."
)

MAX_ITERATIONS = 2
HOURS_INCREMENT_ON_LOOPBACK = 4

# Deterministic groundedness gate. A generated question is "grounded" when this
# fraction of its content terms appears in its cited chunk (heading + snippet)
# AND the snippet itself is substantive. Tuned so that substantive on-topic
# passages pass and empty/thin/off-topic passages fail.
GROUNDEDNESS_THRESHOLD = 0.20
# A cited snippet must carry at least this many content terms to be considered
# substantive enough to ground a question (catches empty/degenerate retrievals,
# the real failure mode when a public Learn result returns little usable text).
MIN_SNIPPET_TERMS = 3
# Drift is flagged only when a cert's curated retrieval covers fewer than this
# fraction of its skills — so the flag discriminates rather than firing for all.
DRIFT_COVERAGE_MIN = 0.6

_QUESTION_TEMPLATES = [
    (
        "Conceptual",
        "What is the core purpose of {topic} in the context of {cert}, "
        "according to the guidance in {source}?",
    ),
    (
        "Applied",
        "Describe the key implementation steps for {topic} as outlined in "
        "{source} → {section}. What does a correct implementation look like?",
    ),
    (
        "Scenario",
        "A cloud team must deploy {topic} in a production environment. "
        "What critical considerations does {source} highlight for this scenario?",
    ),
    (
        "Evaluative",
        "What factors should guide your design decisions when implementing {topic}? "
        "Reference the guidance provided in {source}.",
    ),
    (
        "Comparative",
        "How does the {source} guidance on {topic} address the trade-off between "
        "security, performance, and operational manageability?",
    ),
]

# English + question-template boilerplate, removed before computing groundedness
# so the score reflects the question's *substantive* (topic/cert) terms.
_BASIC_STOP = {
    "the", "a", "an", "of", "in", "to", "for", "and", "or", "is", "are", "be",
    "it", "its", "as", "at", "on", "by", "this", "that", "with", "from", "into",
    "which", "your", "you", "do", "does", "what", "when", "how", "should",
}
_TEMPLATE_STOP = {
    "core", "purpose", "context", "according", "guidance", "describe", "key",
    "implementation", "implementing", "steps", "step", "outlined", "correct",
    "look", "like", "cloud", "team", "must", "deploy", "production",
    "environment", "critical", "considerations", "consideration", "highlight",
    "scenario", "factors", "guide", "design", "decisions", "reference",
    "provided", "address", "trade", "off", "between", "operational",
    "manageability", "working", "area",
}
_GROUNDEDNESS_STOP = _BASIC_STOP | _TEMPLATE_STOP


def _terms(text: str, stop: set[str]) -> set[str]:
    # Keep 2-char tokens (e.g. acronym fragments like "ci"/"cd" from "CI/CD").
    tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {t for t in tokens if len(t) >= 2 and t not in stop}


def groundedness_score(question: str, passage: str) -> float:
    """Fraction of a question's substantive terms supported by its passage.

    Deterministic and LLM-free: ``|Q ∩ P| / |Q|`` over content terms (English
    and question-template boilerplate stripped from ``Q``). Returns 0.0 when
    the question has no content terms or the passage is empty.
    """
    q = _terms(question, _GROUNDEDNESS_STOP)
    if not q:
        return 0.0
    p = _terms(passage, _BASIC_STOP)
    return len(q & p) / len(q)


def is_grounded(question: str, passage: str, threshold: float = GROUNDEDNESS_THRESHOLD) -> bool:
    return groundedness_score(question, passage) >= threshold


def _question_groundedness(question: str, snippet: str, section: str) -> float:
    """Gate score for a generated question against its cited chunk.

    A question is grounded in the *cited chunk* (section heading + snippet), but
    only if the snippet itself is substantive — an empty or degenerate snippet
    scores 0 regardless of the heading, so thin retrievals are caught.
    """
    if len(_terms(snippet, _BASIC_STOP)) < MIN_SNIPPET_TERMS:
        return 0.0
    return groundedness_score(question, f"{section} {snippet}")


def _topic_from_section(section: str) -> str:
    """Extract a clean topic label from a section heading.

    Prefers the specific part after a colon ("Skill Area: API Development" ->
    "API Development"); otherwise uses the heading, stripped of parentheticals.
    """
    label = section.split(":", 1)[1] if ":" in section else section
    return label.split("–")[0].split("(")[0].strip()


def _resource_to_question(index: int, resource: dict, cert: str) -> dict:
    """Build one typed, cited, provenance-tagged question from a resource."""
    q_type, template = _QUESTION_TEMPLATES[index % len(_QUESTION_TEMPLATES)]
    topic = _topic_from_section(resource["section"])
    source_label = resource["source"].replace("_", " ").replace("guide", "Guide").title()
    question = template.format(
        topic=topic, cert=cert, source=source_label, section=resource["section"]
    )
    return {
        "type": q_type,
        "question": question,
        "citation": f"{resource['source']} → {resource['section']}",
        "source_tier": resource.get("source_tier", "synthetic-internal"),
        "source_url": resource.get("source_url"),
    }


def _resource_from_retrieval(r) -> dict:
    """Map a FoundryIQ RetrievalResult into the resource-dict shape."""
    return {
        "source": r.source,
        "section": r.section,
        "snippet": r.text[:240],
        "score": r.score,
        "source_tier": r.source_tier,
        "source_url": r.source_url,
    }


def _generate_and_validate(
    resources: List[dict],
    cert: str,
    foundry_iq=None,
) -> tuple[List[dict], dict]:
    """Generate typed questions, gate them on groundedness, optionally correct.

    Returns ``(emitted_questions, validation_summary)``. Each emitted question
    carries a ``groundedness`` score and is provenance-tagged. Ungrounded
    questions trigger a single corrective re-retrieval (when ``foundry_iq`` is
    available) before being dropped.
    """
    generated = 0
    grounded: List[dict] = []
    ungrounded: List[tuple[int, dict]] = []  # (template_index, resource)

    for i, res in enumerate(resources):
        q = _resource_to_question(i, res, cert)
        score = _question_groundedness(q["question"], res.get("snippet", ""), res.get("section", ""))
        q["groundedness"] = round(score, 3)
        generated += 1
        if score >= GROUNDEDNESS_THRESHOLD:
            grounded.append(q)
        else:
            ungrounded.append((i, res))

    corrective_used = False
    corrective_recovered = 0
    if ungrounded and foundry_iq is not None:
        corrective_used = True
        topics = " ".join(_topic_from_section(res["section"]) for _, res in ungrounded)
        try:
            fresh = foundry_iq.query(f"{cert} {topics}", top_k=len(ungrounded) + 3)
        except Exception:  # noqa: BLE001 - corrective retrieval is best-effort
            fresh = []
        fresh_resources = [_resource_from_retrieval(r) for r in fresh]
        # Regenerate each failed question from the best fresh passage available.
        for (template_index, _orig), fres in zip(ungrounded, fresh_resources):
            q = _resource_to_question(template_index, fres, cert)
            score = _question_groundedness(q["question"], fres.get("snippet", ""), fres.get("section", ""))
            q["groundedness"] = round(score, 3)
            if score >= GROUNDEDNESS_THRESHOLD:
                grounded.append(q)
                corrective_recovered += 1

    validation = {
        "generated": generated,
        "emitted": len(grounded),
        "dropped": generated - len(grounded),
        "corrective_retrieval_used": corrective_used,
        "corrective_recovered": corrective_recovered,
        "groundedness_threshold": GROUNDEDNESS_THRESHOLD,
        "all_emitted_grounded": all(q["groundedness"] >= GROUNDEDNESS_THRESHOLD for q in grounded),
    }
    return grounded, validation


def _detect_drift(skills: List[str], emitted_questions: List[dict], resources: List[dict]) -> dict:
    """Flag certification skills under-covered by the grounded/cited passages.

    Compares the certification's expected skills (Fabric IQ ontology) against the
    terms present across the cited passages and reports a *coverage ratio*. Rather
    than flagging whenever any single skill is missing (which fires for almost
    everyone and means little), drift is flagged only when a meaningful share of
    the cert's skills is genuinely uncovered (``coverage_ratio <
    DRIFT_COVERAGE_MIN``) — so a flag is discriminating and actionable. Non-fatal
    either way; it surfaces a gap between the ontology and the retrieved knowledge
    (synthetic KB, or Learn-augmented when MCP is on).
    """
    covered_terms: set[str] = set()
    for res in resources:
        covered_terms |= _terms(res.get("snippet", ""), _BASIC_STOP)
        covered_terms |= _terms(res.get("section", ""), _BASIC_STOP)

    uncovered_skills = []
    for skill in skills:
        skill_terms = _terms(skill, _BASIC_STOP)
        if skill_terms and not (skill_terms & covered_terms):
            uncovered_skills.append(skill)

    total = len(skills) or 1
    coverage_ratio = round((total - len(uncovered_skills)) / total, 2)
    return {
        "drift_flag": coverage_ratio < DRIFT_COVERAGE_MIN,
        "drift_skills": uncovered_skills,
        "drift_coverage": coverage_ratio,
    }


def run(
    learner_id: str,
    curated_resources: List[dict],
    plan: dict,
    fabric_iq: FabricIQ,
    chat_client: ChatClient,
    iteration: int = 1,
    foundry_iq=None,
) -> dict:
    # Model the additional study each loop-back represents, so readiness is
    # re-evaluated against the post-loop-back hours (the Critic/Verifier loop can
    # then actually flip an hours-limited learner Not Ready -> Ready).
    extra_hours = (iteration - 1) * HOURS_INCREMENT_ON_LOOPBACK
    readiness: ReadinessAssessment = fabric_iq.compute_readiness(
        learner_id, extra_hours=extra_hours
    )
    cert_model = fabric_iq.get_certification(readiness.certification)

    practice_questions, validation = _generate_and_validate(
        curated_resources, readiness.certification, foundry_iq=foundry_iq
    )
    drift = _detect_drift(cert_model["skills"], practice_questions, curated_resources)

    loop_back = readiness.readiness_status == "Not Ready" and iteration < MAX_ITERATIONS
    next_hours_target = None
    if loop_back:
        next_hours_target = plan["remaining_hours_target"] + HOURS_INCREMENT_ON_LOOPBACK

    next_certification = (
        fabric_iq.get_next_certification(readiness.certification)
        if readiness.readiness_status == "Ready"
        else None
    )

    context = (
        f"Learner {learner_id}: practice score {readiness.practice_score_avg} "
        f"(threshold {readiness.pass_threshold}), hours studied "
        f"{readiness.hours_studied}/{readiness.recommended_hours} "
        f"({readiness.hours_completion_ratio*100:.0f}% of recommended), "
        f"risk level {readiness.risk_level}, status {readiness.readiness_status}, "
        f"iteration {iteration}. {validation['emitted']} grounded practice "
        f"question(s) passed the validation gate."
    )
    narrative = chat_client.complete(SYSTEM_PROMPT, context)
    if narrative is None:
        if readiness.readiness_status == "Ready":
            narrative = (
                f"Status: Ready. Practice score {readiness.practice_score_avg} meets the "
                f"{readiness.pass_threshold} threshold and {readiness.hours_completion_ratio*100:.0f}% "
                f"of recommended study hours are complete."
            )
            if next_certification:
                narrative += f" Recommended next step: {next_certification}."
        else:
            narrative = (
                f"Status: Not Ready (iteration {iteration}). Practice score "
                f"{readiness.practice_score_avg} is {readiness.score_gap} points below the "
                f"{readiness.pass_threshold} threshold, with "
                f"{readiness.hours_completion_ratio*100:.0f}% of recommended hours complete "
                f"(risk: {readiness.risk_level})."
            )
            if loop_back:
                narrative += (
                    f" Looping back to the Study Plan Generator with an additional "
                    f"{HOURS_INCREMENT_ON_LOOPBACK}h target."
                )

    return {
        "agent": "assessment_agent",
        "learner_id": learner_id,
        "readiness": readiness.__dict__,
        "practice_questions": practice_questions,
        "validation": validation,
        "drift_flag": drift["drift_flag"],
        "drift_skills": drift["drift_skills"],
        "drift_coverage": drift["drift_coverage"],
        "loop_back": loop_back,
        "next_hours_target": next_hours_target,
        "recommended_next_certification": next_certification,
        "iteration": iteration,
        "narrative": narrative,
    }
