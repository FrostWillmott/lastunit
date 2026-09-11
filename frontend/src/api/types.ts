// Response/request shapes mirror the backend's Pydantic models (snake_case,
// as FastAPI serialises them). Keeping the same field names means no mapping
// layer to drift; when the backend publishes OpenAPI these should be generated
// rather than hand-maintained.

export type UserRole = 'buyer' | 'shop'

export type SalePhase = 'upcoming' | 'active' | 'ended'

export type ReservationStatus =
  'held' | 'paying' | 'sold' | 'expired' | 'released' | 'cleared'

export type OrderStatus = 'pending' | 'paid' | 'cancelled'

export type PaymentStatus = 'pending' | 'approved' | 'declined'

export interface User {
  id: number
  email: string
  role: UserRole
}

export interface Sale {
  id: number
  title: string
  price_minor: number
  quantity: number
  available: number
  starts_at: string
  ends_at: string
  timezone: string
  phase: SalePhase
  server_now: string
}

export interface Reservation {
  id: number
  sale_id: number
  status: string
  expires_at: string
}

export interface CartItem {
  reservation_id: number
  sale_id: number
  title: string
  price_minor: number
  expires_at: string
}

export interface Cart {
  server_now: string
  items: CartItem[]
}

export interface Order {
  id: number
  reservation_id: number
  sale_id: number
  amount_minor: number
  status: OrderStatus
}

export interface PayResult {
  status: PaymentStatus
}

export interface PendingPayment {
  provider_ref: string
  order_id: number
  requested_at: string
}

export interface SaleStats {
  available: number
  sold: number
  in_cart: number
  revenue_minor: number
  pending_payments: PendingPayment[]
}

export interface SaleCreateInput {
  title: string
  price_minor: number
  quantity: number
  timezone: string
  starts_at: string
  ends_at: string
}
