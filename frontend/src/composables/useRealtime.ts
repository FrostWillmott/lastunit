// The one realtime composable: it owns the SSE connection to /api/events and
// its reconnect, and stores subscribe to it — no component ever opens a socket
// itself (frontend-vue rule). Listeners live at module scope so every store
// shares one EventSource and stays subscribed across a logout→login cycle;
// only the EventSource itself is closed (logout) and reopened (login).
//
// Native EventSource rather than VueUse useEventSource on purpose: useEventSource
// exposes only "latest value" refs (event/data are shallowRefs), so watching the
// event name drops two consecutive same-named events (two stock_changed in a row
// would deliver one callback). addEventListener fires per event, which is what
// live updates need. The browser's EventSource auto-reconnects, so no retry loop
// is needed here (see DECISIONS.md).

export const REALTIME_EVENTS = [
  'stock_changed',
  'sale_status',
  'order_status',
  'sale_stats',
] as const
export type RealtimeEvent = (typeof REALTIME_EVENTS)[number]

type Listener = (data: unknown) => void

export interface Realtime {
  on(event: RealtimeEvent, listener: Listener): void
  onReconnect(listener: () => void): void
}

const listeners = new Map<RealtimeEvent, Set<Listener>>()
const reconnectListeners = new Set<() => void>()
let source: EventSource | null = null

function parse(data: string): unknown {
  try {
    return JSON.parse(data)
  } catch {
    return null
  }
}

function open(): void {
  if (source) return
  const src = new EventSource('/api/events')

  for (const name of REALTIME_EVENTS) {
    src.addEventListener(name, (event: MessageEvent) => {
      const payload = parse(event.data)
      for (const listener of listeners.get(name) ?? []) listener(payload)
    })
  }

  // The first open is the initial connection; each later open is a reconnect,
  // so refetch before resuming the stream (a missed event is never shown).
  let opened = false
  src.onopen = () => {
    if (opened) {
      for (const listener of reconnectListeners) listener()
    }
    opened = true
  }

  source = src
}

export function useRealtime(): Realtime {
  open()
  return {
    on(event, listener) {
      const set = listeners.get(event) ?? new Set<Listener>()
      set.add(listener)
      listeners.set(event, set)
    },
    onReconnect(listener) {
      reconnectListeners.add(listener)
    },
  }
}

// Closes the EventSource (logout) without dropping the subscribed listeners, so
// the next openRealtime() re-attaches them to a fresh connection.
export function closeRealtime(): void {
  source?.close()
  source = null
}

export function openRealtime(): void {
  open()
}
