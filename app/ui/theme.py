"""
Design tokens, CSS, and the Plotly theme for TalentFabric AI.

This is the single source of styling truth (Fluent 2 / Microsoft Learn). Every
colour, spacing, radius, elevation, and motion value is defined once here — as
CSS custom properties (consumed by authored CSS + components) and as Python
constants (consumed by Plotly charts). Nothing downstream should hard-code hex.

Typography: the stack prefers Segoe UI Variable / Segoe UI (native on Windows),
then a locally vendored **Inter Variable** (SIL OFL, base64-embedded below so
the demo is fully offline), then the system sans fallback. Segoe is proprietary
and is never bundled.
"""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

import plotly.graph_objects as go
import plotly.io as pio

FONTS_DIR = Path(__file__).resolve().parent / "fonts"
INTER_WOFF2 = FONTS_DIR / "inter-variable-latin.woff2"

# ─────────────────────────────────────────────────────────────────────────────
# Design tokens — Python mirror (used by Plotly + any Python-side styling)
# ─────────────────────────────────────────────────────────────────────────────

# Accent / brand
AZURE_BLUE = "#0078D4"
ACCENT_HOVER = "#106EBE"
ACCENT_DEEP = "#005A9E"
ACCENT_SUBTLE = "#C9E4FF"
AZURE_CYAN = "#50E6FF"
PURPLE = "#5C2D91"
PURPLE_DEEP = "#3B1F6F"

# Status
SUCCESS = "#00B294"
SUCCESS_SUBTLE = "#DFF6DD"
WARN = "#F7630C"
DANGER = "#D13438"
DANGER_SUBTLE = "#FDE7E9"

# AA-safe "strong" variants for use as TEXT on white / behind white text.
# The bright brand teal/orange fail WCAG AA for small text both ways; these
# darker variants pass (>=4.5:1). The bright colours stay for fills/icons/charts.
SUCCESS_STRONG = "#107C41"
WARN_STRONG = "#A14B00"
CYAN_STRONG = "#0E6E8C"
INK = "#1B1A19"  # near-black, for on-light-accent pill text

# Surfaces / neutrals
SURFACE = "#FFFFFF"
SURFACE_RAISED = "#FFFFFF"
APP_BG = "#F3F2F1"
RAIL_BG = "#1B1A19"
RAIL_BORDER = "#3A3A3A"
BORDER_SUBTLE = "#E1DFDD"

# Text
TEXT_1 = "#323130"          # primary on light
TEXT_2 = "#605E5C"          # secondary on light
TEXT_ON_DARK = "#F3F2F1"    # primary on the dark rail
TEXT_MUTED_ON_DARK = "#C8C6C4"  # AA-passing muted on rail (was #A19F9D, failed AA)

# Provenance tiers
TIER_SYNTHETIC = PURPLE
TIER_PUBLIC = AZURE_BLUE

# Typography
FONT_STACK = '"Segoe UI Variable", "Segoe UI", "Inter", system-ui, -apple-system, Roboto, sans-serif'
MONO_STACK = "'Cascadia Code', 'Consolas', 'Courier New', monospace"

# Plotly
PLOTLY_TEMPLATE_NAME = "talentfabric"
# Brand colorway. Colour-blind-safety on the semantic green/red charts is handled
# at the chart level via fill patterns + always-on data labels (readiness pie,
# risk bars, cross-team bars) — not by hue alone.
PLOTLY_COLORWAY = [AZURE_BLUE, PURPLE, SUCCESS, WARN, DANGER, AZURE_CYAN]


def risk_color(level: str) -> str:
    """Semantic colour for a risk level (Low/Medium/High)."""
    return {"Low": SUCCESS, "Medium": WARN, "High": DANGER}.get(level, TEXT_2)


