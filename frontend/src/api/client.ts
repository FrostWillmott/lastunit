// The single place that talks HTTP. Every request goes through the /api
// prefix so the Vite dev proxy and nginx route it to the backend without the
// browser knowing the origin; components and stores never call fetch directly.
//
// Session auth rides the HttpOnly cookie, so no token is threaded through
// here — the browser sends it on same-origin requests (the default
// `credentials` of 'same-origin').

import type {
  Cart,
  Order,
  PayResult,
  Reservation,
  Sale,
  SaleCreateInput,
  SaleStats,
  User,
} from './types'

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`/api${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
  } catch (e) {
    throw new ApiError(0, e instanceof Error ? e.message : 'network error')
  }
  if (!res.ok) {
    throw new ApiError(res.status, await detail(res))
  }
  if (res.status === 204) {
    return undefined as T
  }
  return (await res.json()) as T
}

async function detail(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown }
    if (typeof body.detail === 'string') return body.detail
  } catch {
    // Non-JSON error body (proxy/nginx 502 etc.) — fall through to the status.
  }
  return `HTTP ${res.status}`
}

function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: 'POST', body: JSON.stringify(body) })
}

export const api = {
  // auth
  register(email: string, password: string): Promise<User> {
    return post<User>('/auth/register', { email, password })
  },
  login(email: string, password: string): Promise<User> {
    return post<User>('/auth/login', { email, password })
  },
  logout(): Promise<void> {
    return request<void>('/auth/logout', { method: 'POST' })
  },
  me(): Promise<User> {
    return request<User>('/auth/me')
  },

  // sales
  listSales(): Promise<Sale[]> {
    return request<Sale[]>('/sales')
  },
  getSale(id: number): Promise<Sale> {
    return request<Sale>(`/sales/${id}`)
  },
  createSale(input: SaleCreateInput): Promise<Sale> {
    return post<Sale>('/sales', input)
  },
  reserve(saleId: number): Promise<Reservation> {
    return post<Reservation>(`/sales/${saleId}/reserve`, {})
  },

  // cart
  releaseReservation(reservationId: number): Promise<void> {
    return request<void>(`/reservations/${reservationId}`, { method: 'DELETE' })
  },
  cart(): Promise<Cart> {
    return request<Cart>('/me/cart')
  },
  listOrders(): Promise<Order[]> {
    return request<Order[]>('/me/orders')
  },

  // orders + payments
  createOrder(reservationId: number, idempotencyKey: string): Promise<Order> {
    return request<Order>('/orders', {
      method: 'POST',
      body: JSON.stringify({ reservation_id: reservationId }),
      headers: { 'Idempotency-Key': idempotencyKey },
    })
  },
  pay(orderId: number, cardNumber: string): Promise<PayResult> {
    return post<PayResult>(`/orders/${orderId}/pay`, { card_number: cardNumber })
  },

  // shop
  saleStats(saleId: number): Promise<SaleStats> {
    return request<SaleStats>(`/shop/sales/${saleId}/stats`)
  },
  checkPayment(reference: string): Promise<{ status: string }> {
    return post<{ status: string }>(`/shop/payments/${reference}/check`, {})
  },
}
