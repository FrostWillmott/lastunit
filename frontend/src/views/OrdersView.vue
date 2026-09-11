<script setup lang="ts">
import { onMounted } from 'vue'
import { formatPrice } from '../lib/money'
import { useOrdersStore } from '../stores/orders'

const store = useOrdersStore()

onMounted(async () => {
  store.bindRealtime()
  await store.fetchOrders()
})
</script>

<template>
  <main>
    <h1>Your orders</h1>

    <ul class="orders">
      <li v-for="order in store.orders" :key="order.id" class="order">
        <span class="id">Order #{{ order.id }}</span>
        <span class="amount">{{ formatPrice(order.amount_minor) }}</span>
        <span class="status" :data-status="order.status">{{ order.status }}</span>
      </li>
    </ul>

    <p v-if="!store.orders.length" class="empty">No orders yet.</p>
  </main>
</template>

<style scoped>
main {
  max-width: 40rem;
  margin: 2rem auto;
  padding: 0 1rem;
}
.orders {
  list-style: none;
  padding: 0;
  display: grid;
  gap: 0.5rem;
}
.order {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.75rem 1rem;
  border: 1px solid var(--border, #0002);
  border-radius: 0.5rem;
}
.amount {
  font-weight: 600;
}
.status {
  text-transform: capitalize;
}
.status[data-status='paid'] {
  color: var(--ok, #1a7f37);
}
.status[data-status='cancelled'] {
  color: var(--muted, #667);
}
.empty {
  color: var(--muted, #667);
}
</style>
