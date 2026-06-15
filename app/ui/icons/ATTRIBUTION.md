# Icon attribution

The SVG icons in this directory are a subset of **Fluent UI System Icons** by
Microsoft, used under the MIT License (see [`LICENSE`](LICENSE)).

- Source: https://github.com/microsoft/fluentui-system-icons
- Package: `@fluentui/svg-icons`
- Pinned version: **1.1.330**
- Style: 24px "regular"

Files are renamed to logical names (e.g. `home_24_regular.svg` → `nav_overview.svg`)
for use via `app/ui/icons.py`'s `icon()` helper. Each icon's `fill` is set to
`currentColor` at render time so it inherits design-system token colours.

This is an independent hackathon submission and is **not affiliated with or
endorsed by Microsoft**. "Fluent", "Microsoft Learn", "Microsoft Foundry", and
"Azure" are referenced nominatively only.
