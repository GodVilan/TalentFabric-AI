# TalentFabric AI — UI design system

A small, self-contained Fluent 2 / Microsoft Learn design system for the
Streamlit app. **Presentation only** — nothing here imports from `src/`; the
agent/workflow/data layers are never touched by the UI.

```
app/ui/
  theme.py        # design tokens, authored CSS, Plotly template, @font-face
  components.py   # reusable HTML-string components (consume tokens, never raw hex)
  icons.py        # icon(name, size, label) -> inline Fluent SVG
  fonts/          # Inter Variable woff2 (SIL OFL) + OFL.txt
  icons/          # vendored Fluent UI System Icons (MIT) + LICENSE + ATTRIBUTION.md
```

The app entry point (`app/streamlit_app.py`) injects the CSS once
(`st.markdown(inject_css(), unsafe_allow_html=True)`) and renders components via
`st.markdown(component(...), unsafe_allow_html=True)`.

---

## Tokens (`theme.py`)

Defined once as CSS custom properties (`:root`) **and** as a Python mirror
(for Plotly, which can't read CSS). Never hard-code hex in a page or component —
use a token.

| Group | Examples |
|---|---|
| Color — accent | `--color-accent` `#0078D4`, `--color-accent-hover`, `--color-accent-deep`, `--color-accent-subtle`, `--color-cyan`, `--color-purple` |
| Color — status | `--success`, `--success-subtle`, `--warning`, `--danger`, `--danger-subtle` |
| Color — surfaces | `--surface`, `--app-bg` `#F3F2F1`, `--rail-bg` `#1B1A19`, `--border-subtle` |
| Color — text | `--text-1` `#323130`, `--text-2`, `--text-on-dark`, `--text-muted-on-dark` (AA-safe) |
| Provenance | `--tier-synthetic` (purple), `--tier-public` (accent) |
| Spacing | `--space-1`…`--space-8` (4px scale) |
| Radius | `--radius-sm/md/lg` = 4 / 8 / 12 |
| Elevation | `--elev-resting/raised/overlay` |
| Motion | `--motion-fast` 120ms, `--motion-med` 200ms, `--ease-fluent` |

**Typography.** Stack: `"Segoe UI Variable", "Segoe UI", "Inter", system-ui,
-apple-system, Roboto, sans-serif`. Segoe is native on Windows (never bundled —
proprietary); **Inter** is vendored locally (SIL OFL) and base64-embedded via
`@font-face` so the demo is fully offline.

**Plotly.** `register_plotly_template()` registers the `talentfabric` template
(font, colorway, transparent paper bg, token gridlines) and sets it as the
default, so every chart inherits the theme. Import `ui.theme` and charts are
themed automatically.

### Accessibility helpers
`contrast_ratio(a, b)`, `best_text_on(bg)` (black/white pick for pills), and
`text_safe_on_white(color)` (AA-safe foreground for badges) keep text ≥ 4.5:1.
The bright brand teal/orange fail AA for small text, so `*_STRONG` variants
(`SUCCESS_STRONG`, `WARN_STRONG`, `CYAN_STRONG`) are used for text while the
bright colours stay for fills/icons/charts.

---

## Components (`components.py`)

All return an HTML string; render with
`st.markdown(component(...), unsafe_allow_html=True)`.

| Component | Purpose |
|---|---|
| `card(body, *, accent, title, icon_name, hover)` | Fluent surface card (raw HTML body) |
| `info_card(title, desc, *, accent, icon_name)` | Titled card with muted description |
| `metric_tile(value, label, color)` | KPI tile |
| `pill(text, color, icon_name)` / `status_pill` / `risk_pill` | Status pills — icon + text, AA-safe auto text colour |
| `badge(text, *, fg, icon_name)` | Small tag — AA-safe foreground |
| `provenance_badge(tier)` | `synthetic-internal` vs `microsoft-learn-public` |
| `section_header(title, icon_name)` / `page_header(title, icon_name)` | Headers with icons |
| `citation_chip(text, url, icon_name)` | Monospace cited-source chip (optional link) |
| `grounding_note(text, color, icon_name)` | Per-agent "Grounding: …" label |
| `muted_panel(html)` | Secondary panel (rationale, reconciliation) |
| `empty_state` / `error_state` / `status_banner` | Intentional empty / error / connection states |

**Conventions.** Per-call colours are passed as CSS-var bindings
(`style="--card-accent:…"`), not style soup. Text passed to components is
HTML-escaped; `body`/`*_html` params are treated as raw and are caller-controlled.

---

## Icons (`icons.py`)

`icon(name, size=18, label=None, cls="tf-icon")` reads `icons/<name>.svg`,
rebuilds the `<svg>` with `fill="currentColor"` (inherits token colour) + sizing
+ ARIA (`role="img"`+`aria-label` when `label` is given, else `aria-hidden`).
Missing names fall back to a clean text label — never emoji.

Icons are a vendored subset of **Microsoft Fluent UI System Icons** (MIT),
pinned to `@fluentui/svg-icons` **1.1.330** — see `icons/LICENSE` and
`icons/ATTRIBUTION.md`. To add one: download `<name>_<size>_regular.svg` from
that pinned version, save it as `icons/<logical_name>.svg`, and reference it by
`<logical_name>`.

---

## Conventions & guardrails

- **No raw hex** in pages/components — use a token (CSS var or Python constant).
- **Offline-safe** — all fonts/icons vendored locally; no CDN at runtime.
- **Accessibility** — status carries text + icon (not colour-only); custom HTML
  blocks carry ARIA roles/labels; transitions respect `prefers-reduced-motion`.
- **Trademark** — Fluent design + icons used legitimately (MIT); no Microsoft
  logos/wordmarks/cert badges. Microsoft product names are nominative only.
- **Streamlit native widgets** are themed via `.streamlit/config.toml`.
