'use client'

import { useState, useEffect, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { ChevronLeft, Loader2, Bot, CheckCircle, AlertCircle } from 'lucide-react'
import { cn, formatPrice, CONDITION_LABELS } from '@/lib/utils'
import { api } from '@/lib/api'
import { useAgentEvents } from '@/hooks/useAgentEvents'
import type { Draft, GeneratedListing, Condition } from '@/lib/types'

const PRICE_STEPS = [-50, -25, -10, 10, 25, 50]

export default function DraftReviewPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const [draft, setDraft]       = useState<Draft | null>(null)
  const [listing, setListing]   = useState<GeneratedListing | null>(null)
  const [price, setPrice]       = useState(0)
  const [publishing, setPublishing] = useState(false)
  const [done, setDone]         = useState(false)
  const [listingId, setListingId] = useState<string | null>(null)

  const load = useCallback(async () => {
    const d = await api.drafts.get(id)
    setDraft(d)
    if (d.status === 'ready' && d.draft) {
      setListing(d.draft as GeneratedListing)
      setPrice(d.draft.suggested_price)
    }
  }, [id])

  useEffect(() => {
    if (!localStorage.getItem('agora_token')) { router.replace('/login'); return }
    load()
  }, [load, router])

  // SSE: when draft_ready fires for this draft, reload it — no more polling
  useAgentEvents({
    draft_ready: (data) => {
      if (data.draft_id === id) load()
    },
  })

  async function publish() {
    if (!listing) return
    setPublishing(true)
    try {
      setListing(l => l ? { ...l, suggested_price: price } : l)
      const result = await api.drafts.publish(id)
      setListingId(result.id)
      setDone(true)
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : 'Failed to publish')
      setPublishing(false)
    }
  }

  if (!draft) return (
    <div className="min-h-screen flex items-center justify-center">
      <Loader2 size={32} className="text-indigo-400 animate-spin" />
    </div>
  )

  if (done) return (
    <div className="min-h-screen bg-white flex flex-col items-center justify-center px-4 gap-6 text-center">
      <div className="w-24 h-24 rounded-full bg-emerald-50 flex items-center justify-center">
        <CheckCircle size={48} className="text-emerald-500" />
      </div>
      <div className="space-y-2">
        <h2 className="text-2xl font-bold text-gray-900">You&apos;re live!</h2>
        <p className="text-gray-500 max-w-xs">Your agent is handling buyer questions and negotiations.</p>
      </div>
      <div className="flex gap-3 w-full max-w-sm">
        {listingId && (
          <a href={`/listings/${listingId}`}
            className="flex-1 border border-gray-200 text-gray-700 font-semibold py-3 rounded-2xl text-center text-sm">
            View listing
          </a>
        )}
        <a href="/dashboard" className="flex-1 bg-indigo-600 text-white font-semibold py-3 rounded-2xl text-center text-sm">
          Dashboard
        </a>
      </div>
    </div>
  )

  return (
    <div className="min-h-screen bg-white">
      <div className="sticky top-0 bg-white/95 backdrop-blur border-b border-gray-100 z-10">
        <div className="flex items-center h-14 px-4 max-w-lg mx-auto">
          <button onClick={() => router.back()} className="p-2 -ml-2 text-gray-500">
            <ChevronLeft size={24} />
          </button>
          <h1 className="font-semibold text-gray-900 mx-auto">Review listing</h1>
        </div>
      </div>

      <div className="max-w-lg mx-auto px-4 py-6 space-y-6">

        {draft.status === 'processing' && (
          <div className="flex flex-col items-center py-20 gap-4">
            <div className="relative">
              <div className="w-20 h-20 rounded-full bg-indigo-50 flex items-center justify-center">
                <Bot size={36} className="text-indigo-500" />
              </div>
              <Loader2 size={80} className="absolute inset-0 text-indigo-200 animate-spin" strokeWidth={1} />
            </div>
            <p className="font-semibold text-gray-900">Agent is writing your listing…</p>
            <p className="text-sm text-gray-500 text-center">Analysing photos, crafting description, researching price</p>
          </div>
        )}

        {draft.status === 'failed' && (
          <div className="flex flex-col items-center py-20 gap-4 text-center">
            <AlertCircle size={48} className="text-red-400" />
            <p className="font-semibold text-gray-900">Generation failed</p>
            <p className="text-sm text-gray-500">{draft.error || 'Something went wrong. Please try again.'}</p>
            <a href="/sell" className="bg-indigo-600 text-white font-semibold px-6 py-3 rounded-2xl text-sm">Try again</a>
          </div>
        )}

        {draft.status === 'ready' && listing && (
          <>
            {listing.photo_urls && listing.photo_urls.length > 0 && (
              <div className="flex gap-2 overflow-x-auto no-scrollbar -mx-4 px-4">
                {listing.photo_urls.map((src, i) => (
                  <img key={i} src={src} alt=""
                    className={cn(
                      'rounded-2xl object-cover shrink-0',
                      listing.photo_urls!.length === 1 ? 'w-full h-64' : 'w-40 h-40'
                    )} />
                ))}
              </div>
            )}

            <div className="bg-indigo-50 rounded-2xl p-4 text-sm text-indigo-700 flex gap-2">
              <Bot size={16} className="shrink-0 mt-0.5" />
              <span><span className="font-medium">Agent: </span>{listing.reasoning}</span>
            </div>

            <div>
              <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide block mb-1">Title</label>
              <input value={listing.title}
                onChange={e => setListing(l => l ? { ...l, title: e.target.value } : l)}
                className="w-full rounded-xl border border-gray-200 px-4 py-3 text-base font-medium focus:outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100" />
            </div>

            <div>
              <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide block mb-3">Price</label>
              <div className="flex items-center gap-2 flex-wrap">
                {PRICE_STEPS.slice(0, 3).map(step => (
                  <button key={step} onClick={() => setPrice(p => Math.max(1, p + step))}
                    className="px-3 py-2 rounded-xl border border-gray-200 text-sm text-gray-600 hover:border-indigo-300 font-medium">
                    {step < 0 ? `-$${Math.abs(step)}` : `+$${step}`}
                  </button>
                ))}
                <div className="flex-1 text-center">
                  <span className="text-2xl font-bold text-gray-900">{formatPrice(price)}</span>
                  {price !== listing.suggested_price && (
                    <button onClick={() => setPrice(listing.suggested_price)}
                      className="block mx-auto text-xs text-indigo-500 mt-0.5">
                      Reset to AI pick ({formatPrice(listing.suggested_price)})
                    </button>
                  )}
                </div>
                {PRICE_STEPS.slice(3).map(step => (
                  <button key={step} onClick={() => setPrice(p => p + step)}
                    className="px-3 py-2 rounded-xl border border-gray-200 text-sm text-gray-600 hover:border-indigo-300 font-medium">
                    +${step}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide block mb-1">Condition</label>
              <select value={listing.condition}
                onChange={e => setListing(l => l ? { ...l, condition: e.target.value as Condition } : l)}
                className="w-full rounded-xl border border-gray-200 px-4 py-3 text-base focus:outline-none focus:border-indigo-400 bg-white">
                {Object.entries(CONDITION_LABELS).map(([v, l]) => (
                  <option key={v} value={v}>{l}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide block mb-1">Description</label>
              <textarea value={listing.description}
                onChange={e => setListing(l => l ? { ...l, description: e.target.value } : l)}
                rows={4}
                className="w-full rounded-xl border border-gray-200 px-4 py-3 text-base focus:outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 resize-none" />
            </div>

            {Object.keys(listing.attributes).length > 0 && (
              <div className="flex flex-wrap gap-2">
                {Object.entries(listing.attributes).map(([k, v]) => (
                  <span key={k} className="bg-gray-100 text-gray-700 text-sm px-3 py-1 rounded-full">
                    <span className="text-gray-400">{k}: </span>{v}
                  </span>
                ))}
              </div>
            )}

            <button onClick={publish} disabled={publishing}
              className="w-full bg-indigo-600 text-white font-semibold py-4 rounded-2xl flex items-center justify-center gap-2 disabled:opacity-60">
              {publishing ? <Loader2 size={20} className="animate-spin" /> : <CheckCircle size={20} />}
              {publishing ? 'Publishing…' : `Post listing — ${formatPrice(price)}`}
            </button>
          </>
        )}
      </div>
    </div>
  )
}
