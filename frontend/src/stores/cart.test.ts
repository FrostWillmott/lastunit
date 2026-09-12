import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useCartStore } from './cart'

const realtime = vi.hoisted(() => ({ on: vi.fn(), onReconnect: vi.fn() }))
vi.mock('../composables/useRealtime', () => ({
  useRealtime: () => ({
    on: realtime.on,
    onReconnect: realtime.onReconnect,
    status: { value: 'OPEN' },
  }),
}))

const CART = {
  server_now: '2026-01-01T00:30:00Z',
  items: [
    {
      reservation_id: 1,
      sale_id: 2,
      title: 'Sneakers',
      price_minor: 1000,
      expires_at: '2026-01-01T00:40:00Z',
    },
  ],
}

const ORDER = {
  id: 10,
  reservation_id: 1,
  sale_id: 2,
  amount_minor: 1000,
  status: 'pending',
}

function ok(status: number, body: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => body }
}

beforeEach(() => {
  setActivePinia(createPinia())
  sessionStorage.clear()
  realtime.on.mockClear()
  realtime.onReconnect.mockClear()
})
afterEach(() => vi.unstubAllGlobals())

describe('cart store', () => {
  it('fetchCart populates the cart and captures the server offset', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok(200, CART)))
    const store = useCartStore()

    await store.fetchCart()

    expect(store.cart?.items).toHaveLength(1)
    expect(store.cart?.items[0]?.title).toBe('Sneakers')
    expect(store.serverOffset).not.toBeNull()
  })

  it('release deletes the reservation then refetches', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(ok(204, null))
      .mockResolvedValueOnce(ok(200, { server_now: '2026-01-01T00:30:00Z', items: [] }))
    vi.stubGlobal('fetch', fetch)
    const store = useCartStore()

    await store.release(1)

    expect(fetch).toHaveBeenCalledWith(
      '/api/reservations/1',
      expect.objectContaining({ method: 'DELETE' }),
    )
    expect(store.cart?.items).toHaveLength(0)
  })

  it('pay creates the order once and pays it, then refetches on approval', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(ok(201, ORDER))
      .mockResolvedValueOnce(ok(200, { status: 'approved' }))
      .mockResolvedValueOnce(ok(200, { server_now: '2026-01-01T00:30:00Z', items: [] }))
    vi.stubGlobal('fetch', fetch)
    const store = useCartStore()

    await store.pay(1, '4242 0000')

    expect(store.checkoutOf(1)?.outcome).toBe('approved')
    expect(store.checkoutOf(1)?.orderId).toBe(10)

    const [orderUrl, orderInit] = fetch.mock.calls[0] as [string, RequestInit]
    expect(orderUrl).toBe('/api/orders')
    expect(orderInit.headers).toMatchObject({ 'Idempotency-Key': expect.any(String) })
    const [payUrl] = fetch.mock.calls[1] as [string, RequestInit]
    expect(payUrl).toBe('/api/orders/10/pay')
    expect(store.cart?.items).toHaveLength(0)
  })

  it('a declined payment reuses the order on retry (no second order)', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(ok(201, ORDER))
      .mockResolvedValueOnce(ok(200, { status: 'declined' }))
      .mockResolvedValueOnce(ok(200, { status: 'approved' }))
      .mockResolvedValueOnce(ok(200, { server_now: '2026-01-01T00:30:00Z', items: [] }))
    vi.stubGlobal('fetch', fetch)
    const store = useCartStore()

    await store.pay(1, '4242 0002')
    expect(store.checkoutOf(1)?.outcome).toBe('declined')

    await store.pay(1, '4242 0000')
    expect(store.checkoutOf(1)?.outcome).toBe('approved')

    const orderCalls = fetch.mock.calls.filter(([url]) => url === '/api/orders')
    expect(orderCalls).toHaveLength(1)
    const payCalls = fetch.mock.calls.filter(([url]) => url === '/api/orders/10/pay')
    expect(payCalls).toHaveLength(2)
  })

  it('adopts the existing order when creating it 409s (second tab)', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(ok(409, { detail: 'reservation already has an order' }))
      .mockResolvedValueOnce(ok(200, [ORDER]))
      .mockResolvedValueOnce(ok(200, { status: 'approved' }))
      .mockResolvedValueOnce(ok(200, { server_now: '2026-01-01T00:30:00Z', items: [] }))
    vi.stubGlobal('fetch', fetch)
    const store = useCartStore()

    await store.pay(1, '4242 0000')

    expect(store.checkoutOf(1)?.outcome).toBe('approved')
    expect(store.checkoutOf(1)?.orderId).toBe(10)
    // The order was created once (the 409 was adopted, not retried)...
    const orderCalls = fetch.mock.calls.filter(([url]) => url === '/api/orders')
    expect(orderCalls).toHaveLength(1)
    // ...and the existing order was paid.
    expect(fetch).toHaveBeenCalledWith('/api/orders/10/pay', expect.any(Object))
  })

  it('a pending outcome leaves the item in the cart', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(ok(201, ORDER))
      .mockResolvedValueOnce(ok(200, { status: 'pending' }))
    vi.stubGlobal('fetch', fetch)
    const store = useCartStore()

    await store.pay(1, '4242 9995')

    expect(store.checkoutOf(1)?.outcome).toBe('pending')
    // No refetch happened: only createOrder + pay were called.
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('applyEvent refetches on order_status', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(ok(200, CART))
      .mockResolvedValueOnce(ok(200, { server_now: '2026-01-01T00:30:00Z', items: [] }))
    vi.stubGlobal('fetch', fetch)
    const store = useCartStore()
    await store.fetchCart()

    await store.applyEvent('order_status')

    expect(fetch).toHaveBeenCalledTimes(2)
    expect(store.cart?.items).toHaveLength(0)
  })

  it('bindRealtime subscribes to order/stock/sale events and reconnect, once', () => {
    const store = useCartStore()

    store.bindRealtime()
    store.bindRealtime()

    expect(realtime.on).toHaveBeenCalledWith('order_status', expect.any(Function))
    expect(realtime.on).toHaveBeenCalledWith('stock_changed', expect.any(Function))
    expect(realtime.on).toHaveBeenCalledWith('sale_status', expect.any(Function))
    expect(realtime.onReconnect).toHaveBeenCalledWith(expect.any(Function))
    expect(realtime.on).toHaveBeenCalledTimes(3)
    expect(realtime.onReconnect).toHaveBeenCalledTimes(1)
  })

  it('a reloaded checkout reuses the persisted order id', async () => {
    sessionStorage.setItem(
      'lastunit:checkouts',
      JSON.stringify({ 1: { key: 'persisted-key', orderId: 10 } }),
    )
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(ok(200, { status: 'approved' }))
      .mockResolvedValueOnce(ok(200, { server_now: '2026-01-01T00:30:00Z', items: [] }))
    vi.stubGlobal('fetch', fetch)
    const store = useCartStore()

    await store.pay(1, '4242 0000')

    expect(store.checkoutOf(1)?.outcome).toBe('approved')
    expect(fetch).not.toHaveBeenCalledWith(
      '/api/orders',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('applyEvent refetches on sale_status', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(ok(200, CART))
      .mockResolvedValueOnce(ok(200, { server_now: '2026-01-01T00:30:00Z', items: [] }))
    vi.stubGlobal('fetch', fetch)
    const store = useCartStore()
    await store.fetchCart()

    await store.applyEvent('sale_status')

    expect(fetch).toHaveBeenCalledTimes(2)
  })
})
