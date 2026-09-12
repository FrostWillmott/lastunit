import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, api } from './client'

// Mocks fetch at the system boundary — same rule as the backend's testing.md.
function mockFetch(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  })
}

afterEach(() => vi.unstubAllGlobals())

describe('api client', () => {
  it('posts credentials to /api/auth/register and returns the user', async () => {
    const fetch = mockFetch(201, { id: 1, email: 'a@b.c', role: 'buyer' })
    vi.stubGlobal('fetch', fetch)

    await expect(api.register('a@b.c', 'pw')).resolves.toEqual({
      id: 1,
      email: 'a@b.c',
      role: 'buyer',
    })
    expect(fetch).toHaveBeenCalledWith(
      '/api/auth/register',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ email: 'a@b.c', password: 'pw' }),
      }),
    )
  })

  it('returns undefined for a 204 (logout, release)', async () => {
    vi.stubGlobal('fetch', mockFetch(204, null))
    await expect(api.logout()).resolves.toBeUndefined()
  })

  it('throws ApiError carrying the backend detail on a non-2xx', async () => {
    vi.stubGlobal('fetch', mockFetch(409, { detail: 'email already registered' }))
    await expect(api.register('a@b.c', 'pw')).rejects.toMatchObject({
      name: 'ApiError',
      status: 409,
      message: 'email already registered',
    })
  })

  it('flattens a FastAPI validation error array into one message', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch(422, {
        detail: [
          {
            loc: ['body', 'password'],
            msg: 'String should have at least 8 characters',
            type: 'string_too_short',
          },
        ],
      }),
    )
    await expect(api.register('a@b.c', 'short')).rejects.toMatchObject({
      status: 422,
      message: 'String should have at least 8 characters',
    })
  })

  it('falls back to the status text when the error body is not JSON', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 502,
        json: async () => {
          throw new Error('not json')
        },
      }),
    )
    await expect(api.me()).rejects.toMatchObject({ status: 502, message: 'HTTP 502' })
  })

  it('wraps a network failure as an ApiError with status 0', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('ECONNREFUSED')))
    await expect(api.me()).rejects.toMatchObject({ status: 0, message: 'ECONNREFUSED' })
  })

  it('sends the Idempotency-Key header when creating an order', async () => {
    const fetch = mockFetch(201, {
      id: 1,
      reservation_id: 2,
      sale_id: 3,
      amount_minor: 100,
      status: 'pending',
    })
    vi.stubGlobal('fetch', fetch)

    await api.createOrder(2, 'key-1')
    expect(fetch).toHaveBeenCalledWith(
      '/api/orders',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ 'Idempotency-Key': 'key-1' }),
        body: JSON.stringify({ reservation_id: 2 }),
      }),
    )
  })

  it('is an instance of ApiError and Error', async () => {
    vi.stubGlobal('fetch', mockFetch(500, { detail: 'boom' }))
    const err = await api.me().catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err).toBeInstanceOf(Error)
  })
})
