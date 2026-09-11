import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useShopStore } from './shop'

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
  available: 2,
  starts_at: '2026-01-01T00:00:00Z',
  ends_at: '2026-01-01T01:00:00Z',
  timezone: 'Europe/Moscow',
  phase: 'active',
  server_now: '2026-01-01T00:30:00Z',
}

const STATS = {
  available: 2,
  sold: 3,
  in_cart: 1,
  revenue_minor: 3000,
  pending_payments: [
    { provider_ref: 'ref-1', order_id: 7, requested_at: '2026-01-01T00:29:00Z' },
  ],
}

function ok(status: number, body: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => body }
}

beforeEach(() => {
  setActivePinia(createPinia())
  realtime.on.mockClear()
  realtime.onReconnect.mockClear()
})
afterEach(() => vi.unstubAllGlobals())

describe('shop store', () => {
  it('fetchSales populates the sale list', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok(200, [SALE])))
    const store = useShopStore()

    await store.fetchSales()

    expect(store.sales).toHaveLength(1)
    expect(store.sales[0]?.available).toBe(2)
  })

  it('fetchStats selects the sale and stores its stats', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok(200, STATS)))
    const store = useShopStore()

    await store.fetchStats(1)

    expect(store.selectedSaleId).toBe(1)
    expect(store.stats?.sold).toBe(3)
    expect(store.stats?.pending_payments).toHaveLength(1)
  })

  it('createSale posts the input then refetches the list', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(ok(201, SALE))
      .mockResolvedValueOnce(ok(200, [SALE]))
    vi.stubGlobal('fetch', fetch)
    const store = useShopStore()
    const input = {
      title: 'Sneakers',
      price_minor: 1000,
      quantity: 5,
      timezone: 'Europe/Moscow',
      starts_at: '2026-01-01T03:00',
      ends_at: '2026-01-01T04:00',
    }

    await store.createSale(input)

    expect(fetch).toHaveBeenCalledWith(
      '/api/sales',
      expect.objectContaining({ method: 'POST', body: JSON.stringify(input) }),
    )
    expect(store.sales).toHaveLength(1)
  })

  it('checkPayment posts then refreshes the selected sale stats', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(ok(200, { status: 'approved' }))
      .mockResolvedValueOnce(ok(200, { ...STATS, pending_payments: [] }))
    vi.stubGlobal('fetch', fetch)
    const store = useShopStore()
    store.selectedSaleId = 1

    await store.checkPayment('ref-1')

    expect(fetch).toHaveBeenCalledWith(
      '/api/shop/payments/ref-1/check',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(fetch).toHaveBeenCalledTimes(2)
    expect(store.stats?.pending_payments).toHaveLength(0)
  })

  it('applyEvent refetches sales and the selected stats', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(ok(200, STATS))
      .mockResolvedValueOnce(ok(200, [{ ...SALE, available: 1 }]))
      .mockResolvedValueOnce(ok(200, { ...STATS, available: 1 }))
    vi.stubGlobal('fetch', fetch)
    const store = useShopStore()
    await store.fetchStats(1)

    await store.applyEvent('stock_changed')

    expect(fetch).toHaveBeenCalledTimes(3)
    expect(store.stats?.available).toBe(1)
  })

  it('bindRealtime subscribes to stock/sale events and reconnect, once', () => {
    const store = useShopStore()

    store.bindRealtime()
    store.bindRealtime()

    expect(realtime.on).toHaveBeenCalledWith('stock_changed', expect.any(Function))
    expect(realtime.on).toHaveBeenCalledWith('sale_status', expect.any(Function))
    expect(realtime.onReconnect).toHaveBeenCalledWith(expect.any(Function))
    expect(realtime.on).toHaveBeenCalledTimes(2)
    expect(realtime.onReconnect).toHaveBeenCalledTimes(1)
  })
})
