import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from './auth'

const realtime = vi.hoisted(() => ({
  openRealtime: vi.fn(),
  closeRealtime: vi.fn(),
}))
vi.mock('../composables/useRealtime', () => ({
  openRealtime: realtime.openRealtime,
  closeRealtime: realtime.closeRealtime,
}))

function mockFetch(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  })
}

beforeEach(() => {
  setActivePinia(createPinia())
  realtime.openRealtime.mockClear()
  realtime.closeRealtime.mockClear()
})
afterEach(() => vi.unstubAllGlobals())

describe('auth store', () => {
  it('login stores the returned user and exposes the role flag', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch(200, { id: 1, email: 'shop@example.com', role: 'shop' }),
    )
    const auth = useAuthStore()

    await auth.login('shop@example.com', 'pw')

    expect(auth.user).toEqual({ id: 1, email: 'shop@example.com', role: 'shop' })
    expect(auth.isAuthenticated).toBe(true)
    expect(auth.isShop).toBe(true)
    expect(realtime.openRealtime).toHaveBeenCalledTimes(1)
  })

  it('fetchMe restores the session from the cookie and marks initialized', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch(200, { id: 2, email: 'buyer@example.com', role: 'buyer' }),
    )
    const auth = useAuthStore()

    await auth.fetchMe()

    expect(auth.user?.email).toBe('buyer@example.com')
    expect(auth.initialized).toBe(true)
  })

  it('fetchMe treats a 401 as signed out and still marks initialized', async () => {
    vi.stubGlobal('fetch', mockFetch(401, { detail: 'not authenticated' }))
    const auth = useAuthStore()

    await auth.fetchMe()

    expect(auth.user).toBeNull()
    expect(auth.initialized).toBe(true)
  })

  it('logout clears the user after calling the backend', async () => {
    vi.stubGlobal('fetch', mockFetch(200, { id: 1, email: 'a@b.c', role: 'buyer' }))
    const auth = useAuthStore()
    await auth.login('a@b.c', 'pw')

    const logoutFetch = mockFetch(204, null)
    vi.stubGlobal('fetch', logoutFetch)
    await auth.logout()

    expect(auth.user).toBeNull()
    expect(realtime.closeRealtime).toHaveBeenCalledTimes(1)
    expect(logoutFetch).toHaveBeenCalledWith(
      '/api/auth/logout',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('register creates the account without starting a session', async () => {
    const fetch = mockFetch(201, { id: 1, email: 'a@b.c', role: 'buyer' })
    vi.stubGlobal('fetch', fetch)
    const auth = useAuthStore()

    await auth.register('a@b.c', 'pw')

    expect(auth.user).toBeNull()
    expect(auth.isAuthenticated).toBe(false)
    expect(fetch).toHaveBeenCalledWith(
      '/api/auth/register',
      expect.objectContaining({ method: 'POST' }),
    )
  })
})
