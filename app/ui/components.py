"""
Reusable UI components for TalentFabric AI.

Every component returns an HTML string built from the design-system **classes**
in ``theme`` (no inline hex) and renders via
``st.markdown(component(...), unsafe_allow_html=True)``. Token colours that must
vary per call (a card accent, a pill colour) are passed as CSS custom-property
bindings (e.g. ``style="--pill-color:…"``), not as ad-hoc style soup.
"""

from __future__ import annotations

from html import escape
from typing import Optional

from ui.icons import icon
from ui.theme import (
    AZURE_BLUE,
    DANGER,
    SUCCESS,
    TIER_PUBLIC,
    TIER_SYNTHETIC,
    WARN,
    best_text_on,
    risk_color,
    text_safe_on_white,
)


def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# ─────────────────────────────────────────────────────────────────────────────
# Cards / tiles
# ─────────────────────────────────────────────────────────────────────────────

def card(
    body: str = "",
    *,
    body_html: Optional[str] = None,
    accent: str = AZURE_BLUE,
    title: Optional[str] = None,
    icon_name: Optional[str] = None,
    hover: bool = True,
) -> str:
    """A Fluent surface card.

    ``body`` is **escaped** by default (safe for dynamic/generated text). Pass
    ``body_html`` instead for author-controlled raw markup. ``title`` is escaped.
    """
    cls = "tf-card tf-card--hover" if hover else "tf-card"
    head = ""
    if title:
        ico = f'<span class="tf-card__icon">{icon(icon_name, 18)}</span>' if icon_name else ""
        head = f'<div class="tf-card__head">{ico}<span class="tf-card__title">{escape(title)}</span></div>'
    inner = body_html if body_html is not None else escape(body)
    return f'<div class="{cls}" style="--card-accent:{accent}">{head}{inner}</div>'


def info_card(title: str, desc: str, *, accent: str = AZURE_BLUE, icon_name: Optional[str] = None) -> str:
    """A titled card with a muted description (IQ-layer / reasoning-pattern style)."""
    return card(
        body_html=f'<div class="tf-card__desc">{escape(desc)}</div>',
        accent=accent, title=title, icon_name=icon_name,
    )


def metric_tile(value, label: str, color: str = AZURE_BLUE) -> str:
    return (
        f'<div class="tf-metric" style="--metric-color:{color}">'
        f'<div class="tf-metric__value">{escape(str(value))}</div>'
        f'<div class="tf-metric__label">{escape(label)}</div></div>'
    )


# ─────────────────────────────────────────────────────────────────────────────
# Pills / badges
# ─────────────────────────────────────────────────────────────────────────────

def pill(text: str, color: str, icon_name: Optional[str] = None) -> str:
    ico = icon(icon_name, 14) if icon_name else ""
    fg = best_text_on(color)  # WCAG AA: black or white, whichever passes on this bg
    return f'<span class="tf-pill" style="--pill-color:{color};--pill-text:{fg}">{ico}{escape(text)}</span>'


def status_pill(status: str) -> str:
    """Ready/Not-Ready pill — carries an icon + text (never colour-only)."""
    ready = status == "Ready"
    return pill(status, SUCCESS if ready else DANGER, "status_ready" if ready else "status_notready")


def risk_pill(level: str) -> str:
    ico = "status_ready" if level == "Low" else "status_warning"
    return pill(f"{level} Risk", risk_color(level), ico)


def badge(text: str, *, fg: str, icon_name: Optional[str] = None, alpha: float = 0.12) -> str:
    ico = icon(icon_name, 13) if icon_name else ""
    fg = text_safe_on_white(fg)  # WCAG AA for small text on the light tint
    style = f"--badge-fg:{fg};--badge-bg:{_rgba(fg, alpha)};--badge-border:{_rgba(fg, 0.3)}"
    return f'<span class="tf-badge" style="{style}">{ico}{escape(text)}</span>'


