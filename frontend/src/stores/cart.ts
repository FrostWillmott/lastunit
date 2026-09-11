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

export const useCartStore = defineStore('cart', () => {
  const cart = ref<Cart | null>(null)
  const serverOffset = ref<number | null>(null)
  const checkouts = ref<Record<number, Checkout>>({})

  function checkoutOf(reservationId: number): Checkout | undefined {
    return checkouts.value[reservationId]
  }

  async function fetchCart(): Promise<void> {
    const data = await api.cart()
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
    }
    if (checkout.busy) return
    checkout.busy = true
    checkout.error = null
    checkout.outcome = null
    try {
      if (checkout.orderId === null) {
        const order = await api.createOrder(reservationId, checkout.key)
        checkout.orderId = order.id
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
    if (event !== 'order_status' && event !== 'stock_changed') return
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
