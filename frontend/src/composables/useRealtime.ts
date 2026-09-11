import { watch, type ShallowRef } from 'vue'
import { useEventSource, type EventSourceStatus } from '@vueuse/core'

// The one realtime composable: it owns the SSE connection to /api/events and
// its reconnect, and stores subscribe to it — no component ever opens a socket
// itself (frontend-vue rule). The connection is a module singleton so every
// store shares one EventSource.

export const REALTIME_EVENTS = ['stock_changed', 'sale_status', 'order_status'] as const
export type RealtimeEvent = (typeof REALTIME_EVENTS)[number]

type Listener = (data: unknown) => void

interface RealtimeConnection {
  status: Readonly<ShallowRef<EventSourceStatus>>
  listeners: Map<RealtimeEvent, Set<Listener>>
  reconnectListeners: Set<() => void>
}

export interface Realtime {
  on(event: RealtimeEvent, listener: Listener): void
  onReconnect(listener: () => void): void
  status: Readonly<ShallowRef<EventSourceStatus>>
}

let connection: RealtimeConnection | null = null

export function useRealtime(): Realtime {
  if (!connection) {
    const { event, data, status } = useEventSource(
      '/api/events',
      [...REALTIME_EVENTS],
      {
        autoReconnect: { retries: -1, delay: 1000 },
      },
    )
    const listeners = new Map<RealtimeEvent, Set<Listener>>()
    const reconnectListeners = new Set<() => void>()

    // Named SSE events arrive as (event name, parsed JSON data); fan out to the
    // listeners registered for that name.
    watch(event, (name) => {
      if (!name) return
      for (const listener of listeners.get(name) ?? []) listener(data.value)
    })

    // After a reconnect the client refetches before resuming the stream, so a
    // missed event never leaves a stale screen.
    watch(status, (current, previous) => {
      if (current === 'OPEN' && previous !== 'OPEN') {
        for (const listener of reconnectListeners) listener()
      }
    })

    connection = { status, listeners, reconnectListeners }
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
    status: conn.status,
  }
}