# ── WCAG contrast helpers (used to keep text AA-compliant at runtime) ─────────
def _relative_luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    chans = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4) for c in chans]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast_ratio(a: str, b: str) -> float:
    la, lb = sorted((_relative_luminance(a), _relative_luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def best_text_on(bg: str) -> str:
    """Return white or near-black — whichever has higher contrast on ``bg``."""
    return "#FFFFFF" if contrast_ratio("#FFFFFF", bg) >= contrast_ratio(INK, bg) else INK


# Map bright brand colours to their AA-safe text variant (for text on white).
_TEXT_SAFE = {SUCCESS: SUCCESS_STRONG, WARN: WARN_STRONG, AZURE_CYAN: CYAN_STRONG}


def text_safe_on_white(color: str) -> str:
    """Return an AA-compliant-on-white version of ``color`` (>=4.5:1)."""
    if color in _TEXT_SAFE:
        return _TEXT_SAFE[color]
    return color if contrast_ratio(color, "#FFFFFF") >= 4.5 else INK


# ─────────────────────────────────────────────────────────────────────────────
# CSS: tokens (:root custom properties)
# ─────────────────────────────────────────────────────────────────────────────

_TOKENS_CSS = f"""
:root {{
  /* Color — accent */
  --color-accent: {AZURE_BLUE};
  --color-accent-hover: {ACCENT_HOVER};
  --color-accent-deep: {ACCENT_DEEP};
  --color-accent-subtle: {ACCENT_SUBTLE};
  --color-cyan: {AZURE_CYAN};
  --color-purple: {PURPLE};
  --color-purple-deep: {PURPLE_DEEP};
  /* Color — status */
  --success: {SUCCESS};
  --success-subtle: {SUCCESS_SUBTLE};
  --warning: {WARN};
  --danger: {DANGER};
  --danger-subtle: {DANGER_SUBTLE};
  /* Color — surfaces / neutrals */
  --surface: {SURFACE};
  --surface-raised: {SURFACE_RAISED};
  --app-bg: {APP_BG};
  --rail-bg: {RAIL_BG};
  --rail-border: {RAIL_BORDER};
  --border-subtle: {BORDER_SUBTLE};
  /* Color — text */
  --text-1: {TEXT_1};
  --text-2: {TEXT_2};
  --text-on-dark: {TEXT_ON_DARK};
  --text-muted-on-dark: {TEXT_MUTED_ON_DARK};
  /* Provenance tiers */
  --tier-synthetic: {TIER_SYNTHETIC};
  --tier-public: {TIER_PUBLIC};
  /* Typography */
  --font-sans: {FONT_STACK};
  --font-mono: {MONO_STACK};
  /* Spacing (4px scale) */
  --space-1: 4px;  --space-2: 8px;  --space-3: 12px; --space-4: 16px;
  --space-5: 20px; --space-6: 24px; --space-7: 32px; --space-8: 44px;
  /* Radius */
  --radius-sm: 4px; --radius-md: 8px; --radius-lg: 12px;
  /* Elevation */
  --elev-resting: 0 1px 4px rgba(0,0,0,.05);
  --elev-raised: 0 4px 12px rgba(0,0,0,.10);
  --elev-overlay: 0 8px 24px rgba(0,0,0,.16);
  /* Motion */
  --motion-fast: 120ms;
  --motion-med: 200ms;
  --ease-fluent: cubic-bezier(0.33, 0, 0.67, 1);
}}
"""


@lru_cache(maxsize=1)
def _font_face_css() -> str:
    """Build the @font-face for the vendored Inter, base64-embedded (offline)."""
    if not INTER_WOFF2.exists():  # graceful: fall back to the system stack
        return ""
    b64 = base64.b64encode(INTER_WOFF2.read_bytes()).decode("ascii")
    return (
        "@font-face {"
        " font-family: 'Inter';"
        " font-style: normal;"
        " font-weight: 100 900;"
        " font-display: swap;"
        f" src: url(data:font/woff2;base64,{b64}) format('woff2');"
        "}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# CSS: base (globals, shell, components) — all values via tokens
# ─────────────────────────────────────────────────────────────────────────────

_BASE_CSS = """
/* ── Globals ─────────────────────────────────────────────────────── */
html, body, [data-testid="stAppViewContainer"] { font-family: var(--font-sans); }
[data-testid="stAppViewContainer"] { background: var(--app-bg); }
[data-testid="stAppViewContainer"] .stMarkdown { color: var(--text-1); }
[data-testid="stSidebar"] { background: var(--rail-bg); }
[data-testid="stSidebar"] * { color: var(--text-on-dark) !important; }
[data-testid="stSidebar"] hr { border-color: var(--rail-border) !important; }
section[data-testid="stSidebar"] a,
section[data-testid="stSidebar"] a:visited { color: var(--color-cyan) !important; }

/* ── Hide Streamlit chrome ───────────────────────────────────────── */
#MainMenu, footer, header { visibility: hidden; }

/* ── Hero banner ─────────────────────────────────────────────────── */
.tf-hero {
    background: linear-gradient(135deg, var(--color-accent) 0%, var(--color-accent-deep) 55%, var(--color-purple-deep) 100%);
    color: #fff;
    padding: var(--space-7) var(--space-8);
    border-radius: var(--radius-lg);
    margin-bottom: var(--space-5);
}
.tf-hero h1 {
    font-size: 2.1rem; font-weight: 800;
    margin: 0 0 var(--space-2) 0; color: #fff;
    letter-spacing: -0.5px;
    display: flex; align-items: center; gap: var(--space-3);
}
.tf-hero p { font-size: 0.95rem; opacity: 0.9; margin: 0; color: var(--color-accent-subtle); }

/* ── Agent pipeline diagram ─────────────────────────────────────── */
.pipeline {
    display: flex; align-items: flex-start; flex-wrap: wrap;
    gap: 2px; margin: var(--space-4) 0;
}
.agent-node { display: flex; flex-direction: column; align-items: center; }
.agent-box {
    background: var(--surface);
    border: 1.5px solid var(--node, var(--color-accent));
    border-radius: var(--radius-md);
    padding: var(--space-2) var(--space-3);
    font-size: 0.82rem; font-weight: 600;
    color: var(--node, var(--color-accent));
    text-align: center; min-width: 124px;
    display: inline-flex; align-items: center; justify-content: center; gap: 6px;
}
.agent-iq-tag { font-size: 0.68rem; font-weight: 500; text-align: center; margin-top: var(--space-1); color: var(--tag, var(--text-2)); }
.pipe-arrow { align-self: center; color: var(--color-accent); font-size: 1.3rem; padding: 0 var(--space-1) var(--space-5); font-weight: 700; }
.loop-label { font-size: 0.68rem; color: var(--warning); text-align: center; margin-top: 3px; font-style: italic; }

/* ── Citation block ──────────────────────────────────────────────── */
.citation-block {
    font-family: var(--font-mono);
    background: var(--app-bg);
    border-left: 3px solid var(--color-accent);
    padding: var(--space-1) var(--space-3);
    border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
    font-size: 0.82rem; margin: var(--space-1) 0; color: var(--text-1);
}

/* ── Score bar ───────────────────────────────────────────────────── */
.score-bar-track { height: 8px; background: var(--border-subtle); border-radius: var(--radius-sm); overflow: hidden; margin: var(--space-1) 0; }
.score-bar-fill { height: 100%; border-radius: var(--radius-sm); transition: width var(--motion-med) var(--ease-fluent); }

/* ── Sidebar nav ─────────────────────────────────────────────────── */
.sidebar-brand { padding: var(--space-2) 0 var(--space-4) 0; border-bottom: 1px solid var(--rail-border); margin-bottom: var(--space-3); }
.sidebar-brand-title { font-size: 1.15rem; font-weight: 700; color: var(--color-cyan) !important; display: flex; align-items: center; gap: 8px; }
.sidebar-brand-sub { font-size: 0.72rem; color: var(--text-muted-on-dark) !important; margin-top: 3px; }
.sidebar-legend { font-size: 0.72rem; color: var(--text-muted-on-dark) !important; line-height: 1.7; }
.sidebar-legend strong { color: var(--text-muted-on-dark) !important; }

/* ── Accessibility: focus ring ───────────────────────────────────── */
button:focus-visible, [role="button"]:focus-visible { outline: 2px solid var(--color-cyan); outline-offset: 2px; }

/* ─────────────────────────────────────────────────────────────────
   Component library (consumed by app/ui/components.py)
   ───────────────────────────────────────────────────────────────── */
.tf-icon { display: inline-block; vertical-align: middle; line-height: 0; }
.tf-icon-fallback { font-weight: 600; }

/* Card */
.tf-card {
    background: var(--surface);
    border: 1px solid var(--border-subtle);
    border-left: 4px solid var(--card-accent, var(--color-accent));
    border-radius: var(--radius-md);
    padding: var(--space-4) var(--space-5);
    box-shadow: var(--elev-resting);
    margin: var(--space-2) 0;
    transition: box-shadow var(--motion-med) var(--ease-fluent),
                transform var(--motion-med) var(--ease-fluent);
    height: 100%;
}
.tf-card--hover:hover { box-shadow: var(--elev-raised); transform: translateY(-1px); }
.tf-card__head { display: flex; align-items: center; gap: var(--space-2); margin-bottom: var(--space-2); }
.tf-card__icon { color: var(--card-accent, var(--color-accent)); }
.tf-card__title { font-size: 1.02rem; font-weight: 700; color: var(--text-1); }
.tf-card__desc { font-size: 0.85rem; color: var(--text-2); line-height: 1.5; }

/* Metric tile */
.tf-metric {
    background: var(--surface);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    padding: var(--space-4) var(--space-5);
    text-align: center;
    height: 100%;
}
.tf-metric__value { font-size: 1.9rem; font-weight: 700; color: var(--metric-color, var(--color-accent)); line-height: 1.15; }
.tf-metric__label { font-size: 0.78rem; color: var(--text-2); margin-top: var(--space-1); }

/* Pills (status / risk) */
.tf-pill {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 3px 12px; border-radius: 999px;
    font-size: 0.8rem; font-weight: 600;
    color: var(--pill-text, #fff);
    background: var(--pill-color, var(--color-accent));
}

/* Provenance / tier badges */
.tf-badge {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 2px 10px; border-radius: 999px;
    font-size: 0.72rem; font-weight: 600;
    border: 1px solid var(--badge-border, var(--border-subtle));
    background: var(--badge-bg, transparent);
    color: var(--badge-fg, var(--text-2));
}

/* Page header (top-of-page title) */
.tf-page-header { display: flex; align-items: center; gap: var(--space-3); margin: var(--space-1) 0 var(--space-1); }
.tf-page-header__icon { color: var(--color-accent); }
.tf-page-header__title { font-size: 1.6rem; font-weight: 800; color: var(--text-1); letter-spacing: -0.3px; }

/* Section header */
.tf-section { display: flex; align-items: center; gap: var(--space-2); margin: var(--space-6) 0 var(--space-3); }
.tf-section__icon { color: var(--color-accent); }
.tf-section__title { font-size: 1.15rem; font-weight: 700; color: var(--text-1); }

/* Citation chip */
.tf-citation {
    display: inline-flex; align-items: center; gap: 6px;
    font-family: var(--font-mono);
    background: var(--app-bg);
    border: 1px solid var(--border-subtle);
    border-left: 3px solid var(--color-accent);
    border-radius: var(--radius-sm);
    padding: 4px 10px; font-size: 0.8rem; color: var(--text-1);
    margin: 3px 0; word-break: break-word;
}
.tf-citation a { color: var(--color-accent); text-decoration: none; }
.tf-citation a:hover { text-decoration: underline; }

/* State blocks (empty / loading / error) */
.tf-state {
    text-align: center; padding: var(--space-7) var(--space-5);
    background: var(--surface); border: 1px dashed var(--border-subtle);
    border-radius: var(--radius-md); color: var(--text-2);
}
.tf-state--error { border-style: solid; border-color: var(--danger); }
.tf-state__icon { color: var(--text-2); opacity: 0.7; }
.tf-state--error .tf-state__icon { color: var(--danger); opacity: 1; }
.tf-state__title { font-weight: 600; color: var(--text-1); margin-top: var(--space-2); }
.tf-state__body { font-size: 0.85rem; margin-top: var(--space-1); }

/* Detail card (page headers) */
.tf-detail {
    background: var(--surface);
    border: 1px solid var(--border-subtle);
    border-left: 4px solid var(--card-accent, var(--color-accent));
    border-radius: var(--radius-md);
    padding: var(--space-4) var(--space-6);
    box-shadow: var(--elev-resting);
    margin-bottom: var(--space-4);
}

/* Grounding note (per-agent IQ grounding label) */
.tf-grounding {
    display: flex; align-items: center; gap: 6px;
    font-size: 0.82rem; font-weight: 600;
    color: var(--g, var(--color-accent)); margin-bottom: var(--space-2);
}

/* Muted panel (rationale / secondary content) */
.tf-panel {
    background: var(--app-bg); border-radius: var(--radius-md);
    padding: var(--space-3) var(--space-4); font-size: 0.88rem; color: var(--text-2);
}
.tf-panel strong { color: var(--text-1); }

/* Detail header meta row */
.tf-detail__row { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: var(--space-3); }
.tf-detail__title { font-size: 1.15rem; font-weight: 700; color: var(--text-1); }
.tf-detail__sub { color: var(--text-2); font-size: 0.88rem; margin-top: 3px; }
.tf-detail__meta { display: flex; gap: var(--space-2); align-items: center; flex-wrap: wrap; }
.tf-detail__iter { color: var(--text-2); font-size: 0.8rem; }

/* Status banner (telemetry connection state) */
.tf-banner {
    display: flex; align-items: flex-start; gap: var(--space-3);
    background: var(--surface);
    border: 1px solid var(--border-subtle);
    border-left: 4px solid var(--banner-accent, var(--color-accent));
    border-radius: var(--radius-md);
    padding: var(--space-4) var(--space-5);
    margin-bottom: var(--space-4);
}
.tf-banner__icon { color: var(--banner-accent, var(--color-accent)); margin-top: 2px; }
.tf-banner__title { font-weight: 700; color: var(--banner-accent, var(--color-accent)); }
.tf-banner__body { font-size: 0.82rem; color: var(--text-2); margin-top: 4px; }

/* Gentle reveal for surfaces (disabled under prefers-reduced-motion below) */
@keyframes tf-fade-in { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
.tf-card, .tf-metric, .tf-detail, .tf-banner, .tf-state {
    animation: tf-fade-in var(--motion-med) var(--ease-fluent);
}

/* ── Responsive: tablet (~1024px) and narrow (~768px) ────────────── */
@media (max-width: 1024px) {
    .agent-box { min-width: 104px; font-size: 0.78rem; }
    .tf-hero { padding: var(--space-6) var(--space-6); }
}
@media (max-width: 900px) {
    /* Pipeline stacks vertically; arrows rotate to point down */
    .pipeline { flex-direction: column; align-items: stretch; gap: var(--space-1); }
    .pipe-arrow { transform: rotate(90deg); padding: var(--space-1) 0; align-self: center; }
    .agent-node { width: 100%; }
    .agent-box { width: 100%; min-width: 0; }
}
@media (max-width: 768px) {
    .tf-hero { padding: var(--space-5) var(--space-5); }
    .tf-hero h1 { font-size: 1.6rem; gap: var(--space-2); }
    .tf-hero p { font-size: 0.85rem; }
    .tf-page-header__title { font-size: 1.3rem; }
    .tf-detail__row { flex-direction: column; align-items: flex-start; }
    .tf-card, .tf-metric, .tf-detail { padding: var(--space-3) var(--space-4); }
    .tf-metric__value { font-size: 1.5rem; }
}

/* Never let content overflow its container */
.tf-card, .tf-metric, .tf-detail, .tf-banner, .tf-state, .tf-citation { max-width: 100%; box-sizing: border-box; }

/* ── Motion preference ───────────────────────────────────────────── */
@media (prefers-reduced-motion: reduce) {
  * { transition: none !important; animation: none !important; }
}
"""


def inject_css() -> str:
    """Return the full <style> block (tokens + font + base CSS)."""
    return f"<style>\n{_TOKENS_CSS}\n{_font_face_css()}\n{_BASE_CSS}\n</style>"


# ─────────────────────────────────────────────────────────────────────────────
# Plotly theme — registered once, set as the default for every chart
# ─────────────────────────────────────────────────────────────────────────────

def _build_plotly_template() -> go.layout.Template:
    return go.layout.Template(
        layout=dict(
            font=dict(family=FONT_STACK, color=TEXT_1, size=13),
            colorway=PLOTLY_COLORWAY,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor=SURFACE,
            margin=dict(t=48, b=20, l=12, r=20),
            xaxis=dict(showgrid=True, gridcolor=APP_BG, zeroline=False),
            yaxis=dict(showgrid=True, gridcolor=APP_BG, zeroline=False),
            title=dict(font=dict(size=15, color=TEXT_1)),
            legend=dict(bgcolor="rgba(0,0,0,0)"),
        )
    )


def register_plotly_template(set_default: bool = True) -> str:
    """Register the 'talentfabric' Plotly template; return its name."""
    pio.templates[PLOTLY_TEMPLATE_NAME] = _build_plotly_template()
    if set_default:
        pio.templates.default = PLOTLY_TEMPLATE_NAME
    return PLOTLY_TEMPLATE_NAME


# Register on import so any chart created after `import ui.theme` inherits it.
register_plotly_template()
