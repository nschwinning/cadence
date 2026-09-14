---
name: react-component-scaffold
description: Scaffold a typed React component for the Cadence frontend — component file, typed props, Tailwind styling, TanStack Query hooks where data is involved, and a Vitest + React Testing Library test. Use when creating a new component, page, or data-driven view.
metadata:
  author: cadence
  version: "1.0"
---

Scaffold a new React + TypeScript component following project structure and the Vite + React Query + Tailwind stack.

## Before generating
1. Read an existing component to match folder structure, naming, import style, and how hooks/query keys are organized. Discover the layout — don't assume `src/components/...`.
2. Determine: is this presentational (props only) or data-driven (fetches server state)?

## What to generate
- **Component** (`<Name>.tsx`): function component with a typed props interface. No `any`. Styling via Tailwind utility classes; use design tokens/config classes where the `designer` has defined them. Semantic, accessible markup (roles, labels, focusable controls).
- **Data (if applicable):** a typed `useQuery`/`useMutation` hook with a typed query key and the shared fetch client — not raw `fetch` in the component. Handle **loading, error, and empty** states explicitly.
- **Test** (`<Name>.test.tsx`): Vitest + React Testing Library. Query by role/label/text. Mock the API layer (e.g. MSW or the shared client), not the network. Assert the rendered behavior a user sees.

## Conventions to enforce
- Strict types on props, query results, and event handlers.
- Small, composable components; lift shared logic into hooks.
- Every data view renders sensibly while loading, on error, and when empty.

## After generating
- Run `vitest` for the new test and report the actual result.
- Summarize files created and any new API endpoint the component depends on (flag it for `backend-developer` if missing).
