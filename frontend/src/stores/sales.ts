import { ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '../api/client'
import type { Sale } from '../api/types'
import { useRealtime, type RealtimeEvent } from '../composables/useRealtime'

export const useSalesStore = defineStore('sales', () => {
  const sales = ref<Sale[]>([])
  // Offset between the browser clock and the backend's `server_now`, captured on
  // the last fetch. The UI counts down from `Date.now() - serverOffset`, so
  // "opens for everyone at once" depends on the backend clock, not the browser's.
  const serverOffset = ref<number | null>(null)

  async function fetchSales(): Promise<void> {
    const list = await api.listSales()
    sales.value = list
    serverOffset.value =
      list.length > 0 ? Date.now() - Date.parse(list[0]!.server_now) : null
  }

  async function reserve(saleId: number): Promise<void> {
    await api.reserve(saleId)
    await fetchSales()
  }

  // Applies a realtime event. Kept as its own (async) action so a test can feed
  // it events directly and assert the resulting state — the SSE wiring just
  // routes into it. The payload is not needed: stock/sale changes always
  // refetch the whole list.
  async function applyEvent(event: RealtimeEvent): Promise<void> {
    if (event !== 'stock_changed' && event !== 'sale_status') return
    try {
      await fetchSales()
    } catch {
      // A transient refetch failure is not worth surfacing; the next event or a
      // reconnect will retry.
    }
  }

  let bound = false
  function bindRealtime(): void {
    if (bound) return
    bound = true
    const rt = useRealtime()
    rt.on('stock_changed', () => void applyEvent('stock_changed'))
    rt.on('sale_status', () => void applyEvent('sale_status'))
    rt.onReconnect(() => void fetchSales())
  }

  return { sales, serverOffset, fetchSales, reserve, applyEvent, bindRealtime }
})
