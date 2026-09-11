<script setup lang="ts">
import { RouterLink, RouterView, useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'

const auth = useAuthStore()
const router = useRouter()

async function logout() {
  await auth.logout()
  await router.push({ name: 'login' })
}
</script>

<template>
  <header class="bar">
    <RouterLink to="/" class="brand">lastunit</RouterLink>
    <span v-if="auth.isAuthenticated" class="who">
      <RouterLink to="/cart">Cart</RouterLink>
      {{ auth.user?.email }}
      <button type="button" @click="logout">Log out</button>
    </span>
  </header>
  <RouterView />
</template>

<style scoped>
.bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--border, #0002);
}
.brand {
  font-weight: 600;
  text-decoration: none;
}
.who {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
</style>
