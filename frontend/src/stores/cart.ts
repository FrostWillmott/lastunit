import { ref } from 'vue'
import { defineStore } from 'pinia'
import { api, ApiError } from '../api/client'
import type { Cart } from '../api/types'
import { useRealtime, type RealtimeEvent } from '../composables/useRealtime'

type PaymentOutcome = 'approved' | 'declined' | 'pending'

// Per-reservation checkout state. The idempotency key and the order id are
// created once and reused across retries, so a double click or a "try again"
// never creates a second order (the backend also enforces this, but the client
// does not rely on that alone).
export interface Checkout {
  key: string
  orderId: number | null
  busy: boolean
  outcome: PaymentOutcome | null
  error: string | null
}

// The idempotency key + order id survive a reload in sessionStorage, so a
// "try again" after a decline reuses the existing order instead of creating a
// second one (which the backend's UNIQUE(reservation_id) would reject).
const CHECKOUT_STORAGE = 'lastunit:checkouts'

interface PersistedCheckout {
  key: string
  orderId: number | null
}

function loadCheckouts(): Record<number, Checkout> {
  try {
    const raw = sessionStorage.getItem(CHECKOUT_STORAGE)
    if (!raw) return {}
    const saved = JSON.parse(raw) as Record<string, PersistedCheckout>
    const restored: Record<number, Checkout> = {}
    for (const [id, value] of Object.entries(saved)) {
      restored[Number(id)] = { ...value, busy: false, outcome: null, error: null }
    }
    return restored
  } catch {
    return {}
  }
}

function persistCheckouts(checkouts: Record<number, Checkout>): void {
  try {
    const slim: Record<number, PersistedCheckout> = {}
    for (const [id, checkout] of Object.entries(checkouts)) {
      slim[Number(id)] = { key: checkout.key, orderId: checkout.orderId }
    }
    sessionStorage.setItem(CHECKOUT_STORAGE, JSON.stringify(slim))
  } catch {
    // sessionStorage can be unavailable (private mode); the in-memory copy works.
  }
}

// On a 409 the reservation already has an order (created in another tab, or
// before a reload, under a different idempotency key); adopt that order instead
// of failing, so the buyer can still pay from this tab.
async function createOrAdoptOrder(reservationId: number, key: string): Promise<number> {
  try {
    return (await api.createOrder(reservationId, key)).id
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) {
      const orders = await api.listOrders()
      const existing = orders.find((o) => o.reservation_id === reservationId)
      if (existing) return existing.id
    }
    throw e
  }
}

export const useCartStore = defineStore('cart', () => {
  const cart = ref<Cart | null>(null)
  const serverOffset = ref<number | null>(null)
  const checkouts = ref<Record<number, Checkout>>(loadCheckouts())

  function checkoutOf(reservationId: number): Checkout | undefined {
    return checkouts.value[reservationId]
  }

  let fetchSeq = 0

  async function fetchCart(): Promise<void> {
    const seq = ++fetchSeq
    const data = await api.cart()
    if (seq !== fetchSeq) return
    cart.value = data
    serverOffset.value =
      data.items.length > 0 ? Date.now() - Date.parse(data.server_now) : null
  }

  async function release(reservationId: number): Promise<void> {
    await api.releaseReservation(reservationId)
    await fetchCart()
  }

  async function pay(reservationId: number, cardNumber: string): Promise<void> {
    let checkout = checkouts.value[reservationId]
    if (!checkout) {
      const created: Checkout = {
        key: crypto.randomUUID(),
        orderId: null,
        busy: false,
        outcome: null,
        error: null,
      }
      checkouts.value = { ...checkouts.value, [reservationId]: created }
      checkout = checkouts.value[reservationId]!
      persistCheckouts(checkouts.value)
    }
    if (checkout.busy) return
    checkout.busy = true
    checkout.error = null
    checkout.outcome = null
    try {
      if (checkout.orderId === null) {
        checkout.orderId = await createOrAdoptOrder(reservationId, checkout.key)
        persistCheckouts(checkouts.value)
      }
      checkout.outcome = (await api.pay(checkout.orderId, cardNumber)).status
    } catch (e) {
      checkout.error = e instanceof ApiError ? e.message : 'Payment failed'
    } finally {
      checkout.busy = false
    }
    if (checkout.outcome === 'approved') {
      try {
        await fetchCart()
      } catch {
        // A failed refetch must not hide the successful payment.
      }
    }
  }

  async function applyEvent(event: RealtimeEvent): Promise<void> {
    if (
      event !== 'order_status' &&
      event !== 'stock_changed' &&
      event !== 'sale_status'
    )
      return
    try {
      await fetchCart()
    } catch {
      // Transient refetch failure: the next event or reconnect retries.
    }
  }

  let bound = false
  function bindRealtime(): void {
    if (bound) return
    bound = true
    const rt = useRealtime()
    rt.on('order_status', () => void applyEvent('order_status'))
    rt.on('stock_changed', () => void applyEvent('stock_changed'))
    rt.on('sale_status', () => void applyEvent('sale_status'))
    rt.onReconnect(() => void fetchCart())
  }

  return {
    cart,
    serverOffset,
    checkoutOf,
    fetchCart,
    release,
    pay,
    applyEvent,
    bindRealtime,
  }
})
