---
name: frontend
description: Client-side correctness, accessibility, and performance pass for `review-changes`.
---

# Frontend

Use this profile only inside `review-changes`. Activate when the diff changes
`*.tsx`, `*.jsx`, `*.vue`, `*.svelte`, `*.css`, or the components, styles,
interaction logic, or client data fetching in them.

Parity note: apply the same evidence bar here as `backend.md`. A finding needs a
concrete interaction or state that produces a wrong or unusable result.

## Scope

**State and rendering**
- Derived state stored instead of computed, so the two can disagree
- An effect whose dependency list omits a value it reads, or includes one that
  makes it loop
- A key derived from an array index on a reorderable list
- A subscription, timer, listener, or observer with no teardown
- State updated after unmount on an async path

**Data fetching**
- A request fired per render or per keystroke with no debounce or cancellation
- Loading, empty, and error branches missing where the diff introduces a fetch
- A stale response overwriting a newer one when requests can interleave

**Accessibility**
- An interactive element with no accessible name
- A control reachable by mouse only: `div` or `span` with a click handler and no
  role, `tabindex`, or key handler
- Focus outline removed with no visible replacement
- State conveyed by color alone
- A modal, drawer, or menu with no focus trap and no restore on close

**Layout and responsiveness**
- A fixed width or height that overflows on a small viewport
- Text that clips or truncates without a title or expansion
- Motion that shifts layout, blocks interaction, or ignores
  `prefers-reduced-motion`

**Client-side security**
- `innerHTML`, `dangerouslySetInnerHTML`, `v-html`, or `{@html}` on any value
  not provably static
- A URL, redirect target, or `src` built from user input with no allowlist
- A token, key, or secret in client code or in a public build-time variable

**Weight**
- A heavy dependency added for a small use, where the repository already has an
  equivalent
- A library imported whole where the repository's bundler config supports
  subpath imports

## Do not flag

- Visual taste, branding, or redesign ideas
- Formatting the configured linter or formatter reports
- Pre-existing issues on lines the diff does not touch
- Speculation about user behavior with no evidence in the changed code

## Output

Per finding: `path`, `line`, `severity`, `interaction_or_state`, `wrong_result`,
`fix`, `confidence`.
