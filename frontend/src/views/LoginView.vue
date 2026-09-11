<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { ApiError } from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const email = ref('')
const password = ref('')
const error = ref<string | null>(null)
const submitting = ref(false)

async function submit() {
  error.value = null
  submitting.value = true
  try {
    await auth.login(email.value, password.value)
    const redirect =
      typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    await router.push(redirect)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Login failed'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <form class="auth" data-testid="login-form" @submit.prevent="submit">
    <h1>Sign in</h1>
    <label>
      Email
      <input v-model="email" type="email" autocomplete="email" required />
    </label>
    <label>
      Password
      <input
        v-model="password"
        type="password"
        autocomplete="current-password"
        required
      />
    </label>
    <p v-if="error" role="alert">{{ error }}</p>
    <button type="submit" :disabled="submitting">Sign in</button>
    <p>No account? <RouterLink to="/register">Register</RouterLink></p>
  </form>
</template>

<style scoped>
.auth {
  max-width: 24rem;
  margin: 2rem auto;
  padding: 0 1rem;
  display: grid;
  gap: 0.75rem;
}
.auth label {
  display: grid;
  gap: 0.25rem;
}
</style>
