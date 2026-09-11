<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useTimestamp } from '@vueuse/core'
import type { CartItem } from '../api/types'
import { formatPrice } from '../lib/money'
import { useCartStore } from '../stores/cart'

const store = useCartStore()
const now = useTimestamp({ interval: 1000 })
const cardNumber = ref('')

onMounted(async () => {
  store.bindRealtime()
  await store.fetchCart()
})

const serverNow = computed(() =>
  store.serverOffset === null ? null : now.value - store.serverOffset,
)

function secondsLeft(item: CartItem): number {
  if (serverNow.value === null) return 0
  return Math.max(0, Math.ceil((Date.parse(item.expires_at) - serverNow.value) / 1000))
}

function expired(item: CartItem): boolean {
  return serverNow.value !== null && Date.parse(item.expires_at) <= serverNow.value
}

function countdown(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

function checkout(item: CartItem) {
  return store.checkoutOf(item.reservation_id)
}
</script>

<template>
  <main>
    <h1>Your cart</h1>

    <label class="card">
      Card number
      <input v-model="cardNumber" inputmode="numeric" autocomplete="cc-number" />
    </label>
    <p class="hint">Test cards: …0000 approves, …0002 declines, …9995 hangs.</p>

    <ul class="items">
      <li
        v-for="item in store.cart?.items ?? []"
        :key="item.reservation_id"
        class="item"
      >
        <div>
          <h2>{{ item.title }}</h2>
          <p class="price">{{ formatPrice(item.price_minor) }}</p>
          <p v-if="expired(item)" class="muted">Expired</p>
          <p v-else class="muted">Held for {{ countdown(secondsLeft(item)) }}</p>
          <p v-if="checkout(item)?.error" role="alert">{{ checkout(item)?.error }}</p>
          <p v-else-if="checkout(item)?.outcome === 'declined'" class="muted">
            Declined — try again.
          </p>
          <p v-else-if="checkout(item)?.outcome === 'pending'" class="muted">
            Payment pending…
          </p>
        </div>
        <div class="actions">
          <button
            type="button"
            :disabled="checkout(item)?.busy"
            @click="store.release(item.reservation_id)"
          >
            Remove
          </button>
          <button
            type="button"
            :disabled="
              expired(item) ||
              checkout(item)?.busy ||
              checkout(item)?.outcome === 'pending' ||
              !cardNumber
            "
            @click="store.pay(item.reservation_id, cardNumber)"
          >
            {{ checkout(item)?.outcome === 'declined' ? 'Try again' : 'Pay' }}
          </button>
        </div>
      </li>
    </ul>

    <p v-if="!store.cart?.items.length" class="empty">Your cart is empty.</p>
  </main>
</template>

<style scoped>
main {
  max-width: 40rem;
  margin: 2rem auto;
  padding: 0 1rem;
}
.card {
  display: grid;
  gap: 0.25rem;
  margin-bottom: 0.5rem;
}
.hint,
.muted {
  color: var(--muted, #667);
}
.items {
  list-style: none;
  padding: 0;
  display: grid;
  gap: 1rem;
}
.item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 1rem;
  border: 1px solid var(--border, #0002);
  border-radius: 0.5rem;
}
.price {
  font-weight: 600;
}
.actions {
  display: flex;
  gap: 0.5rem;
}
.empty {
  color: var(--muted, #667);
}
</style>
