"""
TalentFabric AI — Workflow Orchestrator

Implements the two architecture diagrams from the challenge:

  Diagram 1 (execution shape):
      Input -> Sequential Student Readiness Subworkflow (per learner)
            -> Assess & Aggregate team readiness results

  Diagram 2 (agent roster + IQ layer mapping):
      Learning Path Curator  -> Foundry IQ   (Fetch Resources)
      Study Plan Generator   -> Fabric IQ    (Optimize Plans)
      Engagement Agent       -> Work IQ      (Schedule Reminders)
      Assessment Agent       -> Foundry IQ + Fabric IQ (Generate & Evaluate)
      Manager Insights Agent -> Work IQ + Fabric IQ (Team Analytics)

Reasoning patterns demonstrated
--------------------------------
  - Role-based specialisation: each agent has one clear responsibility.
  - Planner-Executor: the Study Plan Generator plans milestones, then
    allocates (executes) hours across them.
  - Critic / Verifier: the Assessment Agent verifies readiness against
    Fabric IQ thresholds and can send the subworkflow back for another
    pass (loop-back), capped at MAX_ITERATIONS via the Assessment Agent's
    own guard -- this is the same "scope/loop guard" pattern used in the
    arXiv Agent project.
  - Fan-out / fan-in: each learner in a team runs the subworkflow
    independently (fan-out); the Manager Insights Agent then aggregates
    every learner's result (fan-in) into a single team report.

This module is the framework-agnostic "business logic" layer. See
src/agent_framework_workflow.py for how to wire these same functions
into a Microsoft Agent Framework Workflow graph backed by Microsoft
Foundry models.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from src.agents import (
    assessment_agent,
    engagement_agent,
    learning_path_curator,
    manager_insights_agent,
    study_plan_generator,
)
from src.agents.base import get_chat_client
from src.iq_layers.fabric_iq import FabricIQ
from src.iq_layers.foundry_iq import FoundryIQ
from src.iq_layers.work_iq import WorkIQ

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class TalentFabricWorkflow:
    def __init__(self):
        self.foundry_iq = FoundryIQ(DATA_DIR / "knowledge_base")
        self.work_iq = WorkIQ(DATA_DIR / "work_activity_signals.json")
        self.fabric_iq = FabricIQ(
            DATA_DIR / "fabric_iq_semantic_model.json", DATA_DIR / "learners.json"
        )
        self.chat_client = get_chat_client()

    # ------------------------------------------------------------------
    # Sequential Student Readiness Subworkflow (per learner)
    # ------------------------------------------------------------------
    def run_learner_subworkflow(self, learner_id: str) -> dict:
        learner = self.fabric_iq.get_learner(learner_id)
        employee_id = learner["employee_id"]

        # Learning Path Curator -> Foundry IQ. Runs ONCE, outside the loop: the
        # curator is deterministic and the Critic/Verifier loop re-plans, not
        # re-curates (matching the Agent Framework graph, which loops
        # assessment -> planner only). This also avoids redundant Learn MCP calls
        # on loop-back.
        curator_result = learning_path_curator.run(
            learner_id, self.foundry_iq, self.fabric_iq, self.chat_client
        )

        trace: List[dict] = [curator_result]
        iteration = 1
        plan_result = None
        assessment_result = None

        while True:
            # 1. Study Plan Generator -> Fabric IQ (Planner-Executor)
            target_hours_override = (
                assessment_result["next_hours_target"]
                if assessment_result and assessment_result.get("loop_back")
                else None
            )
            plan_result = study_plan_generator.run(
                learner_id,
                self.fabric_iq,
                self.chat_client,
                target_hours_override=target_hours_override,
                iteration=iteration,
                foundry_iq=self.foundry_iq,
            )
            trace.append(plan_result)

            # 2. Engagement Agent -> Work IQ
            engagement_result = engagement_agent.run(
                employee_id, plan_result["plan"], learner, self.work_iq, self.chat_client
            )
            trace.append(engagement_result)

            # 3. Assessment Agent -> Foundry IQ + Fabric IQ (Critic/Verifier)
            assessment_result = assessment_agent.run(
                learner_id,
                curator_result["resources"],
                plan_result["plan"],
                self.fabric_iq,
                self.chat_client,
                iteration=iteration,
                foundry_iq=self.foundry_iq,
            )
            trace.append(assessment_result)

            if not assessment_result["loop_back"]:
                break
            iteration += 1

        return {
            "learner_id": learner_id,
            "employee_id": employee_id,
            "role": learner["role"],
            "team_id": learner["team_id"],
            "trace": trace,
            "curator": curator_result,
            "plan": plan_result,
            "engagement": engagement_result,
            "assessment": assessment_result,
            "iterations": iteration,
        }

    # ------------------------------------------------------------------
    # Fan-out over learners, then "Assess & Aggregate team readiness"
    # ------------------------------------------------------------------
    def run_team(self, team_id: str) -> dict:
        learners = self.fabric_iq.list_learners(team_id)
        if not learners:
            raise ValueError(f"No learners found for team {team_id}")

        learner_results = [
            self.run_learner_subworkflow(learner["learner_id"]) for learner in learners
        ]

        manager_result = manager_insights_agent.run(
            team_id, learner_results, self.fabric_iq, self.chat_client, foundry_iq=self.foundry_iq
        )

        return {"team_id": team_id, "learner_results": learner_results, "manager_insights": manager_result}

    def run_all_teams(self) -> List[dict]:
        return [self.run_team(team_id) for team_id in self.fabric_iq.list_teams()]


def main():
    workflow = TalentFabricWorkflow()
    results = workflow.run_all_teams()

    out_path = Path(__file__).resolve().parent.parent / "run_output.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    for team_result in results:
        print(f"\n=== {team_result['team_id']} ===")
        print(team_result["manager_insights"]["narrative"])
        for lr in team_result["learner_results"]:
            print(
                f"  - {lr['learner_id']} ({lr['role']}): "
                f"{lr['assessment']['readiness']['readiness_status']} "
                f"(risk={lr['assessment']['readiness']['risk_level']}, "
                f"iterations={lr['iterations']})"
            )

    print(f"\nFull trace written to {out_path}")


if __name__ == "__main__":
    main()
