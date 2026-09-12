import { ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '../api/client'
import type { Sale, SaleCreateInput, SaleStats } from '../api/types'
import { useRealtime, type RealtimeEvent } from '../composables/useRealtime'

export const useShopStore = defineStore('shop', () => {
  const sales = ref<Sale[]>([])
  const stats = ref<SaleStats | null>(null)
  const selectedSaleId = ref<number | null>(null)

  // Monotonic guards: a burst of events starts concurrent refetches, and a
  // slower, older response must not overwrite a newer one.
  let salesSeq = 0
  let statsSeq = 0

  async function fetchSales(): Promise<void> {
    const seq = ++salesSeq
    const list = await api.listSales()
    if (seq !== salesSeq) return
    sales.value = list
  }

  async function fetchStats(saleId: number): Promise<void> {
    const seq = ++statsSeq
    selectedSaleId.value = saleId
    const data = await api.saleStats(saleId)
    if (seq !== statsSeq) return
    stats.value = data
  }

  async function createSale(input: SaleCreateInput): Promise<Sale> {
    const sale = await api.createSale(input)
    await fetchSales()
    return sale
  }

  // "Check status" asks the paystub and applies the answer through the same
  // handler as the webhook, then refreshes the stats so a resolved payment
  // drops out of the pending list and revenue/sold move.
  async function checkPayment(reference: string): Promise<void> {
    await api.checkPayment(reference)
    if (selectedSaleId.value !== null) await fetchStats(selectedSaleId.value)
  }

  async function applyEvent(event: RealtimeEvent): Promise<void> {
    // sale_stats, not order_status: the latter is scoped to the buyer who owns
    // the order, so a dashboard never receives another user's payment.
    if (event !== 'stock_changed' && event !== 'sale_status' && event !== 'sale_stats')
      return
    try {
      await fetchSales()
      if (selectedSaleId.value !== null) await fetchStats(selectedSaleId.value)
    } catch {
      // Transient refetch failure: the next event or reconnect retries.
    }
  }

  let bound = false
  function bindRealtime(): void {
    if (bound) return
    bound = true
    const rt = useRealtime()
    rt.on('stock_changed', () => void applyEvent('stock_changed'))
    rt.on('sale_status', () => void applyEvent('sale_status'))
    rt.on('sale_stats', () => void applyEvent('sale_stats'))
    rt.onReconnect(() => {
      void fetchSales()
      if (selectedSaleId.value !== null) void fetchStats(selectedSaleId.value)
    })
  }

  return {
    sales,
    stats,
    selectedSaleId,
    fetchSales,
    fetchStats,
    createSale,
    checkPayment,
    applyEvent,
    bindRealtime,
  }
})
