# Frontend conventions (Vue 3 + TypeScript)

Apply to the `frontend/` surface of a client-server project. Rule levels are
defined in `_LEVELS.md`. The mechanical half (formatting, template lint) is
`eslint-plugin-vue` + Prettier via `npm run check` — not restated here.

Why this module exists: Vue has two public styles (Options API, Composition
API) and two major versions still in the training data. Left alone, an agent
mixes them in one codebase, and a reviewer who knows Vue spots it in the first
file. Pinning one style removes the whole class of "which Vue is this" review
comments.

## One style: `<script setup lang="ts">` + Composition API  [MUST]
- Every component is a single-file `.vue` with `<script setup lang="ts">`.
  No Options API (`export default { data() ... }`), no `defineComponent` with
  options, no mixins, no `this`.
- Props and emits are typed: `defineProps<{ ... }>()`, `defineEmits<{ ... }>()`.
  No runtime prop objects when a type will do.
- Reactivity is explicit: `ref`/`reactive`/`computed`. Don't reach for
  `watch` when a `computed` expresses the dependency; when you do `watch`,
  say what side effect justifies it.

## State: Pinia stores, one per domain concept  [MUST]
- Shared or realtime state (the thing several views and the WebSocket touch)
  lives in a Pinia store, setup-style (`defineStore('notes', () => { ... })`).
  Components hold only local UI state.
- The store is the only place that calls the API client and applies socket
  events; components call store actions and render store state. This is what
  makes "two tabs show the same thing" testable in one place.
- No global mutable singletons outside Pinia; no `provide/inject` for app
  state (fine for a theme or a form context).

## API client is one typed module  [MUST]
- `src/api/` (or `src/api.ts`) wraps `fetch` with the `/api` prefix, typed
  request/response shapes, and one error type. Components never call `fetch`
  directly. Types mirror the backend's Pydantic response models; when the
  backend publishes OpenAPI, generate them rather than hand-writing.
- Realtime: one `useRealtime()` composable (VueUse `useWebSocket`/`useEventSource`
  is fine) owns the connection, reconnect and "refetch on reconnect"; stores
  subscribe to it. Never open a socket inside a component.

## Templates  [MUST]
- `v-for` always has a stable `:key` (an id, never the index).
- No business logic in templates: anything beyond a property access or a
  simple ternary becomes a `computed`.
- Text the user sees lives in the template or a messages module, not built
  with string concatenation in script.

## Tests  [MUST]
- Vitest + `@vue/test-utils`; `src/**/*.test.ts` next to the unit under test.
- Mock at the boundary (`fetch`, the socket, the clock with `vi.useFakeTimers`),
  never Pinia internals — use `createTestingPinia` or a real store.
- Assert on rendered text / attributes, not on component internals.
- A store that applies realtime events has a test that feeds it two events
  and asserts the resulting state — that is the frontend half of the
  "two clients" proof.

## Preferred defaults  [PREFER]
- `<script setup>` first, `<template>` second, `<style scoped>` last, in that
  order in every file.
- Vue Router with typed route names; lazy-load route components.
- Prefer VueUse composables over hand-rolled ones for browser APIs
  (`useLocalStorage`, `useIntervalFn`, `useWebSocket`).
- Component names are multi-word (`NoteCard`, not `Note`) — the lint rule
  exists because single-word names collide with HTML elements.
