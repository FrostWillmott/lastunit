<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useTimestamp } from '@vueuse/core'
import { ApiError } from '../api/client'
import type { Sale } from '../api/types'
import { formatPrice } from '../lib/money'
import { useSalesStore } from '../stores/sales'

const store = useSalesStore()
// A ticking browser clock; combined with the store's serverOffset it becomes
// backend time, so the countdown does not drift with the viewer's own clock.
const now = useTimestamp({ interval: 1000 })

const reserveError = ref<string | null>(null)

onMounted(async () => {
  store.bindRealtime()
  try {
    await store.fetchSales()
  } catch (e) {
    reserveError.value = e instanceof ApiError ? e.message : 'Could not load sales'
  }
})

const serverNow = computed(() =>
  store.serverOffset === null ? null : now.value - store.serverOffset,
)

type Phase = 'upcoming' | 'active' | 'ended'

function phaseOf(sale: Sale): Phase {
  if (serverNow.value === null) return sale.phase
  const starts = Date.parse(sale.starts_at)
  const ends = Date.parse(sale.ends_at)
  if (serverNow.value < starts) return 'upcoming'
  if (serverNow.value < ends) return 'active'
  return 'ended'
}

function secondsUntil(instant: string): number {
  if (serverNow.value === null) return 0
  return Math.max(0, Math.ceil((Date.parse(instant) - serverNow.value) / 1000))
}

function countdown(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

async function reserve(sale: Sale) {
  reserveError.value = null
  try {
    await store.reserve(sale.id)
  } catch (e) {
    reserveError.value = e instanceof ApiError ? e.message : 'Could not reserve'
  }
}
</script>

<template>
  <main>
    <h1>Flash sales</h1>
    <p v-if="reserveError" role="alert">{{ reserveError }}</p>

    <ul class="sales">
      <li v-for="sale in store.sales" :key="sale.id" class="sale">
        <div>
          <h2>{{ sale.title }}</h2>
          <p class="price">{{ formatPrice(sale.price_minor) }}</p>
          <p class="stock">
            <template v-if="phaseOf(sale) === 'upcoming'">
              Starts in {{ countdown(secondsUntil(sale.starts_at)) }}
            </template>
            <template v-else-if="phaseOf(sale) === 'active'">
              {{ sale.available }} of {{ sale.quantity }} left · ends in
              {{ countdown(secondsUntil(sale.ends_at)) }}
            </template>
            <template v-else>Ended</template>
          </p>
        </div>
        <button
          type="button"
          :disabled="phaseOf(sale) !== 'active' || sale.available === 0"
          @click="reserve(sale)"
        >
          <template v-if="phaseOf(sale) === 'ended'">Ended</template>
          <template v-else-if="sale.available === 0">Sold out</template>
          <template v-else>Add to cart</template>
        </button>
      </li>
    </ul>

    <p v-if="store.sales.length === 0" class="empty">No sales yet.</p>
  </main>
</template>

<style scoped>
main {
  max-width: 40rem;
  margin: 2rem auto;
  padding: 0 1rem;
}
.sales {
  list-style: none;
  padding: 0;
  display: grid;
  gap: 1rem;
}
.sale {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 1rem;
  border: 1px solid var(--border, #0002);
  border-radius: 0.5rem;
}
.price {
  font-size: 1.25rem;
  font-weight: 600;
}
.stock {
  color: var(--muted, #667);
}
.empty {
  color: var(--muted, #667);
}
</style>
