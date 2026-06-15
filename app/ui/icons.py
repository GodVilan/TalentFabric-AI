"""
Inline Fluent icon helper.

Vendored from Microsoft's **Fluent UI System Icons** (MIT — see
``icons/LICENSE`` and ``icons/ATTRIBUTION.md``), pinned to a fixed version for
reproducibility. The raw SVGs carry no ``fill`` attribute (they default to
black); :func:`icon` rebuilds the ``<svg>`` tag with ``fill="currentColor"`` so
icons inherit the surrounding design-system token colour, plus sizing and ARIA.

Concepts with no vendored icon fall back to a clean text label — never emoji.
"""

from __future__ import annotations

import re
from functools import lru_cache
from html import escape
from pathlib import Path

ICONS_DIR = Path(__file__).resolve().parent / "icons"

_SVG_OPEN = re.compile(r"<svg\b[^>]*>", re.IGNORECASE)
_VIEWBOX = re.compile(r'viewBox="([^"]+)"', re.IGNORECASE)


@lru_cache(maxsize=128)
def _load_raw(name: str) -> str | None:
    path = ICONS_DIR / f"{name}.svg"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def has_icon(name: str) -> bool:
    return (ICONS_DIR / f"{name}.svg").exists()


def icon(name: str, size: int = 18, label: str | None = None, cls: str = "tf-icon") -> str:
    """Return an inline SVG string for ``name`` (token-coloured via currentColor).

    Args:
        name: logical icon name (file ``app/ui/icons/<name>.svg``).
        size: rendered px width/height (viewBox is preserved).
        label: accessible label. If given, the icon is exposed to AT
            (``role="img"``); if omitted, it is decorative (``aria-hidden``).
        cls: CSS class applied to the ``<svg>``.
    """
    raw = _load_raw(name)
    if raw is None:
        text = escape(label or name.replace("_", " "))
        return f'<span class="tf-icon-fallback" aria-label="{text}">{text}</span>'

    vb_match = _VIEWBOX.search(raw)
    viewbox = vb_match.group(1) if vb_match else "0 0 24 24"
    inner = _SVG_OPEN.sub("", raw, count=1).replace("</svg>", "").strip()

    if label:
        aria = f'role="img" aria-label="{escape(label)}"'
    else:
        aria = 'aria-hidden="true"'

    return (
        f'<svg class="{cls}" width="{size}" height="{size}" viewBox="{viewbox}" '
        f'fill="currentColor" focusable="false" xmlns="http://www.w3.org/2000/svg" {aria}>'
        f"{inner}</svg>"
    )
