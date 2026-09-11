<script setup lang="ts">
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
</script>

<template>
  <main>
    <h1>Welcome, {{ auth.user?.email }}</h1>
    <p>You are signed in as {{ auth.user?.role }}.</p>
  </main>
</template>

<style scoped>
main {
  max-width: 40rem;
  margin: 2rem auto;
  padding: 0 1rem;
}
</style>
