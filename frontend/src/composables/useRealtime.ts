// The one realtime composable: it owns the SSE connection to /api/events and
// its reconnect, and stores subscribe to it — no component ever opens a socket
// itself (frontend-vue rule). The connection is a module singleton so every
// store shares one EventSource.
//
// Native EventSource rather than VueUse useEventSource on purpose: useEventSource
// exposes only "latest value" refs (event/data are shallowRefs), so watching the
// event name drops two consecutive same-named events (two stock_changed in a row
// would deliver one callback). addEventListener fires per event, which is what
// live updates need. The browser's EventSource auto-reconnects, so no retry loop
// is needed here (see DECISIONS.md).

export const REALTIME_EVENTS = ['stock_changed', 'sale_status', 'order_status'] as const
export type RealtimeEvent = (typeof REALTIME_EVENTS)[number]

type Listener = (data: unknown) => void

interface RealtimeConnection {
  source: EventSource
  listeners: Map<RealtimeEvent, Set<Listener>>
  reconnectListeners: Set<() => void>
}

export interface Realtime {
  on(event: RealtimeEvent, listener: Listener): void
  onReconnect(listener: () => void): void
}

let connection: RealtimeConnection | null = null

function parse(data: string): unknown {
  try {
    return JSON.parse(data)
  } catch {
    return null
  }
}

export function useRealtime(): Realtime {
  if (!connection) {
    const listeners = new Map<RealtimeEvent, Set<Listener>>()
    const reconnectListeners = new Set<() => void>()
    const source = new EventSource('/api/events')

    for (const name of REALTIME_EVENTS) {
      source.addEventListener(name, (event: MessageEvent) => {
        const payload = parse(event.data)
        for (const listener of listeners.get(name) ?? []) listener(payload)
      })
    }

    // The first open is the initial connection; each later open is a reconnect,
    // so refetch before resuming the stream (a missed event is never shown).
    let opened = false
    source.onopen = () => {
      if (opened) {
        for (const listener of reconnectListeners) listener()
      }
      opened = true
    }

    connection = { source, listeners, reconnectListeners }
  }
  const conn = connection
  return {
    on(event, listener) {
      const set = conn.listeners.get(event) ?? new Set<Listener>()
      set.add(listener)
      conn.listeners.set(event, set)
    },
    onReconnect(listener) {
      conn.reconnectListeners.add(listener)
    },
  }
}
