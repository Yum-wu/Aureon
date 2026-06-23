# Aureon Design System

This is a draft project design system for the current Canvas workspace.

Approval status: pending user review. Do not treat this file as the final production standard until the user approves the showcase.

Reference source: none selected. This draft is derived from the chosen visual direction and must be reviewed before reuse.
Visual direction: `dense-enterprise` - Dense Enterprise.
## Product-Fit Intelligence

- Matched category: `General`
- Recommended pattern: `not specified`
- Style priority: `not specified`
- Color mood: `not specified`
- Typography mood: `not specified`
- Key effects: `subtle state transitions only`

Anti-patterns to avoid:

- Generic AI styling, placeholder content, inaccessible contrast, and ungrounded metrics.

UX checks:

- Maintain visible focus, labels, loading feedback, and responsive constraints.




## Visual Theme & Atmosphere

Use a coherent product interface language that supports the current artifact instead of a generic visual theme. The design should feel production-ready, inspectable, and stable across revisions.

- dense tables, filters, sidebars, and inspectable detail panes
- small headings inside panels, no hero-scale typography
- status pills with restrained tinted backgrounds
- predictable navigation over editorial composition

## Color Palette & Roles

- Background: `oklch(98% 0.005 250)`
- Surface: `oklch(100% 0 0)`
- Foreground: `oklch(22% 0.02 240)`
- Muted text: `oklch(50% 0.018 240)`
- Border: `oklch(90% 0.008 240)`
- Accent: `oklch(58% 0.16 145)`

Use semantic roles from `design-system.css` instead of raw colors in page code.

## Typography Rules

- Display font: `-apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', system-ui, sans-serif`
- Body font: `-apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', system-ui, sans-serif`
- Mono font: `'JetBrains Mono', 'IBM Plex Mono', ui-monospace, Menlo, monospace`
- Keep letter spacing at `0`.
- Use compact headings inside tools, panels, cards, and dense product surfaces.

## Token Architecture

Use a three-layer token model:

1. Primitive tokens define raw values, such as `--primitive-color-bg` and `--primitive-space-4`.
2. Semantic tokens define product roles, such as `--color-bg`, `--color-accent`, and `--spacing-md`.
3. Component tokens define implementation contracts, such as `--button-bg`, `--card-padding`, and `--input-border`.

Components must consume semantic or component tokens, not raw hex values.

## Component Stylings

- Components must expose meaningful `data-component` attributes.
- Reusable styling should flow through `design-system.css` tokens.
- Component variants belong in `design-system.json` when they should appear in the Canvas component panel.
- Avoid one-off inline values unless they express layout unique to the artifact.
- Every interactive component must define default, hover, focus, active, disabled, and loading states.

## Layout Principles

- Prefer stable responsive constraints: grid tracks, fixed-format control dimensions, aspect ratios, and min/max widths.
- Keep primary workflows visible without marketing-page padding unless the artifact is explicitly a landing page.
- Use whitespace to clarify scanning and comparison, not as decoration.

## Depth & Elevation

- Use elevation sparingly for focus, overlays, and repeated cards.
- Default product surfaces should rely on borders and tokenized backgrounds before heavy shadows.
- Do not layer cards inside cards unless the inner card is a repeated item or modal content.

## Do's and Don'ts

Do:

- Build from real user intent and selected workflow constraints.
- Preserve production handoff paths for HTML and React + Vite.
- Lint the artifact before handoff.

Don't:

- landing-page hero sections
- large decorative imagery
- soft lifestyle tone

## Responsive Behavior

- Define the intended desktop, tablet, and mobile frames before final layout.
- Preserve touch target sizes on mobile.
- Prevent text overlap and truncation in buttons, tabs, cards, and toolbar controls.
- Use media queries only where layout behavior genuinely changes.

## Agent Prompt Guide

When generating or refining this workspace:

1. Read this `DESIGN.md`, `design-system.css`, and `design-system.json` before editing HTML.
2. Ask blocking questions through the design questions workflow when required decisions are missing.
3. Keep Canvas rendering HTML-first unless the user asks for React + Vite export.
4. Do not introduce Next.js structure unless the user explicitly requests it.
5. After major edits, run Canvas artifact lint and fix P0/P1 issues before handoff.
