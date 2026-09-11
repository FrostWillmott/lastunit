import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '../api/client'
import type { User } from '../api/types'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  // Set once the session has been restored from the cookie (or confirmed
  // absent), so the router guard knows it has checked before redirecting.
  const initialized = ref(false)

  const isAuthenticated = computed(() => user.value !== null)
  const isShop = computed(() => user.value?.role === 'shop')

  async function register(email: string, password: string): Promise<void> {
    // Registering creates the account but does not start a session; the caller
    // sends the user to the login form.
    await api.register(email, password)
  }

  async function login(email: string, password: string): Promise<void> {
    user.value = await api.login(email, password)
    initialized.value = true
  }

  async function fetchMe(): Promise<void> {
    try {
      user.value = await api.me()
    } catch {
      // No session (or the backend is down): treat as signed out.
      user.value = null
    }
    initialized.value = true
  }

  async function logout(): Promise<void> {
    await api.logout()
    user.value = null
  }

  return {
    user,
    initialized,
    isAuthenticated,
    isShop,
    register,
    login,
    fetchMe,
    logout,
  }
})
