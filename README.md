<div align="center">

# 🧠 TalentFabric AI
### Enterprise Certification Readiness Platform

A five-agent reasoning system that turns a team of employees working toward Azure
certifications into **grounded study plans, workload-aware schedules, cited readiness
assessments, and privacy-conscious manager insights** — built on the Microsoft Agent
Framework and all three Microsoft IQ layers.

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Microsoft Agent Framework](https://img.shields.io/badge/Microsoft%20Agent%20Framework-1.8.1-0078D4?logo=microsoft&logoColor=white)](https://github.com/microsoft/agent-framework)
[![Microsoft Foundry](https://img.shields.io/badge/Microsoft%20Foundry-Azure%20OpenAI-0078D4?logo=microsoftazure&logoColor=white)](https://learn.microsoft.com/azure/ai-foundry/)
[![Microsoft IQ](https://img.shields.io/badge/Microsoft%20IQ-Foundry%20%C2%B7%20Fabric%20%C2%B7%20Work-5C2D91)](https://learn.microsoft.com/)
[![Learn MCP](https://img.shields.io/badge/Microsoft%20Learn-MCP%20Server-5C2D91?logo=microsoft&logoColor=white)](https://github.com/microsoftdocs/mcp)
[![Streamlit](https://img.shields.io/badge/UI-Streamlit%20%2B%20Plotly-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)

[![Data: Synthetic Only](https://img.shields.io/badge/Data-Synthetic%20Only-2EA043)](docs/ARCHITECTURE.md#6-synthetic-data)
[![Accessibility](https://img.shields.io/badge/Accessibility-WCAG%202.1%20AA-2EA043)](#-responsible-ai--reliability)
[![Tests](https://img.shields.io/badge/tests-passing-2EA043?logo=pytest&logoColor=white)](#-quick-start)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Agents League](https://img.shields.io/badge/Agents%20League-Reasoning%20Agents-blueviolet)](https://aka.ms/agentsleague)
[![Challenge A](https://img.shields.io/badge/Challenge%20A-Enterprise%20Learning%20System-0078D4)](#)

**Agents League Hackathon · Reasoning Agents track · Challenge A: Enterprise Learning System**

</div>

---

> [!IMPORTANT]
> **Synthetic data only.** All learners, employee IDs, certification performance data,
> calendar signals, and knowledge-base documents in this repository are fabricated for
> demonstration purposes. No real names, credentials, or organisational data are used.
> See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md#6-synthetic-data).

## Table of contents

- [Overview](#overview)
- [Data governance — two content categories](#data-governance--two-content-categories)
- [What it demonstrates](#what-it-demonstrates)
- [Quick start](#-quick-start)
- [Project layout](#project-layout)
- [Responsible AI & reliability](#-responsible-ai--reliability)
- [Deployment story](#-deployment-story)
- [Hackathon submission compliance](#-hackathon-submission-compliance)
- [Evaluation-criteria alignment](#-evaluation-criteria-alignment)
- [Compliance, disclaimer & licence](#-compliance-disclaimer--licence)

## Overview

TalentFabric AI helps an organisation manage internal certification programmes. For each
learner it runs a **Sequential Student Readiness Subworkflow** (curate → plan → engage →
assess, with a Critic/Verifier loop-back), fans that out across every learner on a team,
and fans the results in to a **Manager Insights** report. A cross-team comparison view
surfaces readiness gaps across the whole organisation at a glance.

```
        ┌──────────────────── per learner (fan-out) ────────────────────┐
Input → │  Learning Path Curator → Study Plan Generator → Engagement →   │ → Manager
(role,  │  Assessment ──(loop-back: not ready, max 2×)──► Study Plan      │   Insights
 cert)  └───────────────────────────────────────────────────────────────┘   (fan-in)
```

### Data governance — two content categories

The system distinguishes **two strictly separated categories** of content, so that an
optional public-knowledge integration never compromises the synthetic-only guarantee:

| Category | What it is | Where it lives | Rule |
|---|---|---|---|
| **Synthetic internal records** | Fabricated learners, employees, teams, work signals, certification ontology, internal KB docs | `data/` | 100 % synthetic. Public content is **never** written/merged/serialised here. |
| **Public knowledge corpus** | Official Microsoft Learn docs, retrieved live via the Microsoft Learn MCP Server | Retrieval/citation layer only (+ a gitignored disk cache) | Consumed only as cited, provenance-tagged retrieval results — never stored as or relabelled as organisational data. |

Every retrieved chunk carries a `source_tier` tag (`synthetic-internal` or
`microsoft-learn-public`) and, for public content, its source URL — both a reasoning
signal and a compliance audit trail. A single toggle, **`LEARN_MCP_ENABLED` (default
off)**, makes the whole system run on synthetic data only. The separation is enforced by
a guard (`src/iq_layers/provenance.py`) and covered by `tests/test_synthetic_separation.py`.

---

## What it demonstrates

### 5-Agent Pipeline

| Agent | IQ Grounding | Reasoning role |
|---|---|---|
| Learning Path Curator  | Foundry IQ             | Hybrid BM25 + TF-IDF retrieval; `source → section` citations on every resource |
| Study Plan Generator   | Fabric IQ              | **Planner-Executor**: derives milestones from cert ontology, then allocates remaining study hours |
| Engagement Agent       | Work IQ                | Workload-aware scheduling; adapts session length and slot to meeting load / focus time |
| Assessment Agent       | Foundry IQ + Fabric IQ | **Critic/Verifier**: verifies readiness vs. Fabric IQ threshold; loops back if not ready (cap `MAX_ITERATIONS = 2`) — and can flip Not Ready → Ready once the loop-back adds study hours |
| Manager Insights Agent | Work IQ + Fabric IQ    | Privacy-conscious **fan-in**: aggregates team readiness, skill gaps, and capacity flags — no individual scores exposed |

### Three Microsoft IQ Layers *(only one is required — all three are implemented)*

| IQ Layer | Local implementation | Production migration |
|---|---|---|
| **Foundry IQ** | Hybrid BM25 + TF-IDF retrieval over `data/knowledge_base/*.md`, fused with Microsoft Learn | Upload docs to a Foundry IQ knowledge source (Blob / SharePoint / OneLake); replace `FoundryIQ.query()` with the Foundry IQ agentic retrieval API |
| **Fabric IQ**  | JSON-backed certification ontology (learner, role, cert, skill, threshold, next-cert) | Replace with a Fabric IQ OneLake semantic model; same return shapes |
| **Work IQ**    | Synthetic workplace signals JSON (meeting load, focus time, slot) | Replace with the Work IQ API (Microsoft 365 tenant data via Graph) |

### Microsoft Agent Framework

`src/agent_framework_workflow.py` is a real `WorkflowBuilder` graph (tested against
`agent-framework-core` / `agent-framework-openai` 1.8.1):

- a per-learner subworkflow with `add_edge(assessment, planner, condition=lambda s: s["loop_back"])`
  for the Critic/Verifier loop-back;
- a team-level fan-out/fan-in graph (`add_fan_out_edges` / `add_fan_in_edges`).

A framework-agnostic twin (`src/workflow.py`) runs the identical agent logic for the eval
harness and CLI.

### Microsoft Learn MCP integration *(external tool, where it adds real value)*

The Microsoft Learn MCP Server is integrated as a public knowledge layer fused into
Foundry IQ retrieval (`src/iq_layers/learn_mcp.py`): a resilient streamable-HTTP client
with runtime tool discovery, a 24h disk cache, a loop-aware sync facade, and a three-tier
fallback (Learn → synthetic KB → empty-but-valid) so it **never breaks the offline demo**.
It grounds the Curator (cited resources), the Assessment Agent (corrective-RAG), the Study
Plan Generator (Learn modules), and Manager Insights (next-cert path).

### Evaluation & telemetry

`src/eval/run_eval.py` scores readiness-classification accuracy, risk-level accuracy,
citation-grounding rate, average loop-back iterations, authoritative-grounding rate, and
citation validity against a ground-truth set — logged as an MLflow run when MLflow is
installed. The Streamlit **MCP Telemetry** page surfaces call counts, cache-hit rate,
latency, provenance mix, and groundedness-by-source live.

### LLM narration *(graceful, never-crash fallback chain)*

| Priority | Backend | Config |
|---|---|---|
| 1 | Microsoft Foundry / Azure OpenAI | `AZURE_OPENAI_ENDPOINT` + `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_DEPLOYMENT` |
| 2 | GitHub Models (free, no quota)   | `GITHUB_MODELS_TOKEN` + `GITHUB_MODELS_MODEL` |
| 3 | Deterministic templated narration | *(always-on offline fallback — no keys required)* |

The grounded reasoning (retrieval, readiness scoring, scheduling, loop-back, aggregation)
is identical regardless of backend — only the natural-language narration changes.

---

## 🚀 Quick start

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

| Command | What it does |
|---|---|
| `python -m src.workflow` | Framework-agnostic pipeline for every team → `run_output.json` |
| `python -m src.agent_framework_workflow` | Same logic as a real Agent Framework graph → `run_output_agent_framework.json` |
| `python -m src.eval.run_eval` | Evaluation harness (+ MLflow) → `eval_results.json` |
| `streamlit run app/streamlit_app.py` | Interactive 6-page demo *(recommended)* |

```bash
# Tests
pip install -r requirements-dev.txt
pytest -q          # default: network-free, deterministic (mocked MCP transport)
pytest -m live     # opt-in: hits the real Microsoft Learn MCP endpoint (needs network)
python scripts/smoke_test_learn_mcp.py   # opt-in live smoke test of all three MCP tools
```

The six Streamlit pages: **Overview** (pipeline + IQ/reasoning explainers), **Learner
Analysis** (per-learner subworkflow, readiness gauges, milestone chart, cited 5-type
practice questions, validation gate), **Manager Dashboard** (KPIs, colour-blind-safe
charts, privacy-safe per-learner table, CSV export), **Team Comparison** (cross-team
charts + CSV), **MCP Telemetry** (status console), and **About** (rosters + migration
path + disclaimers).

### Enable LLM narration (optional)

```bash
cp .env.example .env
```

**Option A — Microsoft Foundry / Azure OpenAI** (needs a model deployment in your Foundry
project's *Models + Endpoints*):

```env
AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com/openai/v1
AZURE_OPENAI_API_KEY=<your-key>
AZURE_OPENAI_DEPLOYMENT=gpt-4o
```

**Option B — GitHub Models** (free, no Azure quota required):

```env
GITHUB_MODELS_TOKEN=<a GitHub PAT with the models:read permission>
GITHUB_MODELS_MODEL=openai/gpt-4o-mini
```

Either falls back to templated narration automatically on any error (auth, network, rate
limit), so the system never crashes due to LLM unavailability.

---

## Project layout

```
data/
  learners.json                  # 12 synthetic learners, 3 teams, 4 roles (Fabric IQ)
  work_activity_signals.json     # 12 synthetic workplace signal records (Work IQ)
  fabric_iq_semantic_model.json  # Certification ontology: skills, hours, thresholds, next-cert (Fabric IQ)
  knowledge_base/*.md            # Synthetic cert guides + team/workload reports (Foundry IQ)
src/
  config.py                      # LEARN_MCP_ENABLED toggle + MCP settings
  iq_layers/
    foundry_iq.py                # Hybrid BM25 + TF-IDF retrieval, fused with Learn (Foundry IQ stand-in)
    fabric_iq.py                 # Cert ontology + readiness scoring (Fabric IQ stand-in)
    work_iq.py                   # Workplace signal context layer (Work IQ stand-in)
    learn_mcp.py                 # Resilient Microsoft Learn MCP client (cache, retry, telemetry)
    provenance.py                # Two-tier provenance type + synthetic/public write-guard
  agents/                        # The five agents + shared chat client (base.py)
  workflow.py                    # Framework-agnostic orchestration (TalentFabricWorkflow)
  agent_framework_workflow.py    # Microsoft Agent Framework WorkflowBuilder implementation
  eval/                          # Evaluation harness + ground-truth set
app/
  streamlit_app.py               # Interactive demo: 6 pages, Plotly charts, CSV export, WCAG AA
  ui/                            # Fluent 2 design system: theme, components, vendored Inter + Fluent icons
docs/
  ARCHITECTURE.md                # Full architecture, IQ-layer mapping, production migration path
tests/                           # Synthetic-separation, MCP client, hybrid retrieval, corrective-RAG, grounding
scripts/
  smoke_test_learn_mcp.py        # Opt-in live MCP endpoint check
```

---

## 🛡️ Responsible AI & reliability

- **Synthetic-only + provenance guard** — a write-guard blocks public content from ever
  entering `data/`; every chunk is tier-tagged and audit-traceable.
- **Privacy-conscious aggregation** — Manager Insights never exposes individual practice
  scores (enforced by test).
- **Graceful degradation** — LLM and MCP both fall back without crashing; the full demo
  runs offline with no keys and no network.
- **Bounded reasoning** — the Critic/Verifier loop-back is capped (`MAX_ITERATIONS = 2`).
- **Output validation** — a deterministic groundedness gate drops/regenerates ungrounded
  practice questions; non-fatal skill-drift detection is surfaced for transparency.
- **Accessibility** — WCAG 2.1 AA contrast, colour-blind-safe charts (patterns + labels,
  not colour alone), ARIA on custom HTML, `prefers-reduced-motion` respected.

## 🌐 Deployment story

The Agent Framework workflow containerises and deploys as a **Hosted Agent in Foundry
Agent Service**, with the entry agent handling orchestration/routing and the IQ layers as
grounding backends. Each local stand-in maps to its managed service (Foundry IQ knowledge
source + Microsoft Learn MCP, Fabric IQ OneLake semantic model, Work IQ via Microsoft 365
Graph) with **unchanged agent code** — see
[`docs/ARCHITECTURE.md` §7](docs/ARCHITECTURE.md).

---

## ✅ Hackathon submission compliance

| Submission requirement | Status | Where |
|---|---|---|
| Multi-agent system aligned to the challenge scenario | ✅ | Five agents, Enterprise Learning System |
| Use Microsoft Foundry and/or the Microsoft Agent Framework | ✅ | `src/agent_framework_workflow.py` (`WorkflowBuilder`) + Foundry/Azure OpenAI narration |
| Reasoning & multi-step decision-making across agents | ✅ | Planner-Executor, Critic/Verifier loop-back (flips outcomes), fan-out/fan-in, corrective-RAG |
| Integrate external tools / APIs / MCP where they add value | ✅ | Microsoft Learn MCP fused into grounded retrieval, gated + cached + resilient |
| Integrate at least one Microsoft IQ layer | ✅ | **All three** — Foundry IQ, Fabric IQ, Work IQ |
| Synthetic data and documents only | ✅ | `data/` 100 % synthetic; provenance guard + separation test |
| Demoable + clear explanation of agent interactions | ✅ | 6-page Streamlit UI + two CLI entry points |
| Documentation of responsibilities, orchestration, tools, data | ✅ | This README + [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |

> The solution aligns to the challenge scenario; per the brief it does **not** follow the
> suggested architecture node-for-node (e.g. retrieval is grounded on the role→certification
> ontology rather than free-text topics) — these are deliberate, grounded design choices.

**Highly valued extras — all present:** evaluation/telemetry/observability (eval harness +
MLflow + live MCP telemetry panel) · advanced reasoning patterns (corrective-RAG, bounded
loop-back, drift detection) · Responsible AI controls & fallbacks (provenance guard,
three-tier retrieval fallback, LLM fallback chain) · a clear hosted deployment story.

## 📊 Evaluation-criteria alignment

| Criterion | Weight | How this project addresses it |
|---|---|---|
| Accuracy & Relevance | 25% | Grounded, cited retrieval; eval harness reports 1.0 readiness/risk accuracy on the ground-truth set |
| Reasoning & Multi-step Thinking | 25% | Planner-Executor + Critic/Verifier loop-back (visibly flips Not Ready → Ready) + fan-out/fan-in + corrective-RAG |
| Creativity & Originality | 15% | Two-tier provenance/compliance model; hybrid synthetic + Microsoft Learn grounding with a default-off toggle |
| User Experience & Presentation | 15% | Fluent 2 / Microsoft Learn-styled, WCAG AA, 6-page demo with live telemetry and CSV export |
| Reliability & Safety | 20% | Synthetic-only guard, privacy-safe aggregation, graceful LLM/MCP fallbacks, bounded loops, test coverage |

---

## 📜 Compliance, disclaimer & licence

- **Disclaimer** — read the [Agents League Disclaimer](https://aka.ms/AgentsLeague_Disclaimer).
  No confidential information is present in this repository.
- **Code of Conduct** — [Agents League Code of Conduct](https://aka.ms/AgentsLeagueCodeofConduct).
- **Submission deadline** — June 14, 2026. This repository is **public** and includes this README.
- **Independent submission** — not affiliated with or endorsed by Microsoft. "Microsoft
  Learn", "Microsoft Foundry", "Azure", and "Fluent" are referenced nominatively only.
  Fluent UI System Icons are used under the MIT License; the Inter font under the SIL OFL.
- **Licence** — [MIT](LICENSE).
