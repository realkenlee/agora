'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { CheckCircle, X, ChevronRight, Bot, Clock, Tag, MessageCircle } from 'lucide-react'
import { cn, formatPrice, formatRelativeTime, CONDITION_LABELS } from '@/lib/utils'
import { api } from '@/lib/api'
import type { Listing, Offer } from '@/lib/types'

type Tab = 'active' | 'offers' | 'sold'

export default function DashboardPage() {
  const [tab, setTab]           = useState<Tab>('active')
  const [listings, setListings] = useState<Listing[]>([])
  const [offers, setOffers]     = useState<Offer[]>([])
  const [loading, setLoading]   = useState(true)

  useEffect(() => {
    Promise.all([
      api.me.listings('active'),
      api.me.offers('received'),
    ]).then(([l, o]) => {
      setListings(l)
      setOffers(o.filter(o => o.status === 'pending'))
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  const pendingOffers = offers.filter(o => o.status === 'pending')

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-100 px-4 pt-12 pb-0">
        <div className="max-w-lg mx-auto">
          <h1 className="text-2xl font-bold text-gray-900 mb-4">Your listings</h1>
          <div className="flex gap-1">
            {(['active', 'offers', 'sold'] as Tab[]).map(t => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={cn(
                  'px-4 py-2 text-sm font-medium rounded-t-lg capitalize transition-colors relative',
                  tab === t
                    ? 'text-indigo-600 border-b-2 border-indigo-600'
                    : 'text-gray-500'
                )}
              >
                {t}
                {t === 'offers' && pendingOffers.length > 0 && (
                  <span className="ml-1.5 bg-indigo-600 text-white text-xs w-4 h-4 rounded-full inline-flex items-center justify-center">
                    {pendingOffers.length}
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="max-w-lg mx-auto px-4 py-4 space-y-3">
        {loading && (
          <div className="py-12 text-center text-gray-400">Loading…</div>
        )}

        {/* ── Offers tab ───────────────────────────────────────────────── */}
        {!loading && tab === 'offers' && (
          <>
            {pendingOffers.length === 0 ? (
              <EmptyState
                icon={<MessageCircle size={32} className="text-gray-300" />}
                title="No pending offers"
                subtitle="Your agent will notify you the moment a buyer makes an offer"
              />
            ) : (
              pendingOffers.map(offer => (
                <OfferCard key={offer.id} offer={offer} onRespond={(id, action) => {
                  api.offers.respond(id, action).then(() => {
                    setOffers(prev => prev.filter(o => o.id !== id))
                  })
                }} />
              ))
            )}
          </>
        )}

        {/* ── Active listings tab ──────────────────────────────────────── */}
        {!loading && tab === 'active' && (
          <>
            {listings.length === 0 ? (
              <EmptyState
                icon={<Tag size={32} className="text-gray-300" />}
                title="No active listings"
                subtitle="Tap Sell to list your first item in seconds"
                cta={{ label: 'Start selling', href: '/sell' }}
              />
            ) : (
              listings.map(listing => (
                <ActiveListingRow key={listing.id} listing={listing} />
              ))
            )}
          </>
        )}

        {/* ── Sold tab ─────────────────────────────────────────────────── */}
        {!loading && tab === 'sold' && (
          <SoldListings />
        )}
      </div>
    </div>
  )
}

// ── Offer confirmation card ───────────────────────────────────────────────────

function OfferCard({ offer, onRespond }: {
  offer: Offer
  onRespond: (id: string, action: 'accept' | 'reject' | 'counter') => void
}) {
  const [responding, setResponding] = useState(false)

  async function respond(action: 'accept' | 'reject') {
    setResponding(true)
    onRespond(offer.id, action)
  }

  return (
    <div className="bg-white rounded-2xl border border-indigo-100 shadow-sm overflow-hidden">
      {/* Attention banner */}
      <div className="bg-indigo-600 text-white px-4 py-2 flex items-center gap-2">
        <Bot size={14} />
        <span className="text-xs font-medium">Your agent received an offer</span>
        <span className="ml-auto text-xs opacity-75">{formatRelativeTime(offer.created_at)}</span>
      </div>

      <div className="p-4 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-500">
              {offer.offered_by === 'agent' ? '🤖 Agent offer from' : 'Offer from'}{' '}
              <span className="font-medium text-gray-900">{offer.buyer.display_name}</span>
            </p>
            {offer.message && (
              <p className="text-sm text-gray-600 mt-1 italic">&ldquo;{offer.message}&rdquo;</p>
            )}
          </div>
          <p className="text-2xl font-bold text-gray-900">{formatPrice(offer.amount)}</p>
        </div>

        <div className="flex items-center gap-2 text-xs text-gray-400">
          <Clock size={12} />
          Expires in 24 hours
        </div>

        {/* Actions */}
        <div className="flex gap-2">
          <button
            onClick={() => respond('reject')}
            disabled={responding}
            className="flex-1 border border-gray-200 text-gray-600 font-semibold py-3 rounded-xl flex items-center justify-center gap-2 text-sm"
          >
            <X size={16} />
            Decline
          </button>
          <button
            onClick={() => respond('accept')}
            disabled={responding}
            className="flex-2 flex-grow bg-emerald-500 text-white font-semibold py-3 rounded-xl flex items-center justify-center gap-2 text-sm"
          >
            <CheckCircle size={16} />
            Confirm sale
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Active listing row ────────────────────────────────────────────────────────

function ActiveListingRow({ listing }: { listing: Listing }) {
  return (
    <Link href={`/listings/${listing.id}`} className="block">
      <div className="bg-white rounded-2xl border border-gray-100 p-3 flex gap-3 items-center hover:border-indigo-200 transition-colors">
        <div className="w-16 h-16 rounded-xl overflow-hidden bg-gray-100 shrink-0">
          {listing.photos[0] ? (
            <img src={listing.photos[0]} alt="" className="w-full h-full object-cover" />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-gray-300 text-xs">No photo</div>
          )}
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-gray-900 text-sm truncate">{listing.title}</p>
          <p className="text-indigo-600 font-bold text-sm">{formatPrice(listing.price)}</p>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="text-xs text-gray-400">{listing.views} views</span>
            {listing.listed_by === 'agent' && (
              <span className="text-xs text-indigo-500 flex items-center gap-0.5">
                <Bot size={10} /> Agent listed
              </span>
            )}
            <span className={cn(
              'text-xs px-2 py-0.5 rounded-full ml-auto',
              listing.status === 'active'  ? 'bg-emerald-100 text-emerald-700' :
              listing.status === 'pending' ? 'bg-yellow-100 text-yellow-700' : 'bg-gray-100 text-gray-500'
            )}>
              {listing.status}
            </span>
          </div>
        </div>
        <ChevronRight size={16} className="text-gray-300 shrink-0" />
      </div>
    </Link>
  )
}

// ── Sold listings ─────────────────────────────────────────────────────────────

function SoldListings() {
  const [sold, setSold] = useState<Listing[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.me.listings('sold').then(setSold).finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="py-12 text-center text-gray-400">Loading…</div>
  if (sold.length === 0) return (
    <EmptyState
      icon={<CheckCircle size={32} className="text-gray-300" />}
      title="No sold items yet"
      subtitle="Items you've sold will appear here"
    />
  )
  return (
    <div className="space-y-3">
      {sold.map(listing => (
        <div key={listing.id} className="bg-white rounded-2xl border border-gray-100 p-3 flex gap-3 items-center opacity-75">
          <div className="w-16 h-16 rounded-xl overflow-hidden bg-gray-100 shrink-0">
            {listing.photos[0] && <img src={listing.photos[0]} alt="" className="w-full h-full object-cover grayscale" />}
          </div>
          <div className="flex-1 min-w-0">
            <p className="font-semibold text-gray-900 text-sm truncate">{listing.title}</p>
            <p className="text-gray-500 text-sm">{formatPrice(listing.price)}</p>
            <p className="text-xs text-gray-400">{formatRelativeTime(listing.updated_at)}</p>
          </div>
          <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">Sold</span>
        </div>
      ))}
    </div>
  )
}

// ── Empty state ───────────────────────────────────────────────────────────────

function EmptyState({ icon, title, subtitle, cta }: {
  icon: React.ReactNode
  title: string
  subtitle: string
  cta?: { label: string; href: string }
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center gap-3">
      {icon}
      <p className="font-semibold text-gray-700">{title}</p>
      <p className="text-sm text-gray-400 max-w-xs">{subtitle}</p>
      {cta && (
        <Link href={cta.href} className="mt-2 bg-indigo-600 text-white text-sm font-semibold px-6 py-3 rounded-2xl">
          {cta.label}
        </Link>
      )}
    </div>
  )
}
