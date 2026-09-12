import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// jsdom has no EventSource, so the test supplies a fake and drives it directly.
// The module-level singleton in useRealtime means each test re-imports the
// module (vi.resetModules) to get a fresh connection.
class FakeEventSource {
  static instances: FakeEventSource[] = []
  url: string
  onopen: (() => void) | null = null
  closed = false
  private listeners = new Map<string, ((event: MessageEvent) => void)[]>()

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  addEventListener(type: string, handler: (event: MessageEvent) => void): void {
    const arr = this.listeners.get(type) ?? []
    arr.push(handler)
    this.listeners.set(type, arr)
  }

  emit(type: string, data: unknown): void {
    this.emitRaw(type, JSON.stringify(data))
  }

  emitRaw(type: string, raw: string): void {
    for (const handler of this.listeners.get(type) ?? []) {
      handler({ data: raw } as MessageEvent)
    }
  }

  open(): void {
    this.onopen?.()
  }

  close(): void {
    this.closed = true
  }
}

beforeEach(() => {
  FakeEventSource.instances = []
  vi.stubGlobal('EventSource', FakeEventSource)
  vi.resetModules()
})
afterEach(() => vi.unstubAllGlobals())

async function freshRealtime() {
  const { useRealtime } = await import('./useRealtime')
  const rt = useRealtime()
  return { rt, source: FakeEventSource.instances[0]! }
}

describe('useRealtime', () => {
  it('routes a named event to its listener with parsed data', async () => {
    const { rt, source } = await freshRealtime()
    const handler = vi.fn()
    rt.on('stock_changed', handler)

    source.emit('stock_changed', { sale_id: 1 })

    expect(handler).toHaveBeenCalledWith({ sale_id: 1 })
  })

  it('delivers two same-named events in a row', async () => {
    const { rt, source } = await freshRealtime()
    const handler = vi.fn()
    rt.on('stock_changed', handler)

    source.emit('stock_changed', { sale_id: 1 })
    source.emit('stock_changed', { sale_id: 2 })

    expect(handler).toHaveBeenCalledTimes(2)
    expect(handler).toHaveBeenNthCalledWith(2, { sale_id: 2 })
  })

  it('routes different events to their own listeners', async () => {
    const { rt, source } = await freshRealtime()
    const stock = vi.fn()
    const order = vi.fn()
    rt.on('stock_changed', stock)
    rt.on('order_status', order)

    source.emit('order_status', { order_id: 7, status: 'paid' })

    expect(order).toHaveBeenCalledWith({ order_id: 7, status: 'paid' })
    expect(stock).not.toHaveBeenCalled()
  })

  it('refetches on reconnect but not the initial open', async () => {
    const { rt, source } = await freshRealtime()
    const refetch = vi.fn()
    rt.onReconnect(refetch)

    source.open() // initial connection
    expect(refetch).not.toHaveBeenCalled()

    source.open() // reconnect
    expect(refetch).toHaveBeenCalledTimes(1)
  })

  it('passes null for non-JSON event data', async () => {
    const { rt, source } = await freshRealtime()
    const handler = vi.fn()
    rt.on('stock_changed', handler)

    source.emitRaw('stock_changed', 'not json')

    expect(handler).toHaveBeenCalledWith(null)
  })

  it('closeRealtime closes the source and openRealtime opens a fresh one', async () => {
    const { closeRealtime, openRealtime } = await import('./useRealtime')
    const { source } = await freshRealtime()

    closeRealtime()
    expect(source.closed).toBe(true)

    openRealtime()
    expect(FakeEventSource.instances).toHaveLength(2)
    expect(FakeEventSource.instances[1]!.closed).toBe(false)
  })

  it('keeps listeners subscribed across a close/reopen', async () => {
    const { useRealtime, closeRealtime, openRealtime } = await import('./useRealtime')
    const rt = useRealtime()
    const handler = vi.fn()
    rt.on('stock_changed', handler)

    closeRealtime()
    openRealtime()

    FakeEventSource.instances[1]!.emit('stock_changed', { sale_id: 1 })
    expect(handler).toHaveBeenCalledWith({ sale_id: 1 })
  })
})
