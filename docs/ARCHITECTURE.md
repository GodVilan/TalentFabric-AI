# TalentFabric AI — Architecture

## 1. Scenario

TalentFabric AI is a multi-agent enterprise learning system (Challenge A:
Enterprise Learning System) that helps a manager understand certification
readiness across their team, while giving each learner a grounded,
workload-aware study plan.

All data is synthetic. See [Synthetic Data](#6-synthetic-data) below.

## 2. Architecture diagrams

### 2.1 Execution shape

```
Input  -->  Sequential Student Readiness Subworkflow  -->  Assess & Aggregate
            (run once per learner, fan-out)               team readiness results
                                                            (fan-in, Manager Insights)
```

### 2.2 Agent roster and IQ layer mapping

```
                 User                                  Manager
                  |                                       |
                  v                                       v
        +-------------------------------------------------------------+
        |              Enterprise Learning & Optimization System       |
        |  --------------------- Multi-Agent Orchestration ----------- |
        |  [Learning Path  ]->[Study Plan   ]->[Engagement]->[Assessment]->[Manager Insights]
        |  [Curator        ]  [Generator    ]  [Agent     ]  [Agent     ]  [Agent           ]
        |  Fetch Resources    Optimize Plans   Schedule       Generate &    Team Analytics
        |                                      Reminders      Evaluate
        +----------------------^-------^------------^-------------^----------------^-------+
                                |       |            |             |                |
                          +-----+-------+------------+-------------+----------------+-----+
                          |   Foundry IQ        Fabric IQ        Work IQ                   |
                          |  (Knowledge        (Performance      (Workplace               |
                          |   Retrieval,        Analytics,        Signals,                |
                          |   Training Docs)    Learner Data)     Calendar Data)          |
                          +-----------------------------------------------------------------+
                                                     |
                                        Outputs: Assessments, Reports
```

This repository implements the diagram directly:

| Diagram element | Module |
|---|---|
| Learning Path Curator | `src/agents/learning_path_curator.py` |
| Study Plan Generator | `src/agents/study_plan_generator.py` |
| Engagement Agent | `src/agents/engagement_agent.py` |
| Assessment Agent | `src/agents/assessment_agent.py` |
| Manager Insights Agent | `src/agents/manager_insights_agent.py` |
| Foundry IQ | `src/iq_layers/foundry_iq.py` + `data/knowledge_base/*.md` |
| Fabric IQ | `src/iq_layers/fabric_iq.py` + `data/fabric_iq_semantic_model.json` + `data/learners.json` |
| Work IQ | `src/iq_layers/work_iq.py` + `data/work_activity_signals.json` |
| Orchestration (both diagrams) | `src/workflow.py` (`TalentFabricWorkflow`) and `src/agent_framework_workflow.py` (Agent Framework `WorkflowBuilder`) |

## 3. IQ layer implementation pattern (as specified in the starter kit)

**Work IQ** -> context layer for the Engagement Agent and planning logic.
Work signals (meeting hours, focus hours, collaboration load) are treated
as contextual inputs that drive study-window, session-length, and
escalation (capacity_flag) decisions. Outputs are framed supportively
("recommended session length / slot") rather than exposing raw calendar
data. See `WorkIQ.recommend_study_window`.

**Foundry IQ** -> grounded knowledge layer for the Learning Path Curator
and Assessment Agent. A knowledge base is built from synthetic guidance
docs in `data/knowledge_base/*.md` (certification guides + team/workload
reports). Agents query this knowledge base via hybrid BM25 + TF-IDF
retrieval and must cite `source -> section` for every resource and
practice question. See `FoundryIQ.query` and
`learning_path_curator.run` / `assessment_agent._generate_and_validate`
(which builds typed questions via `_resource_to_question`). When
`LEARN_MCP_ENABLED` is on, `FoundryIQ.query` additionally fuses these local
results with public Microsoft Learn content via reciprocal-rank fusion
(see §7), tagging each result with its provenance tier.

**Fabric IQ** -> semantic layer for business meaning and structured
decision support, used by the Study Plan Generator, Assessment Agent, and
Manager Insights Agent. The ontology in
`data/fabric_iq_semantic_model.json` models Learner, Role, Certification,
Skill, RecommendedHours, PassThreshold, and the `next_certification`
relationship (prerequisites / role alignment / pass thresholds). See
`FabricIQ.compute_readiness`, `FabricIQ.get_certification`,
`FabricIQ.skill_gap_summary`.

## 4. Reasoning patterns

- **Role-based specialisation** - each of the five agents has one clear
  responsibility and one primary IQ grounding source, matching the
  "Suggested Implementation Pattern" table in the starter kit. The Learning
  Path Curator is deterministic and runs **once** per learner, outside the
  loop-back loop (the loop re-plans, not re-curates).
- **Planner-Executor** - the Study Plan Generator first *plans* milestones
  (one per required skill, from the Fabric IQ ontology), then *executes*
  by allocating the remaining study-hour budget across those milestones.
- **Critic / Verifier (with effective loop-back)** - the Assessment Agent
  verifies readiness against Fabric IQ thresholds and either confirms
  readiness (with a `next_certification` recommendation) or sends the
  subworkflow back to the Study Plan Generator with an adjusted hours target.
  Crucially, the loop-back *changes outcomes*: `compute_readiness` is
  re-evaluated against the post-loop-back hours
  (`extra_hours = (iteration - 1) * HOURS_INCREMENT_ON_LOOPBACK`), so an
  hours-limited learner flips Not Ready -> Ready on a later iteration while a
  below-threshold learner correctly stays Not Ready.
- **Corrective-RAG + output-validation gate** - the Assessment Agent generates
  five typed, cited practice questions (Conceptual / Applied / Scenario /
  Evaluative / Comparative), then runs a *deterministic* groundedness gate
  (term-overlap between each question and its cited chunk; no LLM, so it is
  reproducible and assertable). A question that fails the gate triggers a
  single corrective re-retrieval before being dropped — separate from, and
  prior to, the readiness loop-back budget. See `_generate_and_validate`,
  `groundedness_score`, `GROUNDEDNESS_THRESHOLD` / `MIN_SNIPPET_TERMS`.
- **Drift detection** - `_detect_drift` reports a coverage ratio of the
  certification's ontology skills against the cited passages and flags drift
  only when coverage falls below `DRIFT_COVERAGE_MIN` — a discriminating,
  non-fatal signal surfaced in the trace and the UI.
- **Loop guard** - the loop-back is capped at `MAX_ITERATIONS = 2`
  (`src/agents/assessment_agent.py`), preventing runaway iteration.
- **Fan-out / fan-in** - `TalentFabricWorkflow.run_team` fans the per-learner
  subworkflow out across every learner on a team, then fans the results in
  to the Manager Insights Agent for aggregation.

## 5. Responsible AI / reliability

- **Citations required**: the Learning Path Curator and Assessment Agent
  return `source -> section` citations for every resource and practice
  question; nothing is presented as fact without a citation.
- **Privacy-conscious aggregation**: the Manager Insights Agent's report
  (`manager_insights_agent.run`) deliberately excludes individual practice
  scores -- only readiness status, risk level, capacity flags, and
  aggregate skill gaps are surfaced, per the starter kit's requirement to
  "present insights without exposing sensitive personal data."
- **Bounded iteration**: the Critic/Verifier loop is capped to prevent
  runaway re-planning.
- **Output validation**: every emitted practice question must pass the
  deterministic groundedness gate (§4); ungrounded questions are corrected or
  dropped, satisfying the "validate generated outputs" requirement and acting
  as a leakage check.
- **Content-separation guard**: a provenance write-guard
  (`assert_not_public`, `src/iq_layers/provenance.py`) prevents public Microsoft
  Learn content from ever being persisted into the synthetic `data/` records
  (see §6.1).
- **Transparency**: all output is generated by a templated/LLM narrative
  layer that is explicitly labelled per-agent in the Streamlit UI, and the
  README states clearly that all data is synthetic and AI-generated.
- **Graceful degradation**: the system runs fully offline (deterministic
  templated narration) if no LLM credentials are configured, and upgrades
  automatically to Foundry/Azure OpenAI-generated narration when
  `AZURE_OPENAI_*` environment variables are present (`src/agents/base.py`).
  The Microsoft Learn MCP integration has its own three-tier fallback
  (Learn -> synthetic KB -> empty-but-valid) and never breaks the offline path.
- **Accessibility**: the Streamlit UI targets WCAG 2.1 AA — contrast-checked
  tokens, status conveyed by text + icon (not colour alone), colour-blind-safe
  charts (patterns + labels), ARIA on custom HTML, and `prefers-reduced-motion`.

## 6. Synthetic data

All data under `data/` is fabricated for this hackathon:

- `data/learners.json` - 12 synthetic learners (`L-1001`...`L-1012`) across
  4 roles and 3 teams (`TEAM-A`/`TEAM-B`/`TEAM-C`), modelled on the example
  schema in the starter kit.
- `data/work_activity_signals.json` - synthetic per-employee workplace
  signals (`EMP-001`...`EMP-012`).
- `data/fabric_iq_semantic_model.json` - the certification ontology
  (skills, recommended hours, prerequisites, pass thresholds, next-cert
  relationships).
- `data/knowledge_base/*.md` - synthetic certification guides and
  team/workload reports used as the Foundry IQ knowledge base.

No real names, emails, credentials, or organisational data are used
anywhere in this repository.

### 6.1 Compliance & content separation (two-category model)

The optional Microsoft Learn MCP integration introduces a second content
category — public Microsoft Learn docs — alongside the synthetic internal
records. These two categories are kept strictly separated:

| Category | `source_tier` | Lives in | Rule |
|---|---|---|---|
| Synthetic internal records | `synthetic-internal` | `data/` | 100 % synthetic; public content is never written/merged/serialised here |
| Public Microsoft Learn corpus | `microsoft-learn-public` | Retrieval/citation layer + gitignored `.cache/learn_mcp/` | Consumed only as cited, provenance-tagged retrieval results; never persisted as org data |

Enforcement:

- **Provenance type** (`src/iq_layers/provenance.py`): every retrieved chunk
  carries a `source_tier` and, for public content, a `source_url`.
- **Write guard** (`assert_not_public`): any code path serialising into `data/`
  rejects `microsoft-learn-public` content, raising `ProvenanceViolationError`.
- **Toggle** (`LEARN_MCP_ENABLED`, default off; `src/config.py`): with it off
  the system runs synthetic-only, fully functional. It is the compliance
  backbone.
- **Tests** (`tests/test_synthetic_separation.py`): assert synthetic-shaped
  identifiers, that the synthetic record loaders never import the MCP client,
  and that the write guard rejects public content.

No secrets are involved — the Learn MCP endpoint is public and unauthenticated;
`.env` stays gitignored and only `.env.example` is tracked.

## 7. Production migration path

- **Foundry IQ**: upload `data/knowledge_base/*.md` to a Foundry IQ
  knowledge source (Blob Storage / SharePoint / OneLake) and replace
  `FoundryIQ.query` with the Foundry IQ agentic retrieval API, keeping the
  same `(source, section, text, score)` return shape. For higher retrieval
  quality, swap the TF-IDF vectorizer for BGE-large-en embeddings + FAISS
  (as used in the author's arXiv Agent project) while keeping the BM25
  hybrid scoring.
- **Work IQ**: replace `WorkIQ._signals` with calls to the Work IQ API,
  which derives meeting load / focus time / collaboration signals from
  Microsoft 365 tenant data.
- **Fabric IQ**: replace the JSON-backed `FabricIQ` with queries against a
  Fabric ontology / OneLake semantic model with the same entities and
  relationships.
- **Orchestration**: `src/agent_framework_workflow.py` is a real
  `agent_framework.WorkflowBuilder` implementation (tested against
  `agent-framework-core`/`agent-framework-openai` 1.8.1). It builds:
  - a per-learner subworkflow graph -- curator -> planner -> engagement ->
    assessment, with a conditional `add_edge(assessment, planner,
    condition=lambda s: s["loop_back"])` implementing the Critic/Verifier
    loop-back; and
  - a team-level graph -- a dispatcher fans out to four
    `LearnerRunnerExecutor`s (one per learner on the team, each running its
    own nested per-learner subworkflow), which fan in to the
    `ManagerInsightsExecutor` for aggregation.

  This is a direct, working implementation of both architecture diagrams
  using Agent Framework's `WorkflowBuilder`, `add_edge` (with `condition`),
  `add_fan_out_edges`, and `add_fan_in_edges`. `src/workflow.py` remains as
  a framework-agnostic equivalent (useful for the eval harness and as a
  reference), producing identical results.
- **Model backend**: `src/agents/base.py` selects the best available
  narration backend at runtime: Azure OpenAI / Microsoft Foundry
  (`AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_API_KEY` / `AZURE_OPENAI_DEPLOYMENT`,
  if a model deployment with quota is available), then GitHub Models
  (`GITHUB_MODELS_TOKEN` / `GITHUB_MODELS_MODEL`) as a free, no-quota
  fallback explicitly permitted by the starter kit ("Microsoft
  Foundry-hosted, GitHub-hosted, or locally-hosted models"), then templated
  narration. Any backend falls back automatically on error, so the system
  never crashes due to LLM unavailability. Note that the "Use ... Microsoft
  Agent Framework" requirement is satisfied independently of this choice by
  `src/agent_framework_workflow.py`'s `WorkflowBuilder` graph.
- **Hosting**: the resulting Agent Framework workflow can be containerised
  and deployed as a Hosted Agent in Foundry Agent Service, with the entry
  agent handling orchestration/routing and the IQ layers as the grounding
  backends, per the starter kit's "Suggested Hosted Agent Deployment
  Pattern."
- **Microsoft Learn MCP Server (implemented)**: the system integrates the
  Microsoft Learn MCP Server (`learn.microsoft.com/api/mcp`) as a public
  knowledge layer fused into `FoundryIQ.query()` via reciprocal-rank fusion
  (`src/iq_layers/learn_mcp.py` + `foundry_iq.py`). It grounds the Learning
  Path Curator (cited resources), the Assessment Agent (corrective-RAG on
  practice questions), the Study Plan Generator (Learn module decomposition),
  and the Manager Insights Agent (grounded next-certification path). It is
  gated behind `LEARN_MCP_ENABLED` (default off) and degrades cleanly to the
  synthetic KB on any failure (three-tier fallback). For production, the same
  `RetrievedChunk` provenance contract maps onto a Foundry IQ knowledge source
  with Microsoft Learn attached as an additional knowledge source on a
  Foundry-hosted agent — the agent code above the retrieval layer is unchanged,
  and the two-category compliance model (§6.1) carries over directly (public
  Learn content stays in the retrieval/citation layer; synthetic org data stays
  in the tenant store).

### 7.1 Evaluation & monitoring

- **Eval metrics** (`src/eval/run_eval.py`): in addition to readiness/risk
  accuracy and citation grounding, the harness reports *authoritative grounding
  rate* (fraction of cited resources resolving to public Microsoft Learn URLs)
  and *citation validity* (URL well-formedness; structural by default, live
  HTTP 200 when `EVAL_LIVE_URL_CHECK` is set). All metrics are logged to MLflow.
- **Telemetry** (`src/iq_layers/learn_mcp.py` `get_telemetry()` + the Streamlit
  "MCP Telemetry" page): process-wide MCP call counts, cache-hit rate, latency,
  and error/degradation counts, plus per-tier provenance mix and groundedness —
  the "visualisation and monitoring" the challenge encourages.
- **Live verification**: `pytest -m live` and `scripts/smoke_test_learn_mcp.py`
  exercise the real endpoint (network required); the default test suite is
  fully mocked and network-free.
