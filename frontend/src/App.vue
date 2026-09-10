<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { fetchHealth, type Health } from './api'

const health = ref<Health | null>(null)
const error = ref<string | null>(null)

onMounted(async () => {
  try {
    health.value = await fetchHealth()
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : String(e)
  }
})
</script>

<template>
  <main>
    <h1>App</h1>
    <p v-if="error" role="alert">Backend unavailable: {{ error }}</p>
    <p v-if="health" data-testid="health">Backend status: {{ health.status }}</p>
  </main>
</template>

<style scoped>
main {
  max-width: 40rem;
  margin: 2rem auto;
  padding: 0 1rem;
}
</style>
