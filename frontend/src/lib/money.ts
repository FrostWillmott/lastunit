// Prices travel as minor units (kopecks) in `price_minor` / `amount_minor`;
// render them as major units. Kept as a tiny pure helper because cart, orders
// and the shop dashboard all display the same value.
export function formatPrice(minor: number): string {
  return `$${(minor / 100).toFixed(2)}`
}
