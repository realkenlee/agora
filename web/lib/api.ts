import type { Listing, Offer, Message, GeneratedListing } from './types'

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'https://agora-production-2bbb.up.railway.app'

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('agora_token') : null
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? 'Request failed')
  }
  return res.json()
}

// ── Listings ──────────────────────────────────────────────────────────────────

export const api = {
  listings: {
    get: (id: string) => req<Listing>(`/listings/${id}`),
    create: (body: object) => req<Listing>('/listings', { method: 'POST', body: JSON.stringify(body) }),
    update: (id: string, body: object) => req<Listing>(`/listings/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
    delete: (id: string) => req<void>(`/listings/${id}`, { method: 'DELETE' }),
    offers: (id: string) => req<Offer[]>(`/listings/${id}/offers`),
    messages: (id: string) => req<Message[]>(`/listings/${id}/messages`),
    sendMessage: (id: string, body: string) =>
      req<Message>(`/listings/${id}/messages`, { method: 'POST', body: JSON.stringify({ body }) }),
    makeOffer: (id: string, amount: number, message?: string) =>
      req<Offer>(`/listings/${id}/offers`, { method: 'POST', body: JSON.stringify({ amount, message }) }),
  },

  search: (query: object) => req<{ results: Array<{ listing: Listing; score: number; distance_mi: number | null }> }>('/search', {
    method: 'POST',
    body: JSON.stringify(query),
  }),

  offers: {
    respond: (id: string, action: 'accept' | 'reject' | 'counter', counter_amount?: number, message?: string) =>
      req<Offer>(`/offers/${id}`, { method: 'PATCH', body: JSON.stringify({ action, counter_amount, message }) }),
  },

  me: {
    listings: (status = 'active') => req<Listing[]>(`/me/listings?status=${status}`),
    offers: (direction = 'all') => req<Offer[]>(`/me/offers?direction=${direction}`),
  },

  ai: {
    generate: (body: { description?: string; price_hint?: number; location?: { lat: number; lng: number; text: string }; photo_urls?: string[] }) =>
      req<{ draft_id: string; status: string }>('/ai/generate', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
  },

  drafts: {
    get: (id: string) => req<import('./types').Draft>(`/drafts/${id}`),
    publish: (id: string) => req<import('./types').Listing>(`/drafts/${id}/publish`, { method: 'POST' }),
  },

  notifications: {
    list: () => req<import('./types').Notification[]>('/me/notifications'),
    read: (id: string) => req<void>(`/me/notifications/${id}/read`, { method: 'PATCH' }),
  },

  usage: () => req<import('./types').UsageInfo>('/me/usage'),
}
