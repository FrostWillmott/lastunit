import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useOrdersStore } from './orders'

const realtime = vi.hoisted(() => ({ on: vi.fn(), onReconnect: vi.fn() }))
vi.mock('../composables/useRealtime', () => ({
  useRealtime: () => ({
    on: realtime.on,
    onReconnect: realtime.onReconnect,
    status: { value: 'OPEN' },
  }),
}))

const ORDER = {
  id: 1,
  reservation_id: 2,
  sale_id: 3,
  amount_minor: 1000,
  status: 'pending',
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

describe('orders store', () => {
  it('fetchOrders populates the list', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok(200, [ORDER])))
    const store = useOrdersStore()

    await store.fetchOrders()

    expect(store.orders).toHaveLength(1)
    expect(store.orders[0]?.status).toBe('pending')
  })

  it('applyEvent refetches on order_status and reflects a paid order', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(ok(200, [ORDER]))
      .mockResolvedValueOnce(ok(200, [{ ...ORDER, status: 'paid' }]))
    vi.stubGlobal('fetch', fetch)
    const store = useOrdersStore()
    await store.fetchOrders()
    expect(store.orders[0]?.status).toBe('pending')

    await store.applyEvent('order_status')

    expect(fetch).toHaveBeenCalledTimes(2)
    expect(store.orders[0]?.status).toBe('paid')
  })

  it('applyEvent refetches on a cancellation carried by stock_changed', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(ok(200, [ORDER]))
      .mockResolvedValueOnce(ok(200, [{ ...ORDER, status: 'cancelled' }]))
    vi.stubGlobal('fetch', fetch)
    const store = useOrdersStore()
    await store.fetchOrders()

    await store.applyEvent('stock_changed')

    expect(fetch).toHaveBeenCalledTimes(2)
    expect(store.orders[0]?.status).toBe('cancelled')
  })

  it('bindRealtime subscribes to all events and reconnect, once', () => {
    const store = useOrdersStore()

    store.bindRealtime()
    store.bindRealtime()

    expect(realtime.on).toHaveBeenCalledWith('order_status', expect.any(Function))
    expect(realtime.on).toHaveBeenCalledWith('stock_changed', expect.any(Function))
    expect(realtime.on).toHaveBeenCalledWith('sale_status', expect.any(Function))
    expect(realtime.onReconnect).toHaveBeenCalledWith(expect.any(Function))
    expect(realtime.on).toHaveBeenCalledTimes(3)
    expect(realtime.onReconnect).toHaveBeenCalledTimes(1)
  })
})
