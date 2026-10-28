# ADR-0006: Small in-repo UI kit instead of shadcn/ui; no Framer Motion

- **Status:** accepted · 2026-10-28

## Context
The spec lists shadcn/ui and (restrained) Framer Motion.

## Decision
Use a small set of accessible Tailwind components in `apps/web/src/components/ui.tsx` (Button, Field, Modal with focus trap, Badge, ProgressBar, QueryView…) driven by CSS-variable design tokens in `src/index.css` (light and dark themes). Motion is limited to CSS transitions, which are disabled under `prefers-reduced-motion`.

## Consequences
Fewer dependencies and a smaller bundle. Components are maintained by hand. Adopting shadcn later is mechanical, because the tokens already map onto Tailwind colours.
