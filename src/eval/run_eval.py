"""
TalentFabric AI — Evaluation harness for the multi-agent workflow.

Measures:
  1. Readiness accuracy: does the Assessment Agent's readiness_status /
     risk_level match the expected values derived from the Fabric IQ
     ontology (data/eval/eval_set.json)?
  2. Citation grounding rate: what fraction of the Learning Path Curator's
     citations come from the certification-specific knowledge base
     document (i.e. are correctly grounded for that learner's target
     certification)?
  3. Average iterations: how often the Critic/Verifier loop-back fires.

This mirrors the benchmarking approach used for the arXiv Agent project
(retrieval quality + answer relevance metrics), adapted to this challenge's
grounded, multi-agent setting.

If MLflow is installed, metrics are also logged as an MLflow run for
observability / telemetry (a "highly valued extra" per the rubric). If not
installed, metrics are printed and written to eval_results.json.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlparse

from src.workflow import TalentFabricWorkflow

EVAL_SET_PATH = Path(__file__).resolve().parent / "eval_set.json"
RESULTS_PATH = Path(__file__).resolve().parent.parent.parent / "eval_results.json"


def _structurally_valid_learn_url(url: str) -> bool:
    """A well-formed https Microsoft (Learn) URL."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme == "https" and parsed.netloc.endswith("microsoft.com")


def _live_url_ok(url: str) -> bool:
    """Best-effort live 200 check (only used when EVAL_LIVE_URL_CHECK is set)."""
    try:
        import requests

        resp = requests.head(url, timeout=5, allow_redirects=True)
        return resp.status_code == 200
    except Exception:  # noqa: BLE001 - network/optional dep failures are non-fatal
        return False


def run_evaluation() -> dict:
    with open(EVAL_SET_PATH, "r", encoding="utf-8") as f:
        eval_set = json.load(f)

    workflow = TalentFabricWorkflow()

    total = len(eval_set)
    status_correct = 0
    risk_correct = 0
    total_iterations = 0
    citation_total = 0
    citation_correct = 0

    # Authoritative-grounding metrics (Microsoft Learn public citations).
    resource_total = 0
    learn_citation_total = 0
    url_total = 0
    url_valid = 0
    live_url_check = bool(os.getenv("EVAL_LIVE_URL_CHECK"))

    per_learner = []

    for case in eval_set:
        learner_id = case["learner_id"]
        result = workflow.run_learner_subworkflow(learner_id)

        readiness = result["assessment"]["readiness"]
        status_match = readiness["readiness_status"] == case["expected_readiness_status"]
        risk_match = readiness["risk_level"] == case["expected_risk_level"]
        status_correct += int(status_match)
        risk_correct += int(risk_match)
        total_iterations += result["iterations"]

        # citation_grounding_rate measures grounding to the learner's synthetic
        # cert guide, so it is computed over SYNTHETIC-tier citations only —
        # public Microsoft Learn citations (covered by authoritative_grounding_rate
        # below) would otherwise dilute it under MCP-on.
        cert_doc = readiness["certification"].replace("-", "").lower() + "_guide"
        synthetic_res = [
            r for r in result["curator"]["resources"]
            if r.get("source_tier", "synthetic-internal") == "synthetic-internal"
        ]
        matched = [r for r in synthetic_res if r["source"].startswith(cert_doc)]
        citation_total += len(synthetic_res)
        citation_correct += len(matched)

        # Authoritative grounding: fraction of cited resources that resolve to a
        # public Microsoft Learn URL, and whether those URLs are valid.
        for res in result["curator"]["resources"]:
            resource_total += 1
            url = res.get("source_url")
            if res.get("source_tier") == "microsoft-learn-public":
                learn_citation_total += 1
            if url:
                url_total += 1
                ok = _live_url_ok(url) if live_url_check else _structurally_valid_learn_url(url)
                url_valid += int(ok)

        per_learner.append(
            {
                "learner_id": learner_id,
                "expected_status": case["expected_readiness_status"],
                "actual_status": readiness["readiness_status"],
                "status_match": status_match,
                "expected_risk": case["expected_risk_level"],
                "actual_risk": readiness["risk_level"],
                "risk_match": risk_match,
                "iterations": result["iterations"],
                "citation_grounding_rate": round(len(matched) / len(synthetic_res), 2) if synthetic_res else 0.0,
            }
        )

    metrics = {
        "n_cases": total,
        "readiness_status_accuracy": round(status_correct / total, 3),
        "risk_level_accuracy": round(risk_correct / total, 3),
        "avg_iterations": round(total_iterations / total, 2),
        # Synthetic-tier only (grounding to the cert guide); Learn side is the
        # authoritative_grounding_rate below.
        "citation_grounding_rate": round(citation_correct / citation_total, 3) if citation_total else 0.0,
        # Fraction of cited resources grounded in public Microsoft Learn content
        # (0.0 when the Learn MCP toggle is off — synthetic-only, by design).
        "authoritative_grounding_rate": round(learn_citation_total / resource_total, 3) if resource_total else 0.0,
        # Fraction of citation URLs that are valid. Structural by default;
        # live (HTTP 200) when EVAL_LIVE_URL_CHECK is set. Vacuously 1.0 when
        # there are no URLs (off-path).
        "citation_validity": round(url_valid / url_total, 3) if url_total else 1.0,
        "learn_citations": learn_citation_total,
        "live_url_check": live_url_check,
    }

    output = {"metrics": metrics, "per_learner": per_learner}

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    _log_to_mlflow(metrics)

    print(json.dumps(metrics, indent=2))
    print(f"\nPer-learner detail written to {RESULTS_PATH}")
    return output


def _log_to_mlflow(metrics: dict) -> None:
    try:
        import mlflow
    except ImportError:
        print("(mlflow not installed -- skipping experiment tracking)")
        return

    mlflow.set_experiment("teamready-agent-eval")
    with mlflow.start_run(run_name="readiness-eval"):
        for key, value in metrics.items():
            if isinstance(value, (int, float)):
                mlflow.log_metric(key, value)
        mlflow.log_artifact(str(RESULTS_PATH))


if __name__ == "__main__":
    run_evaluation()
