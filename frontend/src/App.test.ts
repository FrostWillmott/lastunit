import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App.vue'

// Mocks at the system boundary (network), not internals — same rule as
// testing.md for the backend.
function mockFetch(body: unknown, ok = true, status = 200) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok, status, json: async () => body }),
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('App', () => {
  it('shows backend status when /api/health responds', async () => {
    mockFetch({ status: 'ok' })
    const wrapper = mount(App)
    await flushPromises()
    expect(wrapper.get('[data-testid="health"]').text()).toBe('Backend status: ok')
  })

  it('shows an error when /api/health fails', async () => {
    mockFetch({}, false, 503)
    const wrapper = mount(App)
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('HTTP 503')
  })
})
