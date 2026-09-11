import { ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '../api/client'
import type { Sale, SaleCreateInput, SaleStats } from '../api/types'
import { useRealtime, type RealtimeEvent } from '../composables/useRealtime'

export const useShopStore = defineStore('shop', () => {
  const sales = ref<Sale[]>([])
  const stats = ref<SaleStats | null>(null)
  const selectedSaleId = ref<number | null>(null)

  async function fetchSales(): Promise<void> {
    sales.value = await api.listSales()
  }

  async function fetchStats(saleId: number): Promise<void> {
    selectedSaleId.value = saleId
    stats.value = await api.saleStats(saleId)
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
    if (event !== 'stock_changed' && event !== 'sale_status') return
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
