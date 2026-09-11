<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ApiError } from '../api/client'
import type { Sale } from '../api/types'
import { formatPrice } from '../lib/money'
import { useShopStore } from '../stores/shop'

// The stub's own origin (compose exposes it on 8001). It is not proxied, so
// the dashboard links to it directly for the reviewer to resolve a hung card.
const PAYSTUB_DOCS_URL = 'http://localhost:8001/docs'

const store = useShopStore()
const error = ref<string | null>(null)

// Create-sale form state. Times are naive wall-clock (datetime-local), entered
// in the chosen IANA zone; the backend stores them as UTC.
const title = ref('')
const price = ref('')
const quantity = ref('')
const timezone = ref(Intl.DateTimeFormat().resolvedOptions().timeZone)
const startsAt = ref('')
const endsAt = ref('')
const creating = ref(false)

onMounted(async () => {
  store.bindRealtime()
  try {
    await store.fetchSales()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not load sales'
  }
})

function select(sale: Sale): Promise<void> {
  return store.fetchStats(sale.id).catch((e) => {
    error.value = e instanceof ApiError ? e.message : 'Could not load stats'
  })
}

async function createSale() {
  error.value = null
  creating.value = true
  try {
    const sale = await store.createSale({
      title: title.value,
      price_minor: Math.round(Number(price.value) * 100),
      quantity: Number(quantity.value),
      timezone: timezone.value,
      starts_at: startsAt.value,
      ends_at: endsAt.value,
    })
    title.value = ''
    price.value = ''
    quantity.value = ''
    startsAt.value = ''
    endsAt.value = ''
    await select(sale)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not create sale'
  } finally {
    creating.value = false
  }
}

async function checkPayment(reference: string) {
  error.value = null
  try {
    await store.checkPayment(reference)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not check payment'
  }
}
</script>

<template>
  <main>
    <h1>Shop dashboard</h1>
    <p v-if="error" role="alert">{{ error }}</p>

    <section>
      <h2>Create sale</h2>
      <form class="create" @submit.prevent="createSale">
        <label>Title <input v-model="title" required /></label>
        <label
          >Price <input v-model="price" type="number" min="0" step="0.01" required
        /></label>
        <label
          >Quantity <input v-model="quantity" type="number" min="1" required
        /></label>
        <label>
          Timezone
          <input v-model="timezone" list="zones" required />
        </label>
        <datalist id="zones">
          <option value="Europe/Moscow" />
          <option value="Europe/Berlin" />
          <option value="America/New_York" />
          <option value="Asia/Tokyo" />
          <option value="UTC" />
        </datalist>
        <label
          >Starts at <input v-model="startsAt" type="datetime-local" required
        /></label>
        <label>Ends at <input v-model="endsAt" type="datetime-local" required /></label>
        <button type="submit" :disabled="creating">Create</button>
      </form>
    </section>

    <section>
      <h2>Sales</h2>
      <ul class="sales">
        <li v-for="sale in store.sales" :key="sale.id">
          <button type="button" @click="select(sale)">
            {{ sale.title }} — {{ sale.available }}/{{ sale.quantity }} left
          </button>
        </li>
      </ul>
      <p v-if="!store.sales.length" class="muted">No sales yet.</p>
    </section>

    <section v-if="store.stats">
      <h2>Stats</h2>
      <dl class="stats">
        <dt>Available</dt>
        <dd>{{ store.stats.available }}</dd>
        <dt>Sold</dt>
        <dd>{{ store.stats.sold }}</dd>
        <dt>In carts</dt>
        <dd>{{ store.stats.in_cart }}</dd>
        <dt>Revenue</dt>
        <dd>{{ formatPrice(store.stats.revenue_minor) }}</dd>
      </dl>

      <h3>Pending payments</h3>
      <ul class="pending">
        <li v-for="payment in store.stats.pending_payments" :key="payment.provider_ref">
          <code>{{ payment.provider_ref }}</code>
          <button type="button" @click="checkPayment(payment.provider_ref)">
            Check status
          </button>
        </li>
      </ul>
      <p v-if="!store.stats.pending_payments.length" class="muted">
        No pending payments.
      </p>
      <p class="muted">
        To resolve a hung card (…9995), open the
        <a :href="PAYSTUB_DOCS_URL" target="_blank" rel="noopener">paystub docs</a>.
      </p>
    </section>
  </main>
</template>

<style scoped>
main {
  max-width: 40rem;
  margin: 2rem auto;
  padding: 0 1rem;
}
section {
  margin-top: 2rem;
}
.create {
  display: grid;
  gap: 0.5rem;
}
.create label {
  display: grid;
  gap: 0.25rem;
}
.sales,
.pending {
  list-style: none;
  padding: 0;
  display: grid;
  gap: 0.5rem;
}
.sales button {
  width: 100%;
  text-align: left;
}
.pending li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}
.stats {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 0.25rem 1rem;
}
.stats dd {
  margin: 0;
  font-weight: 600;
}
.muted {
  color: var(--muted, #667);
}
</style>
