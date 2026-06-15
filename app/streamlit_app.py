"""
TalentFabric AI — Enterprise Certification Intelligence Platform

Five-agent reasoning system for Azure certification readiness.
Demonstrates Microsoft Foundry IQ, Fabric IQ, and Work IQ integration with
multi-agent orchestration via the Microsoft Agent Framework.

Run with:
    streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import io
import sys
from html import escape
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

_APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_APP_DIR.parent))  # project root, for `src.*`
sys.path.insert(0, str(_APP_DIR))         # app dir, for the `ui` design-system package

from src.config import get_learn_mcp_config  # noqa: E402
from src.iq_layers import learn_mcp  # noqa: E402
from src.workflow import TalentFabricWorkflow  # noqa: E402
from ui.theme import (  # noqa: E402
    inject_css,
    risk_color,
    ACCENT_SUBTLE,
    AZURE_BLUE,
    AZURE_CYAN,
    BORDER_SUBTLE,
    DANGER,
    DANGER_SUBTLE,
    PURPLE,
    SUCCESS,
    SUCCESS_SUBTLE,
    SURFACE,
    TEXT_2,
    WARN,
)
from ui.components import (  # noqa: E402
    badge,
    card,
    citation_chip,
    empty_state,
    grounding_note,
    info_card,
    metric_tile,
    muted_panel,
    page_header,
    provenance_badge,
    risk_pill,
    section_header,
    status_banner,
    status_pill,
)
from ui.icons import icon  # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
# Constants / content (palette + theme live in ui/theme.py)
# ─────────────────────────────────────────────────────────────────────────────

CERT_NAMES = {
    "AZ-204": "Developing Solutions for Microsoft Azure",
    "AZ-305": "Designing Azure Infrastructure Solutions",
    "AZ-400": "DevOps Solutions",
    "DP-203": "Data Engineering on Azure",
    "AZ-500": "Azure Security Technologies",
}

# (icon_name, name, iq_grounding, description)
AGENT_ROSTER = [
    ("agent_curator",    "Learning Path Curator",  "Foundry IQ",            "Grounded resource retrieval — returns source → section citations for every item"),
    ("agent_planner",    "Study Plan Generator",   "Fabric IQ",             "Planner-Executor — derives milestones from cert ontology, allocates remaining hours"),
    ("agent_engagement", "Engagement Agent",       "Work IQ",               "Workload-aware scheduling — adapts reminders to meeting load and focus windows"),
    ("agent_assessment", "Assessment Agent",       "Foundry IQ + Fabric IQ","Critic/Verifier — checks readiness vs. threshold; loops back if not ready (max 2×)"),
    ("agent_manager",    "Manager Insights Agent", "Work IQ + Fabric IQ",   "Privacy-conscious fan-in — aggregates team readiness without exposing individual scores"),
]

# (icon_name, name, accent_color, description)
IQ_LAYERS = [
    ("iq_foundry", "Foundry IQ", AZURE_BLUE, "Hybrid BM25 + TF-IDF retrieval over synthetic cert-guide knowledge base. Every result carries source → section citations, mirroring Foundry IQ's permission-aware grounded retrieval."),
    ("iq_fabric",  "Fabric IQ",  PURPLE,     "Certification ontology: Learner, Role, Certification, Skill, PassThreshold, RecommendedHours, next_certification. Semantic layer for readiness scoring and study planning."),
    ("iq_work",    "Work IQ",    SUCCESS,    "Synthetic workplace signals (meeting hours, focus hours, preferred slot). Drives study scheduling, session lengths, and capacity flags — keeping outputs supportive and privacy-conscious."),
]

# (icon_name, name, description)
REASONING_PATTERNS = [
    ("pattern_planner", "Planner-Executor",  "Study Plan Generator plans milestones from the Fabric IQ ontology, then executes by allocating the remaining study-hour budget across those milestones."),
    ("pattern_critic",  "Critic / Verifier", "Assessment Agent verifies readiness against Fabric IQ thresholds. If not ready and under the iteration cap (max 2), it loops back to the Study Plan Generator with an adjusted hours target."),
    ("pattern_fanout",  "Fan-out / Fan-in",  "The team workflow fans out the per-learner subworkflow across all learners, then fans in every result to the Manager Insights Agent for team-level aggregation."),
]


# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_resource(show_spinner=False)
def get_workflow() -> TalentFabricWorkflow:
    return TalentFabricWorkflow()


# ─────────────────────────────────────────────────────────────────────────────
# Page helpers
# ─────────────────────────────────────────────────────────────────────────────

def _readiness_gauge(score: int, threshold: int, title: str, color: str) -> go.Figure:
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number+delta",
            value=score,
            delta={"reference": threshold, "valueformat": ".0f", "prefix": "vs threshold "},
            gauge={
                "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": TEXT_2},
                "bar": {"color": color, "thickness": 0.25},
                "bgcolor": SURFACE,
                "borderwidth": 1,
                "bordercolor": BORDER_SUBTLE,
                "steps": [
                    {"range": [0, threshold], "color": DANGER_SUBTLE},
                    {"range": [threshold, 100], "color": SUCCESS_SUBTLE},
                ],
                "threshold": {
                    "line": {"color": DANGER, "width": 3},
                    "thickness": 0.75,
                    "value": threshold,
                },
            },
            number={"font": {"color": color, "size": 36}, "suffix": " pts"},
            title={"text": title, "font": {"size": 13}},
        )
    )
    fig.update_layout(height=210, margin=dict(t=35, b=5, l=15, r=15))  # bg/font from template
    return fig


def _hours_gauge(studied: int, recommended: int) -> go.Figure:
    pct = round(min(studied / recommended * 100, 100))
    color = SUCCESS if pct >= 80 else (WARN if pct >= 50 else DANGER)
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=pct,
            gauge={
                "axis": {"range": [0, 100], "ticksuffix": "%"},
                "bar": {"color": color, "thickness": 0.25},
                "steps": [
                    {"range": [0, 80], "color": DANGER_SUBTLE},
                    {"range": [80, 100], "color": SUCCESS_SUBTLE},
                ],
                "threshold": {
                    "line": {"color": WARN, "width": 3},
                    "thickness": 0.75,
                    "value": 80,
                },
            },
            number={"font": {"color": color, "size": 36}, "suffix": "%"},
            title={"text": f"Hours Completion ({studied}/{recommended}h)", "font": {"size": 13}},
        )
    )
    fig.update_layout(height=210, margin=dict(t=35, b=5, l=15, r=15))  # bg/font from template
    return fig


def _milestone_chart(milestones: list, cert: str, iteration: int) -> go.Figure:
    df = pd.DataFrame(milestones)
    fig = px.bar(
        df,
        x="allocated_hours",
        y="skill",
        orientation="h",
        color="allocated_hours",
        color_continuous_scale=[[0, ACCENT_SUBTLE], [1, AZURE_BLUE]],
        labels={"allocated_hours": "Allocated Hours", "skill": "Skill Area"},
        title=f"{cert} — Study Milestone Allocation (iteration {iteration})",
        text="allocated_hours",
    )
    fig.update_traces(texttemplate="%{text}h", textposition="outside")
    fig.update_layout(
        # Colours/grid/font inherited from the registered Plotly template.
        height=max(220, len(milestones) * 52 + 80),
        showlegend=False,
        coloraxis_showscale=False,
        margin=dict(t=50, b=20, l=10, r=60),  # right margin for outside labels
        yaxis=dict(tickfont=dict(size=11)),
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Page: Overview / Home
# ─────────────────────────────────────────────────────────────────────────────

# Pipeline nodes: (icon, label, iq-tag, accent, has_loopback)
_PIPELINE = [
    ("agent_curator",    "Learning Path Curator", "Foundry IQ",          AZURE_BLUE, False),
    ("agent_planner",    "Study Plan Generator",  "Fabric IQ",           PURPLE,     False),
    ("agent_engagement", "Engagement Agent",      "Work IQ",             SUCCESS,    False),
    ("agent_assessment", "Assessment Agent",      "Foundry + Fabric IQ", AZURE_BLUE, True),
    ("agent_manager",    "Manager Insights",      "Work + Fabric IQ",    PURPLE,     False),
]


def _pipeline_html() -> str:
    aria = ("Five-agent pipeline: Learning Path Curator, Study Plan Generator, Engagement Agent, "
            "Assessment Agent (with loop-back to Study Plan Generator), then Manager Insights Agent.")
    parts = [f'<div class="pipeline" role="img" aria-label="{aria}">']
    for i, (ic, label, iq, color, loop) in enumerate(_PIPELINE):
        if i:
            parts.append('<div class="pipe-arrow" aria-hidden="true">→</div>')
        loop_html = '<div class="loop-label">↩ loop-back (max 2×)</div>' if loop else ""
        parts.append(
            f'<div class="agent-node">'
            f'<div class="agent-box" style="--node:{color}">{icon(ic, 18)}<span>{label}</span></div>'
            f'{loop_html}'
            f'<div class="agent-iq-tag" style="--tag:{color}">{iq}</div></div>'
        )
    parts.append("</div>")
    return "".join(parts)


def page_home(wf: TalentFabricWorkflow) -> None:
    st.markdown(
        f'<div class="tf-hero" role="banner" aria-label="TalentFabric AI">'
        f'<h1>{icon("brand", 34, label="TalentFabric AI logo")}<span>TalentFabric AI</span></h1>'
        f'<p>Enterprise Azure Certification Readiness Platform &nbsp;·&nbsp; '
        f'5-Agent Reasoning System &nbsp;·&nbsp; Microsoft Foundry IQ &nbsp;·&nbsp; Fabric IQ &nbsp;·&nbsp; Work IQ</p>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Quick stats
    all_learners = wf.fabric_iq.list_learners()
    teams = wf.fabric_iq.list_teams()
    stats = [
        (len(teams), "Teams", AZURE_BLUE),
        (len(all_learners), "Learners", AZURE_BLUE),
        (5, "Certifications", PURPLE),
        (3, "IQ Layers", SUCCESS),
        (5, "AI Agents", WARN),
    ]
    for col, (val, lbl, clr) in zip(st.columns(5), stats):
        col.markdown(metric_tile(val, lbl, clr), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Pipeline diagram ──────────────────────────────────────────────
    st.markdown(section_header("5-Agent Reasoning Pipeline", "nav_comparison"), unsafe_allow_html=True)
    st.markdown(_pipeline_html(), unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    # ── IQ Layers ─────────────────────────────────────────────────────
    st.markdown(section_header("Microsoft IQ Layers", "brand"), unsafe_allow_html=True)
    for col, (ic, name, color, desc) in zip(st.columns(3), IQ_LAYERS):
        col.markdown(info_card(name, desc, accent=color, icon_name=ic), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Reasoning patterns ────────────────────────────────────────────
    st.markdown(section_header("Reasoning Patterns", "pattern_critic"), unsafe_allow_html=True)
    for col, (ic, name, desc) in zip(st.columns(3), REASONING_PATTERNS):
        col.markdown(info_card(name, desc, accent=AZURE_BLUE, icon_name=ic), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.caption(
        "⚠️ Synthetic data only — all learner IDs, employee IDs, and certification performance data "
        "are fabricated for demonstration. No real names, credentials, or organisational data are used."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Page: Learner Analysis
# ─────────────────────────────────────────────────────────────────────────────

def page_learner(wf: TalentFabricWorkflow) -> None:
    st.markdown(page_header("Learner Analysis", "nav_learner"), unsafe_allow_html=True)
    st.caption("Run the Sequential Student Readiness Subworkflow for a learner and step through each agent's grounded output.")

    teams = wf.fabric_iq.list_teams()
    c1, c2 = st.columns(2)
    team_id = c1.selectbox("Team", teams, key="learner_team")
    learners = wf.fabric_iq.list_learners(team_id)
    learner_id = c2.selectbox(
        "Learner",
        [l["learner_id"] for l in learners],
        format_func=lambda lid: f"{lid} · {next(l['role'] for l in learners if l['learner_id'] == lid)}",
        key="learner_id",
    )

    if st.button("▶ Run Subworkflow", type="primary"):
        bar = st.progress(0, text="Initialising…")
        steps = ["📚 Curator", "📅 Study Plan", "⏰ Engagement", "✅ Assessment"]
        for i, s in enumerate(steps, 1):
            bar.progress(i / (len(steps) + 1), text=f"Running {s}…")
        with st.spinner("Finalising…"):
            result = wf.run_learner_subworkflow(learner_id)
        bar.progress(1.0, text="Complete ✓")
        st.session_state["learner_result"] = result
        bar.empty()

    result = st.session_state.get("learner_result")
    if not (result and result["learner_id"] == learner_id):
        st.markdown(
            empty_state(
                "No learner analysis yet",
                "Select a team and learner above, then click Run Subworkflow to begin.",
                icon_name="agent_curator",
            ),
            unsafe_allow_html=True,
        )
        return

    learner = wf.fabric_iq.get_learner(learner_id)
    rd = result["assessment"]["readiness"]
    status = rd["readiness_status"]
    risk = rd["risk_level"]
    cert_id = rd["certification"]
    cert_name = CERT_NAMES.get(cert_id, cert_id)
    status_c = SUCCESS if status == "Ready" else DANGER

    # ── Summary header (Fluent detail card) ───────────────────────────
    st.markdown(
        f'<div class="tf-detail" style="--card-accent:{status_c}">'
        f'<div class="tf-detail__row">'
        f'<div><div class="tf-detail__title">{learner_id} · {learner["role"]}</div>'
        f'<div class="tf-detail__sub">Team {learner["team_id"]} &nbsp;|&nbsp; '
        f'Target: <strong>{cert_id}</strong> — {cert_name}</div></div>'
        f'<div class="tf-detail__meta">{status_pill(status)}{risk_pill(risk)}'
        f'<span class="tf-detail__iter">{result["iterations"]} iteration(s)</span>'
        f'</div></div></div>',
        unsafe_allow_html=True,
    )

    # ── Readiness gauges ──────────────────────────────────────────────
    g1, g2 = st.columns(2)
    with g1:
        st.plotly_chart(
            _readiness_gauge(rd["practice_score_avg"], rd["pass_threshold"], "Practice Score", status_c),
            width="stretch",
        )
    with g2:
        st.plotly_chart(
            _hours_gauge(rd["hours_studied"], rd["recommended_hours"]),
            width="stretch",
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Agent tabs ────────────────────────────────────────────────────
    t1, t2, t3, t4 = st.tabs(
        ["📚 Learning Path Curator", "📅 Study Plan Generator", "⏰ Engagement Agent", "✅ Assessment Agent"]
    )

    # Tab 1 — Curator
    with t1:
        st.markdown(
            grounding_note(
                "Grounding: Foundry IQ — hybrid BM25 + TF-IDF · source → section citations required",
                AZURE_BLUE, "iq_foundry",
            ),
            unsafe_allow_html=True,
        )
        st.write(result["curator"]["narrative"])
        st.markdown("**Cited Resources**")
        for r in result["curator"]["resources"]:
            cite = f'{r["source"]} → {r["section"]}  ·  score {r["score"]:.3f}'
            cols = st.columns([0.78, 0.22])
            cols[0].markdown(
                citation_chip(cite, url=r.get("source_url")), unsafe_allow_html=True
            )
            cols[1].markdown(
                provenance_badge(r.get("source_tier", "synthetic-internal")), unsafe_allow_html=True
            )
            with st.expander(f"Preview — {r['section']}", expanded=False):
                st.markdown(r.get("text", r["snippet"]))
        st.caption(
            f"{len(result['curator']['resources'])} citations — every resource is grounded to an "
            "approved source, mirroring Foundry IQ's permission-aware retrieval."
        )

    # Tab 2 — Study Plan
    with t2:
        st.markdown(
            grounding_note(
                "Grounding: Fabric IQ — certification ontology (skills, hours, prerequisites, thresholds) · Planner-Executor",
                PURPLE, "iq_fabric",
            ),
            unsafe_allow_html=True,
        )
        st.write(result["plan"]["narrative"])
        plan = result["plan"]["plan"]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Certification", plan["certification"])
        c2.metric("Recommended Total", f"{plan['recommended_total_hours']}h")
        c3.metric("Already Studied", f"{plan['hours_already_studied']}h")
        c4.metric("Remaining Target", f"{plan['remaining_hours_target']}h")

        if plan["prerequisites"]:
            st.info(f"Prerequisites: {', '.join(plan['prerequisites'])}")

        st.plotly_chart(
            _milestone_chart(plan["milestones"], plan["certification"], plan["iteration"]),
            width="stretch",
        )
        st.caption("Milestones are derived from the Fabric IQ certification ontology. Hours are allocated by Planner-Executor reasoning.")

        # Phase-3 Microsoft Learn module grounding (shown only when MCP is on)
        learn_modules = plan.get("learn_modules")
        if learn_modules:
            st.markdown(section_header("Microsoft Learn Modules", "mcp"), unsafe_allow_html=True)
            if plan.get("hours_reconciliation"):
                st.markdown(muted_panel(plan["hours_reconciliation"]), unsafe_allow_html=True)
            for m in learn_modules:
                st.markdown(
                    citation_chip(m["title"], url=m.get("url"), icon_name="grounding"),
                    unsafe_allow_html=True,
                )

    # Tab 3 — Engagement
    with t3:
        st.markdown(
            grounding_note(
                "Grounding: Work IQ — workplace signals (meeting load, focus hours, preferred slot)",
                SUCCESS, "iq_work",
            ),
            unsafe_allow_html=True,
        )
        st.write(result["engagement"]["narrative"])
        sched = result["engagement"]["schedule"]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Preferred Slot", sched["recommended_slot"])
        c2.metric("Session Length", f"{sched['session_length_minutes']} min")
        c3.metric("Sessions / Week", str(sched["sessions_per_week"]))
        cap_val = "⚠️ Constrained" if sched["capacity_flag"] else "✅ Normal"
        c4.metric("Capacity Status", cap_val)

        st.markdown(
            muted_panel(sched["rationale"], title="Work IQ Rationale"),
            unsafe_allow_html=True,
        )
        st.caption(
            "Engagement scheduling is privacy-conscious: only the recommended slot and session length are surfaced "
            "— raw calendar data is never exposed."
        )

    # Tab 4 — Assessment
    with t4:
        st.markdown(
            grounding_note(
                "Grounding: Foundry IQ (cited questions) + Fabric IQ (thresholds) · Critic/Verifier with loop-back",
                AZURE_BLUE, "agent_assessment",
            ),
            unsafe_allow_html=True,
        )
        st.write(result["assessment"]["narrative"])

        # Readiness detail table
        rd_display = [
            ("Practice Score",    f"{rd['practice_score_avg']} / 100"),
            ("Pass Threshold",    str(rd["pass_threshold"])),
            ("Score Gap",         f"{rd['score_gap']} pts"),
            ("Hours Studied",     f"{rd['hours_studied']} / {rd['recommended_hours']}h"),
            ("Hours Completion",  f"{rd['hours_completion_ratio'] * 100:.0f}%"),
            ("Readiness Status",  rd["readiness_status"]),
            ("Risk Level",        rd["risk_level"]),
        ]
        st.dataframe(
            pd.DataFrame(rd_display, columns=["Metric", "Value"]),
            hide_index=True,
            width="stretch",
        )

        if result["assessment"]["recommended_next_certification"]:
            st.success(
                f"Ready for next certification: **{result['assessment']['recommended_next_certification']}**"
            )
        if result["assessment"]["loop_back"]:
            st.warning(
                f"Looped back to Study Plan Generator with +4h target "
                f"(iteration {result['assessment']['iteration']})"
            )

        # Corrective-RAG validation gate + drift detection (the reasoning story)
        validation = result["assessment"].get("validation")
        if validation:
            st.markdown(section_header("Validation Gate", "status_ready"), unsafe_allow_html=True)
            v1, v2, v3, v4 = st.columns(4)
            v1.markdown(metric_tile(validation["generated"], "Generated", AZURE_BLUE), unsafe_allow_html=True)
            v2.markdown(metric_tile(validation["emitted"], "Grounded / Emitted", SUCCESS), unsafe_allow_html=True)
            v3.markdown(
                metric_tile(validation["dropped"], "Dropped", WARN if validation["dropped"] else TEXT_2),
                unsafe_allow_html=True,
            )
            corrective = "Yes" if validation.get("corrective_retrieval_used") else "No"
            v4.markdown(metric_tile(corrective, "Corrective Re-retrieval", PURPLE), unsafe_allow_html=True)
            st.caption(
                f"Every emitted question is provenance-tagged and passes a deterministic "
                f"groundedness gate (threshold {validation['groundedness_threshold']}). Ungrounded "
                f"questions trigger one corrective re-retrieval before being dropped."
            )
            drift = result["assessment"].get("drift_skills") or []
            if result["assessment"].get("drift_flag") and drift:
                chips = " ".join(badge(s, fg=WARN, icon_name="status_warning") for s in drift)
                st.markdown(
                    muted_panel(body_html=chips, title="Skill-coverage drift"),
                    unsafe_allow_html=True,
                )
                st.caption(
                    "Drift = certification skills (Fabric IQ ontology) not covered by the retrieved "
                    "passages — a non-fatal signal, surfaced for transparency."
                )

        st.markdown(section_header("Cited Practice Questions", "agent_assessment"), unsafe_allow_html=True)
        pqs = result["assessment"]["practice_questions"]
        for i, q in enumerate(pqs, 1):
            q_type = q.get("type", "Applied")
            type_colors = {
                "Conceptual": AZURE_BLUE, "Applied": PURPLE,
                "Scenario": WARN, "Evaluative": SUCCESS, "Comparative": DANGER,
            }
            tc = type_colors.get(q_type, AZURE_BLUE)
            label = f"Q{i} [{q_type}] — {q['question'][:70]}{'…' if len(q['question']) > 70 else ''}"
            with st.expander(label, expanded=(i == 1)):
                st.write(q["question"])
                st.markdown(
                    citation_chip(q["citation"], url=q.get("source_url")), unsafe_allow_html=True
                )
                cols = st.columns([0.3, 0.7])
                cols[0].markdown(badge(q_type, fg=tc), unsafe_allow_html=True)
                cols[1].markdown(
                    provenance_badge(q.get("source_tier", "synthetic-internal")), unsafe_allow_html=True
                )


# ─────────────────────────────────────────────────────────────────────────────
# Page: Manager Dashboard
# ─────────────────────────────────────────────────────────────────────────────

def page_manager(wf: TalentFabricWorkflow) -> None:
    st.markdown(page_header("Manager Dashboard", "nav_manager"), unsafe_allow_html=True)
    st.caption(
        "Team-level certification readiness report. Individual practice scores are **never** exposed — "
        "only aggregate insights are surfaced."
    )

    teams = wf.fabric_iq.list_teams()
    team_id = st.selectbox("Team", teams, key="mgr_team")

    if st.button("▶ Run Team Aggregation", type="primary"):
        with st.spinner(f"Running per-learner subworkflows for {team_id} and aggregating…"):
            st.session_state["team_result"] = wf.run_team(team_id)

    team_result = st.session_state.get("team_result")
    if not (team_result and team_result["team_id"] == team_id):
        st.markdown(
            empty_state(
                "No team report yet",
                "Pick a team above, then click Run Team Aggregation to generate the readiness report.",
                icon_name="nav_manager",
            ),
            unsafe_allow_html=True,
        )
        return

    report = team_result["manager_insights"]["report"]
    st.markdown(f"### Team Readiness Report — {team_id}")
    st.caption("Grounding: Work IQ (capacity signals) + Fabric IQ (skill-gap analytics)")

    # ── KPI cards ─────────────────────────────────────────────────────
    total = report["team_size"]
    ready = report["readiness_status_counts"].get("Ready", 0)
    not_ready = report["readiness_status_counts"].get("Not Ready", 0)
    constrained = report["capacity_constrained_learners"]
    high_risk = report["risk_level_counts"].get("High", 0)

    kpis = [
        (total,       "Team Size",          AZURE_BLUE),
        (ready,       "Ready",              SUCCESS),
        (not_ready,   "Not Ready",          DANGER),
        (constrained, "Capacity Constrained", WARN),
        (high_risk,   "High Risk",          DANGER),
    ]
    cols = st.columns(5)
    for col, (v, lbl, clr) in zip(cols, kpis):
        col.markdown(metric_tile(v, lbl, clr), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Charts ────────────────────────────────────────────────────────
    c1, c2 = st.columns(2)
    with c1:
        status_data = report["readiness_status_counts"]
        # Colour-blind-safe: distinct fill patterns + always-on label+percent text.
        fig_pie = go.Figure(
            go.Pie(
                labels=list(status_data.keys()),
                values=list(status_data.values()),
                marker=dict(
                    colors=[SUCCESS if k == "Ready" else DANGER for k in status_data],
                    pattern=dict(shape=["" if k == "Ready" else "/" for k in status_data]),
                ),
                hole=0.45,
                textinfo="label+percent",
                textfont_size=13,
            )
        )
        fig_pie.update_layout(
            title="Readiness Distribution",
            height=290,
            margin=dict(t=45, b=10, l=10, r=10),
            showlegend=False,
        )  # bg/font from template; green/red marker colours are deliberate + patterned
        st.plotly_chart(fig_pie, width="stretch")

    with c2:
        risk_data = report["risk_level_counts"]
        risk_order = ["Low", "Medium", "High"]
        risk_cols = [SUCCESS, WARN, DANGER]
        labels = [r for r in risk_order if r in risk_data]
        values = [risk_data[r] for r in labels]
        colors = [c for r, c in zip(risk_order, risk_cols) if r in risk_data]

        # Colour-blind-safe: per-level fill patterns + value labels.
        risk_patterns = {"Low": "", "Medium": "/", "High": "x"}
        fig_risk = go.Figure(
            go.Bar(
                x=labels, y=values,
                marker=dict(
                    color=colors,
                    pattern=dict(shape=[risk_patterns.get(r, "") for r in labels]),
                ),
                text=values, textposition="outside",
                textfont_size=14,
            )
        )
        fig_risk.update_layout(
            title="Risk Level Distribution",
            height=290,
            margin=dict(t=45, b=20, l=10, r=10),
            yaxis_title="",
            xaxis_title="",
        )  # bg/grid/font from template
        st.plotly_chart(fig_risk, width="stretch")

    # ── Manager narrative ─────────────────────────────────────────────
    st.markdown(section_header("Manager Summary", "agent_manager"), unsafe_allow_html=True)
    st.markdown(card(team_result["manager_insights"]["narrative"]), unsafe_allow_html=True)

    # ── Skill gaps ────────────────────────────────────────────────────
    if report["top_skill_gaps"]:
        st.markdown(section_header("Top Skill Gaps (team-wide)", "iq_fabric"), unsafe_allow_html=True)
        gaps = report["top_skill_gaps"]
        freq = list(range(len(gaps), 0, -1))
        fig_gap = go.Figure(
            go.Bar(
                x=freq, y=gaps, orientation="h",
                marker_color=WARN,
                text=freq, textposition="outside",
            )
        )
        fig_gap.update_layout(
            height=max(180, len(gaps) * 48 + 60),
            showlegend=False,
            margin=dict(t=20, b=20, l=10, r=60),  # right margin for outside labels
            xaxis_title="Frequency (Not-Ready learners)",
            yaxis_title="",
        )  # bg/grid/font from template
        st.plotly_chart(fig_gap, width="stretch")
        st.caption("Skill gaps are derived from the Fabric IQ certification ontology — skills tied to each Not-Ready learner's target certification.")

    # ── Per-learner table ─────────────────────────────────────────────
    st.markdown(section_header("Per-Learner Status", "nav_learner"), unsafe_allow_html=True)
    st.markdown(
        badge("Privacy-safe — status & risk only, no individual scores", fg=SUCCESS, icon_name="privacy"),
        unsafe_allow_html=True,
    )
    rows = []
    for lr in team_result["learner_results"]:
        rd = lr["assessment"]["readiness"]
        rows.append({
            "Learner ID":   lr["learner_id"],
            "Role":         lr["role"],
            "Certification": rd["certification"],
            "Status":       rd["readiness_status"],
            "Risk Level":   rd["risk_level"],
            "Capacity Constrained": lr["engagement"]["schedule"]["capacity_flag"],
            "Iterations":   lr["iterations"],
        })
    st.dataframe(
        pd.DataFrame(rows),
        width="stretch",
        hide_index=True,
        column_config={
            "Capacity Constrained": st.column_config.CheckboxColumn(
                "Capacity Constrained", help="Flagged when meeting load is high and focus time is low"
            ),
            "Iterations": st.column_config.NumberColumn("Iterations", format="%d×"),
        },
    )

    # ── Next steps ────────────────────────────────────────────────────
    if report["recommended_next_steps"]:
        st.markdown(section_header("Recommended Next-Certification Steps", "pattern_planner"), unsafe_allow_html=True)
        nxt = pd.DataFrame(
            [
                {
                    "Learner ID": s["learner_id"],
                    "Next Certification": s["next_certification"],
                    "Microsoft Learn": (s.get("learn_reference") or {}).get("url"),
                }
                for s in report["recommended_next_steps"]
            ]
        )
        col_cfg = {"Microsoft Learn": st.column_config.LinkColumn("Microsoft Learn", display_text="Open ↗")}
        if nxt["Microsoft Learn"].isna().all():
            nxt = nxt.drop(columns=["Microsoft Learn"])
            col_cfg = {}
        st.dataframe(nxt, width="stretch", hide_index=True, column_config=col_cfg)

    # ── Export ────────────────────────────────────────────────────────
    st.markdown(section_header("Export", "export"), unsafe_allow_html=True)
    buf = io.StringIO()
    pd.DataFrame(rows).to_csv(buf, index=False)
    st.download_button(
        label="Download Team Report (CSV)",
        data=buf.getvalue(),
        file_name=f"talentfabric_{team_id}_readiness_report.csv",
        mime="text/csv",
        help="Privacy-safe export: no individual practice scores included.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Page: Team Comparison
# ─────────────────────────────────────────────────────────────────────────────

def page_comparison(wf: TalentFabricWorkflow) -> None:
    st.markdown(page_header("Team Comparison", "nav_comparison"), unsafe_allow_html=True)
    st.caption("Cross-team view of certification readiness. Runs the full workflow for all teams and compares results.")

    if st.button("▶ Run All Teams & Compare", type="primary"):
        all_teams: dict = {}
        bar = st.progress(0, text="Starting…")
        teams = wf.fabric_iq.list_teams()
        for i, tid in enumerate(teams):
            bar.progress((i + 0.2) / len(teams), text=f"Running {tid}…")
            all_teams[tid] = wf.run_team(tid)
        bar.progress(1.0, text="All teams complete ✓")
        st.session_state["all_teams"] = all_teams
        bar.empty()

    all_teams = st.session_state.get("all_teams")
    if not all_teams:
        st.markdown(
            empty_state(
                "No comparison yet",
                "Click Run All Teams & Compare to run every team and compare readiness side by side.",
                icon_name="nav_comparison",
            ),
            unsafe_allow_html=True,
        )
        return

    # ── Stacked readiness bar ─────────────────────────────────────────
    comp_rows = []
    for tid, tr in all_teams.items():
        r = tr["manager_insights"]["report"]
        comp_rows.append({
            "Team":      tid,
            "Ready":     r["readiness_status_counts"].get("Ready", 0),
            "Not Ready": r["readiness_status_counts"].get("Not Ready", 0),
        })
    df_comp = pd.DataFrame(comp_rows)

    fig_comp = go.Figure()
    fig_comp.add_trace(go.Bar(name="Ready",     x=df_comp["Team"], y=df_comp["Ready"],     marker=dict(color=SUCCESS),                       text=df_comp["Ready"],     textposition="auto"))
    fig_comp.add_trace(go.Bar(name="Not Ready", x=df_comp["Team"], y=df_comp["Not Ready"], marker=dict(color=DANGER, pattern=dict(shape="/")), text=df_comp["Not Ready"], textposition="auto"))
    fig_comp.update_layout(
        barmode="stack", title="Readiness Distribution by Team",
        height=310,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=60, b=20, l=10, r=10),
    )  # bg/font from template
    st.plotly_chart(fig_comp, width="stretch")

    # ── Grouped risk bar ──────────────────────────────────────────────
    risk_rows = []
    for tid, tr in all_teams.items():
        r = tr["manager_insights"]["report"]
        for level in ["High", "Medium", "Low"]:
            risk_rows.append({"Team": tid, "Risk Level": level, "Count": r["risk_level_counts"].get(level, 0)})
    df_risk = pd.DataFrame(risk_rows)

    fig_risk = px.bar(
        df_risk, x="Team", y="Count", color="Risk Level",
        color_discrete_map={"High": DANGER, "Medium": WARN, "Low": SUCCESS},
        # Colour-blind-safe: per-level fill patterns, matching the single-team bars.
        pattern_shape="Risk Level",
        pattern_shape_map={"Low": "", "Medium": "/", "High": "x"},
        barmode="group", title="Risk Level Distribution by Team",
        height=310, text_auto=True,
    )
    # bg/font inherited from the template (px.bar already uses the default template)
    st.plotly_chart(fig_risk, width="stretch")

    # ── Summary table ─────────────────────────────────────────────────
    st.markdown(section_header("Cross-Team Summary", "nav_manager"), unsafe_allow_html=True)
    summary = []
    for tid, tr in all_teams.items():
        r = tr["manager_insights"]["report"]
        summary.append({
            "Team":                tid,
            "Size":                r["team_size"],
            "Ready":               r["readiness_status_counts"].get("Ready", 0),
            "Not Ready":           r["readiness_status_counts"].get("Not Ready", 0),
            "High Risk":           r["risk_level_counts"].get("High", 0),
            "Capacity Constrained": r["capacity_constrained_learners"],
            "Top Skill Gap":       r["top_skill_gaps"][0] if r["top_skill_gaps"] else "—",
        })
    st.dataframe(pd.DataFrame(summary), width="stretch", hide_index=True)

    # ── Export all teams ──────────────────────────────────────────────
    all_rows = []
    for tid, tr in all_teams.items():
        for lr in tr["learner_results"]:
            rd = lr["assessment"]["readiness"]
            all_rows.append({
                "Team":          tid,
                "Learner ID":    lr["learner_id"],
                "Role":          lr["role"],
                "Certification": rd["certification"],
                "Status":        rd["readiness_status"],
                "Risk Level":    rd["risk_level"],
                "Capacity Flag": lr["engagement"]["schedule"]["capacity_flag"],
            })
    buf = io.StringIO()
    pd.DataFrame(all_rows).to_csv(buf, index=False)
    st.download_button(
        "⬇ Download All Teams Report (CSV)",
        buf.getvalue(),
        "talentfabric_all_teams_report.csv",
        "text/csv",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Page: MCP Telemetry & Grounding
# ─────────────────────────────────────────────────────────────────────────────

def _collect_learner_results() -> list:
    """Gather any learner results currently held in session state."""
    out: list = []
    r = st.session_state.get("learner_result")
    if r:
        out.append(r)
    tr = st.session_state.get("team_result")
    if tr:
        out.extend(tr["learner_results"])
    at = st.session_state.get("all_teams")
    if at:
        for t in at.values():
            out.extend(t["learner_results"])
    # De-duplicate by learner_id (a learner may appear via multiple views).
    seen, unique = set(), []
    for lr in out:
        if lr["learner_id"] not in seen:
            seen.add(lr["learner_id"])
            unique.append(lr)
    return unique


def _rollup_cache_key(results: list) -> str:
    """A cheap, content-sensitive signature for the grounding rollup cache.

    Built from already-summarised per-learner fields (no nested re-iteration),
    so the cache invalidates when the underlying results change (e.g. a learner
    re-run with the Learn MCP toggle flipped)."""
    parts = []
    for lr in results:
        a = lr["assessment"]
        v = a.get("validation", {})
        prov = lr["curator"].get("provenance", {})
        parts.append((
            lr["learner_id"], v.get("emitted", 0), v.get("dropped", 0),
            int(a.get("drift_flag", False)), int(v.get("corrective_retrieval_used", False)),
            prov.get("microsoft_learn_public", 0), prov.get("synthetic_internal", 0),
            len(a.get("practice_questions", [])),
        ))
    return repr(sorted(parts))


@st.cache_data(show_spinner=False)
def _grounding_rollup(cache_key: str, _results: list) -> dict:
    """Pure provenance / groundedness aggregation, cached across reruns.

    ``cache_key`` (hashed) drives cache validity; ``_results`` is passed
    underscore-prefixed so Streamlit does not try to hash the nested run data.
    Caches only this derived math — never an agent run.
    """
    syn = pub = 0
    gnd_by_tier: dict[str, list] = {"synthetic-internal": [], "microsoft-learn-public": []}
    emitted = dropped = corrective = drift_count = 0
    for lr in _results:
        for res in lr["curator"]["resources"]:
            if res.get("source_tier") == "microsoft-learn-public":
                pub += 1
            else:
                syn += 1
        a = lr["assessment"]
        for q in a["practice_questions"]:
            tier = q.get("source_tier", "synthetic-internal")
            gnd_by_tier.setdefault(tier, []).append(q.get("groundedness", 0.0))
        v = a.get("validation", {})
        emitted += v.get("emitted", 0)
        dropped += v.get("dropped", 0)
        corrective += int(v.get("corrective_retrieval_used", False))
        drift_count += int(a.get("drift_flag", False))
    return {
        "syn": syn, "pub": pub, "gnd_by_tier": gnd_by_tier,
        "emitted": emitted, "dropped": dropped,
        "corrective": corrective, "drift_count": drift_count,
    }


def page_telemetry(wf: TalentFabricWorkflow) -> None:
    st.markdown(page_header("MCP Telemetry & Grounding", "nav_telemetry"), unsafe_allow_html=True)
    st.caption(
        "Live view of the Microsoft Learn MCP integration: connection status, call "
        "telemetry, and how grounded the agents' outputs are across the two content tiers."
    )

    cfg = get_learn_mcp_config()

    # ── Connection status ─────────────────────────────────────────────
    if cfg.enabled:
        accent, status_text, ic = SUCCESS, "ENABLED — hybrid (synthetic + Microsoft Learn)", "status_ready"
    else:
        accent, status_text, ic = TEXT_2, "OFF — synthetic-only (default)", "mcp"
    st.markdown(
        status_banner(
            f"LEARN_MCP_ENABLED: {status_text}",
            # Static chrome (<code>) via body_html; the one dynamic value (an
            # operator-set config URL) is escaped as defence-in-depth.
            body_html=(
                f"Endpoint: <code>{escape(cfg.endpoint)}</code> &nbsp;·&nbsp; "
                f"Token budget: {cfg.max_token_budget} &nbsp;·&nbsp; Cache TTL: {cfg.cache_ttl_hours}h"
            ),
            accent=accent,
            icon_name=ic,
        ),
        unsafe_allow_html=True,
    )
    if not cfg.enabled:
        st.markdown(
            empty_state(
                "Synthetic-only mode",
                "The Learn MCP toggle is off, so the system runs on synthetic data only. "
                "Set LEARN_MCP_ENABLED=true (in a networked environment) to populate live call "
                "telemetry. Grounding and provenance below still reflect synthetic retrieval.",
                icon_name="mcp",
            ),
            unsafe_allow_html=True,
        )

    # ── MCP client call telemetry ─────────────────────────────────────
    st.markdown(section_header("Call Telemetry", "nav_telemetry"), unsafe_allow_html=True)
    tel = learn_mcp.get_telemetry().as_dict()
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(metric_tile(tel["calls"], "MCP Calls", AZURE_BLUE), unsafe_allow_html=True)
    c2.markdown(metric_tile(f"{tel['cache_hit_rate'] * 100:.0f}%", "Cache Hit Rate", SUCCESS), unsafe_allow_html=True)
    c3.markdown(metric_tile(f"{tel['avg_latency_ms']:.0f} ms", "Avg Latency", PURPLE), unsafe_allow_html=True)
    c4.markdown(metric_tile(tel["errors"], "Errors (degraded)", WARN if tel["errors"] else TEXT_2), unsafe_allow_html=True)
    if tel["calls"] == 0:
        st.caption("No MCP calls recorded yet this session (toggle off, or cached/no runs).")

    # ── Grounding & provenance from current run data ──────────────────
    learner_results = _collect_learner_results()
    st.markdown("### Grounding & Provenance")
    if not learner_results:
        st.markdown(
            empty_state(
                "No grounding data yet",
                "Run a learner, team, or comparison analysis to populate provenance and groundedness metrics.",
                icon_name="grounding",
            ),
            unsafe_allow_html=True,
        )
        return

    # Pure derived math — cached so reruns (every interaction) don't recompute it.
    rollup = _grounding_rollup(_rollup_cache_key(learner_results), learner_results)
    syn, pub = rollup["syn"], rollup["pub"]
    gnd_by_tier = rollup["gnd_by_tier"]
    emitted, dropped = rollup["emitted"], rollup["dropped"]
    corrective, drift_count = rollup["corrective"], rollup["drift_count"]

    c1, c2, c3 = st.columns(3)
    total_sources = syn + pub
    pub_pct = (pub / total_sources * 100) if total_sources else 0
    c1.markdown(metric_tile(f"{pub_pct:.0f}%", "Public Learn Sources", AZURE_BLUE), unsafe_allow_html=True)
    c2.markdown(metric_tile(emitted, "Grounded Questions", SUCCESS), unsafe_allow_html=True)
    c3.markdown(metric_tile(dropped, "Dropped by Gate", WARN if dropped else TEXT_2), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    colL, colR = st.columns(2)

    with colL:
        prov_df = pd.DataFrame(
            {"Tier": ["Synthetic internal", "Microsoft Learn (public)"], "Citations": [syn, pub]}
        )
        fig = px.bar(
            prov_df, x="Citations", y="Tier", orientation="h", text="Citations",
            color="Tier", color_discrete_map={
                "Synthetic internal": PURPLE, "Microsoft Learn (public)": AZURE_BLUE},
            title="Citation Provenance Mix",
        )
        fig.update_layout(height=240, showlegend=False, margin=dict(t=45, b=20, l=10, r=30),
                          yaxis_title="", xaxis_title="")  # bg/font from template
        st.plotly_chart(fig, width="stretch")

    with colR:
        rows = []
        for tier, scores in gnd_by_tier.items():
            if scores:
                rows.append({
                    "Source Tier": "Synthetic" if tier == "synthetic-internal" else "Microsoft Learn",
                    "Avg Groundedness": round(sum(scores) / len(scores), 3),
                    "Questions": len(scores),
                })
        if rows:
            st.markdown("**Groundedness by Source**")
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.caption(
            f"Corrective re-retrievals: {corrective}  ·  Learners with skill-drift flag: {drift_count}"
        )

    st.caption(
        "Groundedness is a deterministic term-overlap score (no LLM). The validation gate drops "
        "questions whose cited passage is too thin to support them; corrective re-retrieval attempts "
        "to recover them from a better passage before they are dropped."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Page: About / Architecture
# ─────────────────────────────────────────────────────────────────────────────

def _md_table(headers: list, rows: list) -> str:
    """Render a Markdown table (cells wrap, so long prose isn't truncated)."""
    def esc(c) -> str:
        return str(c).replace("|", "\\|")
    head = "| " + " | ".join(esc(h) for h in headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = "\n".join("| " + " | ".join(esc(c) for c in r) + " |" for r in rows)
    return "\n".join([head, sep, body])


def page_about(wf: TalentFabricWorkflow) -> None:
    st.markdown(page_header("About TalentFabric AI", "nav_about"), unsafe_allow_html=True)
    st.markdown(
        "**TalentFabric AI** is a five-agent enterprise certification readiness system built on the "
        "Microsoft Reasoning Agents framework. It demonstrates grounded multi-agent reasoning, "
        "orchestration, semantic business understanding, and production-ready deployment patterns.\n\n"
        "Built for the **Agents League Hackathon — Challenge A: Enterprise Learning System** (Reasoning Agents track)."
    )

    st.markdown(section_header("Agent Roster", "agent_manager"), unsafe_allow_html=True)
    st.markdown(
        _md_table(
            ["Agent", "IQ Grounding", "Responsibility"],
            [[name, iq, resp] for _icon_name, name, iq, resp in AGENT_ROSTER],
        )
    )

    st.markdown(section_header("IQ Layers & Production Migration Path", "brand"), unsafe_allow_html=True)
    st.markdown(
        _md_table(
            ["IQ Layer", "Local Stand-in", "Production Path"],
            [
                ["🔍 Foundry IQ", "Hybrid BM25 + TF-IDF retrieval (src/iq_layers/foundry_iq.py)",
                 "Upload docs to Foundry IQ knowledge source (Blob/SharePoint/OneLake); replace FoundryIQ.query() with Foundry IQ agentic retrieval API — same (source, section, text, score) return shape"],
                ["🧩 Fabric IQ", "JSON-backed certification ontology (src/iq_layers/fabric_iq.py)",
                 "Replace with Fabric IQ OneLake semantic model queries; same readiness / skill-gap return shapes so agents above the layer need no changes"],
                ["💼 Work IQ", "Synthetic workplace signals JSON (src/iq_layers/work_iq.py)",
                 "Replace WorkIQ._signals with Work IQ API calls against Microsoft 365 tenant data (Graph calendar, activity signals)"],
            ],
        )
    )

    st.markdown(section_header("Reasoning Patterns", "pattern_critic"), unsafe_allow_html=True)
    st.markdown(
        _md_table(
            ["Pattern", "Agent", "Detail"],
            [
                ["🎯 Planner-Executor", "Study Plan Generator", "Plans milestones from Fabric IQ ontology; allocates remaining hours across them (execute step)"],
                ["🔁 Critic / Verifier", "Assessment Agent", "Verifies readiness vs. Fabric IQ pass threshold; loops back if not ready, capped at MAX_ITERATIONS=2"],
                ["🌐 Fan-out / Fan-in", "Team workflow", "Fans per-learner subworkflow out across team; fans results in to Manager Insights aggregation"],
                ["🎭 Role specialisation", "All agents", "Each of the five agents has one responsibility and one primary IQ grounding source"],
            ],
        )
    )

    st.markdown(section_header("Tech Stack", "run"), unsafe_allow_html=True)
    st.markdown(
        "| Component | Technology |\n"
        "|---|---|\n"
        "| Agent orchestration | Microsoft Agent Framework (`WorkflowBuilder`, `add_edge` with condition, `add_fan_out_edges`, `add_fan_in_edges`) |\n"
        "| LLM narration | Microsoft Foundry / Azure OpenAI → GitHub Models → templated deterministic fallback |\n"
        "| Knowledge retrieval | `rank_bm25` + `scikit-learn` TF-IDF (local stand-in for Foundry IQ) |\n"
        "| Evaluation / telemetry | Custom eval harness + MLflow |\n"
        "| UI | Streamlit + Plotly |\n"
        "| Data | 100 % synthetic — 12 learners, 3 teams, 5 Azure certifications |\n"
    )

    st.markdown(section_header("Microsoft Learn MCP Server", "mcp"), unsafe_allow_html=True)
    st.info(
        "The Microsoft Learn MCP Server (`learn.microsoft.com/api/mcp`) is integrated as a public "
        "knowledge layer, fused into Foundry IQ retrieval and gated behind `LEARN_MCP_ENABLED` "
        "(default off). It grounds the Learning Path Curator, Assessment Agent (corrective-RAG), "
        "Study Plan Generator (Learn modules), and Manager Insights (next-cert path) — degrading "
        "cleanly to the synthetic knowledge base on any failure."
    )

    # ── Disclaimer footer (trademark-safe + synthetic-data) ───────────
    st.markdown(
        muted_panel(
            body_html=(
                "<strong>Independent hackathon submission.</strong> Not affiliated with or endorsed by "
                "Microsoft. &quot;Microsoft Learn&quot;, &quot;Microsoft Foundry&quot;, &quot;Azure&quot;, "
                "and &quot;Fluent&quot; are referenced nominatively only. Fluent UI System Icons used under "
                "the MIT License; Inter font under the SIL OFL. <strong>All data is synthetic</strong> and "
                "fabricated for demonstration — no real names, credentials, or organisational data are used."
            )
        ),
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(
        page_title="TalentFabric AI",
        page_icon="🧠",
        layout="wide",
        initial_sidebar_state="expanded",
        menu_items={"About": "TalentFabric AI — Enterprise Certification Readiness Platform"},
    )
    st.markdown(inject_css(), unsafe_allow_html=True)

    wf = get_workflow()

    # ── Sidebar ───────────────────────────────────────────────────────
    st.sidebar.markdown(
        f'<div class="sidebar-brand">'
        f'<div class="sidebar-brand-title">{icon("brand", 22, label="TalentFabric AI")}'
        f'<span>TalentFabric AI</span></div>'
        f'<div class="sidebar-brand-sub">Enterprise Certification Readiness</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    page = st.sidebar.radio(
        "Navigation",
        ["Overview", "Learner Analysis", "Manager Dashboard", "Team Comparison",
         "MCP Telemetry", "About"],
        label_visibility="collapsed",
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown(
        '<div class="sidebar-legend">'
        '<strong>IQ Layers</strong><br>'
        f'{icon("iq_foundry", 14)} Foundry IQ · knowledge retrieval<br>'
        f'{icon("iq_fabric", 14)} Fabric IQ · cert ontology<br>'
        f'{icon("iq_work", 14)} Work IQ · workplace signals<br><br>'
        '<strong>Reasoning Patterns</strong><br>'
        f'{icon("pattern_planner", 14)} Planner-Executor<br>'
        f'{icon("pattern_critic", 14)} Critic / Verifier<br>'
        f'{icon("pattern_fanout", 14)} Fan-out / Fan-in<br><br>'
        '<strong>Framework</strong><br>'
        f'{icon("run", 14)} Microsoft Agent Framework<br>'
        f'{icon("mcp", 14)} Azure OpenAI / GitHub Models'
        '</div>',
        unsafe_allow_html=True,
    )

    # ── Route ─────────────────────────────────────────────────────────
    if "Overview" in page:
        page_home(wf)
    elif "Learner" in page:
        page_learner(wf)
    elif "Manager" in page:
        page_manager(wf)
    elif "Comparison" in page:
        page_comparison(wf)
    elif "Telemetry" in page:
        page_telemetry(wf)
    else:
        page_about(wf)


if __name__ == "__main__":
    main()
