import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useSalesStore } from './sales'

// The realtime composable is the socket boundary; the store test mocks it so it
// can assert the store wired its events without opening an EventSource.
const realtime = vi.hoisted(() => ({ on: vi.fn(), onReconnect: vi.fn() }))
vi.mock('../composables/useRealtime', () => ({
  useRealtime: () => ({
    on: realtime.on,
    onReconnect: realtime.onReconnect,
    status: { value: 'OPEN' },
  }),
}))

const SALE = {
  id: 1,
  title: 'Sneakers',
  price_minor: 1000,
  quantity: 5,
  available: 5,
  starts_at: '2026-01-01T00:00:00Z',
  ends_at: '2026-01-01T01:00:00Z',
  timezone: 'Europe/Moscow',
  phase: 'active',
  server_now: '2026-01-01T00:30:00Z',
}

function jsonFetch(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  })
}

beforeEach(() => {
  setActivePinia(createPinia())
  realtime.on.mockClear()
  realtime.onReconnect.mockClear()
})
afterEach(() => vi.unstubAllGlobals())

describe('sales store', () => {
  it('fetchSales populates the list and captures the server offset', async () => {
    vi.stubGlobal('fetch', jsonFetch(200, [SALE]))
    const store = useSalesStore()

    await store.fetchSales()

    expect(store.sales).toHaveLength(1)
    expect(store.sales[0]?.title).toBe('Sneakers')
    expect(store.serverOffset).not.toBeNull()
  })

  it('reserve posts to the sale then refetches stock', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 201,
        json: async () => ({
          id: 9,
          sale_id: 1,
          status: 'held',
          expires_at: '2026-01-01T00:40:00Z',
        }),
      })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => [SALE] })
    vi.stubGlobal('fetch', fetch)
    const store = useSalesStore()

    await store.reserve(1)

    expect(fetch).toHaveBeenCalledWith(
      '/api/sales/1/reserve',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(fetch).toHaveBeenCalledTimes(2)
    expect(store.sales).toHaveLength(1)
  })

  it('applyEvent refetches on stock_changed and reflects the new stock', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => [SALE] })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [{ ...SALE, available: 3 }],
      })
    vi.stubGlobal('fetch', fetch)
    const store = useSalesStore()
    await store.fetchSales()
    expect(store.sales[0]?.available).toBe(5)

    await store.applyEvent('stock_changed')

    expect(fetch).toHaveBeenCalledTimes(2)
    expect(store.sales[0]?.available).toBe(3)
  })

  // The frontend half of "two tabs stay in sync": a second client's store
  // applies a stream of stock events and tracks each one, not just the last.
  it('applies two successive stock events and reflects each', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => [SALE] })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [{ ...SALE, available: 4 }],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [{ ...SALE, available: 3 }],
      })
    vi.stubGlobal('fetch', fetch)
    const store = useSalesStore()
    await store.fetchSales()
    expect(store.sales[0]?.available).toBe(5)

    await store.applyEvent('stock_changed')
    expect(store.sales[0]?.available).toBe(4)

    await store.applyEvent('stock_changed')
    expect(store.sales[0]?.available).toBe(3)
    expect(fetch).toHaveBeenCalledTimes(3)
  })

  it('ignores a stale response that resolves after a newer one', async () => {
    type FakeResponse = { ok: boolean; status: number; json: () => Promise<unknown> }
    let resolveFirst!: (v: FakeResponse) => void
    let resolveSecond!: (v: FakeResponse) => void
    const first = new Promise<FakeResponse>((resolve) => {
      resolveFirst = resolve
    })
    const second = new Promise<FakeResponse>((resolve) => {
      resolveSecond = resolve
    })
    vi.stubGlobal(
      'fetch',
      vi.fn().mockReturnValueOnce(first).mockReturnValueOnce(second),
    )
    const store = useSalesStore()

    const older = store.fetchSales()
    const newer = store.fetchSales()

    resolveSecond({
      ok: true,
      status: 200,
      json: async () => [{ ...SALE, available: 3 }],
    })
    await newer
    resolveFirst({
      ok: true,
      status: 200,
      json: async () => [{ ...SALE, available: 5 }],
    })
    await older

    expect(store.sales[0]?.available).toBe(3)
  })

  it('applyEvent ignores unrelated events', async () => {
    const fetch = jsonFetch(200, [SALE])
    vi.stubGlobal('fetch', fetch)
    const store = useSalesStore()
    await store.fetchSales()

    await store.applyEvent('order_status')

    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('applyEvent swallows a refetch failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('down')))
    const store = useSalesStore()

    await expect(store.applyEvent('stock_changed')).resolves.toBeUndefined()
  })

  it('bindRealtime subscribes to stock/sale events and reconnect, once', () => {
    const store = useSalesStore()

    store.bindRealtime()
    store.bindRealtime()

    expect(realtime.on).toHaveBeenCalledWith('stock_changed', expect.any(Function))
    expect(realtime.on).toHaveBeenCalledWith('sale_status', expect.any(Function))
    expect(realtime.onReconnect).toHaveBeenCalledWith(expect.any(Function))
    expect(realtime.on).toHaveBeenCalledTimes(2)
    expect(realtime.onReconnect).toHaveBeenCalledTimes(1)
  })
})
