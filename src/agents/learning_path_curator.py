"""
Learning Path Curator Agent

Role (per the suggested architecture):
    "Suggest relevant learning paths and supporting material.
     Recommended grounding: Foundry IQ knowledge base connected to approved
     learning content. Map a certification target to relevant skills and
     resources. Return cited content rather than unsupported free-text
     recommendations."

This agent queries the Foundry IQ layer for content relevant to the
learner's role and target certification, and returns a cited resource list
that downstream agents (Study Plan Generator, Assessment Agent) build on.
"""

from __future__ import annotations

from typing import List

from src.agents.base import ChatClient
from src.iq_layers.fabric_iq import FabricIQ
from src.iq_layers.foundry_iq import FoundryIQ, RetrievalResult

SYSTEM_PROMPT = (
    "You are the Learning Path Curator Agent in an enterprise certification "
    "readiness system. Summarise the retrieved, cited resources for the "
    "learner in 2-3 sentences. Only describe what is in the provided "
    "context; do not invent resources."
)


def run(
    learner_id: str,
    foundry_iq: FoundryIQ,
    fabric_iq: FabricIQ,
    chat_client: ChatClient,
    top_k: int = 3,
) -> dict:
    learner = fabric_iq.get_learner(learner_id)
    role = learner["role"]
    target_cert = learner["target_certification"]

    query = f"{target_cert} {role} certification study guide skills recommended study pattern"
    cert_doc = target_cert.replace("-", "").lower() + "_guide"
    results: List[RetrievalResult] = foundry_iq.query(
        query, top_k=top_k, boost_sources=[cert_doc], boost_amount=1.0
    )

    citations = [r.citation() for r in results]
    resources = [
        {
            "source": r.source,
            "section": r.section,
            "snippet": r.text[:240],
            "text": r.text,
            "score": r.score,
            "source_tier": r.source_tier,
            "source_url": r.source_url,
        }
        for r in results
    ]

    # Provenance mix across the retrieved set (synthetic KB vs public Learn).
    n_public = sum(1 for r in results if r.source_tier == "microsoft-learn-public")
    n_synthetic = len(results) - n_public
    if n_public:
        provenance_note = (
            f" Grounding spans {n_synthetic} internal source(s) and "
            f"{n_public} public Microsoft Learn source(s)."
        )
    else:
        provenance_note = ""

    context = (
        f"Learner {learner_id} ({role}) is targeting {target_cert}. "
        f"Retrieved sections: " + "; ".join(citations) + provenance_note
    )
    narrative = chat_client.complete(SYSTEM_PROMPT, context)
    if narrative is None:
        narrative = (
            f"For {target_cert} ({role}), the curator grounded its recommendation in "
            f"{len(results)} cited sections: {', '.join(citations)}." + provenance_note
        )

    return {
        "agent": "learning_path_curator",
        "learner_id": learner_id,
        "target_certification": target_cert,
        "resources": resources,
        "citations": citations,
        "provenance": {"synthetic_internal": n_synthetic, "microsoft_learn_public": n_public},
        "narrative": narrative,
    }
