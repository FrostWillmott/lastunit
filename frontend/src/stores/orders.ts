import { ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '../api/client'
import type { Order } from '../api/types'
import { useRealtime, type RealtimeEvent } from '../composables/useRealtime'

export const useOrdersStore = defineStore('orders', () => {
  const orders = ref<Order[]>([])

  async function fetchOrders(): Promise<void> {
    orders.value = await api.listOrders()
  }

  // The buyer's cabinet stays current via SSE: an order_status event means an
  // order moved (paid/cancelled), so refetch the list.
  async function applyEvent(event: RealtimeEvent): Promise<void> {
    if (event !== 'order_status') return
    try {
      await fetchOrders()
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
    rt.onReconnect(() => void fetchOrders())
  }

  return { orders, fetchOrders, applyEvent, bindRealtime }
})
