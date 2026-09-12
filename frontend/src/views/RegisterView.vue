<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { ApiError } from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()

const email = ref('')
const password = ref('')
const error = ref<string | null>(null)
const submitting = ref(false)

async function submit() {
  error.value = null
  submitting.value = true
  try {
    await auth.register(email.value, password.value)
    // Registration does not start a session; sign in next.
    await router.push({ name: 'login' })
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Registration failed'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <form class="auth" data-testid="register-form" @submit.prevent="submit">
    <h1>Create account</h1>
    <label>
      Email
      <input v-model="email" type="email" autocomplete="email" required />
    </label>
    <label>
      Password
      <input
        v-model="password"
        type="password"
        autocomplete="new-password"
        minlength="8"
        required
      />
    </label>
    <p v-if="error" role="alert">{{ error }}</p>
    <button type="submit" :disabled="submitting">Register</button>
    <p>Already have an account? <RouterLink to="/login">Sign in</RouterLink></p>
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
