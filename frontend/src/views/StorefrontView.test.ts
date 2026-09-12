import { enableAutoUnmount, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import StorefrontView from './StorefrontView.vue'

// Unmount between tests, so a visibility change set up by the next test never
// reaches a previous test's component after its fetch stub is gone.
enableAutoUnmount(afterEach)

// The socket boundary: mocked so mounting the view never opens an EventSource
// (jsdom has none), exactly as the store tests do.
const realtime = vi.hoisted(() => ({ on: vi.fn(), onReconnect: vi.fn() }))
vi.mock('../composables/useRealtime', () => ({
  useRealtime: () => ({
    on: realtime.on,
    onReconnect: realtime.onReconnect,
    status: { value: 'OPEN' },
  }),
}))

const SALE = {
  id: 1,
  title: 'Sneakers',
  price_minor: 1000,
  quantity: 5,
  available: 5,
  starts_at: '2026-01-01T00:00:00Z',
  ends_at: '2026-01-01T01:00:00Z',
  timezone: 'Europe/Moscow',
  phase: 'active',
  server_now: '2026-01-01T00:30:00Z',
}

function jsonFetch(body: unknown) {
  return vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => body })
}

// jsdom's visibilityState is read-only, so drive it the way the browser would:
// redefine the value, then fire the event useDocumentVisibility listens for.
function setVisibility(state: DocumentVisibilityState): void {
  Object.defineProperty(document, 'visibilityState', {
    value: state,
    configurable: true,
  })
  document.dispatchEvent(new Event('visibilitychange'))
}

beforeEach(() => {
  setActivePinia(createPinia())
  realtime.on.mockClear()
  realtime.onReconnect.mockClear()
  setVisibility('visible')
})
afterEach(() => vi.unstubAllGlobals())

describe('StorefrontView', () => {
  it('renders a sale with its stock and countdown', async () => {
    vi.stubGlobal('fetch', jsonFetch([SALE]))
    const wrapper = mount(StorefrontView)
    await vi.waitFor(() => expect(wrapper.text()).toContain('Sneakers'))

    expect(wrapper.text()).toContain('5 of 5 left')
    expect(wrapper.get('button').attributes('disabled')).toBeUndefined()
  })

  it('keeps the buy button disabled before the sale starts', async () => {
    const upcoming = {
      ...SALE,
      phase: 'upcoming',
      starts_at: '2026-01-01T00:45:00Z',
      server_now: '2026-01-01T00:30:00Z',
    }
    vi.stubGlobal('fetch', jsonFetch([upcoming]))
    const wrapper = mount(StorefrontView)
    await vi.waitFor(() => expect(wrapper.text()).toContain('Sneakers'))

    expect(wrapper.text()).toContain('Starts in')
    expect(wrapper.get('button').attributes('disabled')).toBeDefined()
  })

  // A backgrounded tab's timers are throttled, so its countdown — and the
  // "has it started" gate derived from it — drifts behind the backend. Coming
  // back to the tab must re-anchor it rather than wait for the next event.
  it('refetches when a backgrounded tab becomes visible again', async () => {
    const fetchMock = jsonFetch([SALE])
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(StorefrontView)
    await vi.waitFor(() => expect(wrapper.text()).toContain('Sneakers'))
    const afterMount = fetchMock.mock.calls.length

    setVisibility('hidden')
    await vi.waitFor(() => expect(fetchMock.mock.calls.length).toBe(afterMount))
    setVisibility('visible')

    await vi.waitFor(() => expect(fetchMock.mock.calls.length).toBe(afterMount + 1))
  })

  it('does not refetch while the tab stays hidden', async () => {
    const fetchMock = jsonFetch([SALE])
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(StorefrontView)
    await vi.waitFor(() => expect(wrapper.text()).toContain('Sneakers'))
    const afterMount = fetchMock.mock.calls.length

    setVisibility('hidden')

    expect(fetchMock.mock.calls.length).toBe(afterMount)
  })
})