def provenance_badge(tier: str) -> str:
    """Provenance tier badge (synthetic-internal vs microsoft-learn-public)."""
    if tier == "microsoft-learn-public":
        return badge("Microsoft Learn", fg=TIER_PUBLIC, icon_name="mcp")
    return badge("Synthetic", fg=TIER_SYNTHETIC, icon_name="privacy")


# ─────────────────────────────────────────────────────────────────────────────
# Section header / citation / states
# ─────────────────────────────────────────────────────────────────────────────

def page_header(title: str, icon_name: Optional[str] = None) -> str:
    """Top-of-page title with a leading icon."""
    ico = f'<span class="tf-page-header__icon">{icon(icon_name, 28)}</span>' if icon_name else ""
    return f'<div class="tf-page-header">{ico}<span class="tf-page-header__title">{escape(title)}</span></div>'


def section_header(title: str, icon_name: Optional[str] = None) -> str:
    ico = f'<span class="tf-section__icon">{icon(icon_name, 20)}</span>' if icon_name else ""
    return f'<div class="tf-section">{ico}<span class="tf-section__title">{escape(title)}</span></div>'


def citation_chip(text: str, url: Optional[str] = None, icon_name: str = "grounding") -> str:
    ico = f'<span aria-hidden="true">{icon(icon_name, 14)}</span>'
    inner = escape(text)
    if url:
        inner = f'{inner} <a href="{escape(url)}" target="_blank" rel="noopener">↗</a>'
    return f'<div class="tf-citation" role="note">{ico}<span>{inner}</span></div>'


def empty_state(title: str, body: str = "", icon_name: str = "nav_about") -> str:
    b = f'<div class="tf-state__body">{escape(body)}</div>' if body else ""
    return (
        f'<div class="tf-state" role="status">'
        f'<div class="tf-state__icon">{icon(icon_name, 32)}</div>'
        f'<div class="tf-state__title">{escape(title)}</div>{b}</div>'
    )


def error_state(title: str, body: str = "", icon_name: str = "status_warning") -> str:
    b = f'<div class="tf-state__body">{escape(body)}</div>' if body else ""
    return (
        f'<div class="tf-state tf-state--error" role="alert">'
        f'<div class="tf-state__icon">{icon(icon_name, 32)}</div>'
        f'<div class="tf-state__title">{escape(title)}</div>{b}</div>'
    )


def grounding_note(text: str, color: str = AZURE_BLUE, icon_name: Optional[str] = None) -> str:
    """A small per-agent 'Grounding: …' label, coloured by its IQ layer."""
    ico = icon(icon_name, 15) if icon_name else ""
    return f'<div class="tf-grounding" style="--g:{color}">{ico}<span>{escape(text)}</span></div>'


def muted_panel(body: str = "", *, title: Optional[str] = None, body_html: Optional[str] = None) -> str:
    """A muted secondary panel (e.g. an agent rationale).

    ``body`` is **escaped** by default; pass ``body_html`` for author-controlled
    raw markup (e.g. already-safe component HTML). ``title`` renders as an
    escaped bold lead-in.
    """
    head = f"<strong>{escape(title)}</strong><br>" if title else ""
    inner = body_html if body_html is not None else escape(body)
    return f'<div class="tf-panel">{head}{inner}</div>'


def status_banner(
    title: str,
    body: str = "",
    *,
    body_html: Optional[str] = None,
    accent: str = AZURE_BLUE,
    icon_name: str = "mcp",
) -> str:
    """A connection/status banner. ``title`` and ``body`` are escaped; pass
    ``body_html`` for author-controlled raw markup chrome."""
    inner = body_html if body_html is not None else escape(body)
    return (
        f'<div class="tf-banner" style="--banner-accent:{accent}" role="status">'
        f'<div class="tf-banner__icon">{icon(icon_name, 22)}</div>'
        f'<div><div class="tf-banner__title">{escape(title)}</div>'
        f'<div class="tf-banner__body">{inner}</div></div></div>'
    )
