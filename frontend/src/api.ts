// Thin typed client over the backend API. All requests go through the /api
// prefix so the Vite dev proxy (vite.config.ts) and nginx (Dockerfile) can
// route them without the browser knowing the backend origin.

export type Health = { status: string }

export async function fetchHealth(): Promise<Health> {
  const res = await fetch('/api/health')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return (await res.json()) as Health
}
