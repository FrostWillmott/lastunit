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

  // The buyer's cabinet stays current via SSE. An order moves on order_status
  // (paid/cancelled), but a cancellation also rides stock_changed (hold expiry)
  // and sale_status (sale end), so refetch on any of them.
  async function applyEvent(event: RealtimeEvent): Promise<void> {
    if (
      event !== 'order_status' &&
      event !== 'stock_changed' &&
      event !== 'sale_status'
    )
      return
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
    rt.on('stock_changed', () => void applyEvent('stock_changed'))
    rt.on('sale_status', () => void applyEvent('sale_status'))
    rt.onReconnect(() => void fetchOrders())
  }

  return { orders, fetchOrders, applyEvent, bindRealtime }
})
