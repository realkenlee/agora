'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { CheckCircle, X, ChevronRight, Bot, Clock, Tag, MessageCircle, Loader2, Bell, LogOut } from 'lucide-react'
import { cn, formatPrice, formatRelativeTime } from '@/lib/utils'
import { api } from '@/lib/api'
import { useAgentEvents } from '@/hooks/useAgentEvents'
import type { Listing, Offer, Notification, UsageInfo } from '@/lib/types'

type Tab = 'active' | 'offers' | 'buying' | 'sold'

export default function DashboardPage() {
  const router = useRouter()
  const [tab, setTab]                   = useState<Tab>('active')
  const [listings, setListings]         = useState<Listing[]>([])
  const [offers, setOffers]             = useState<Offer[]>([])
  const [sentOffers, setSentOffers]     = useState<Offer[]>([])
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [usage, setUsage]               = useState<UsageInfo | null>(null)
  const [loading, setLoading]           = useState(true)

  useEffect(() => {
    Promise.all([
      api.me.listings('active'),
      api.me.offers('received'),
      api.me.offers('sent'),
      api.notifications.list(),
      api.usage(),
    ]).then(([l, o, s, n, u]) => {
      setListings(l)
      setOffers(o.filter(o => o.status === 'pending'))
      setSentOffers(s)
      setNotifications(n)
      setUsage(u)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  // Real-time updates via SSE — replaces the old 5s polling loop
  useAgentEvents({
    offer_received: (data) => {
      // Refresh offers from API to get full offer object
      api.me.offers('received').then(o => setOffers(o.filter(o => o.status === 'pending'))).catch(() => {})
      // Add notification card
      setNotifications(prev => [{
        id: `sse-${data.offer_id}`,
        type: 'offer_received',
        title: 'New offer',
        body: `${data.from} offered ${formatPrice(data.amount)} on "${data.listing_title}"`,
        action_type: 'approve',
        action_url: `/listings/${data.listing_id}`,
        payload: {},
        read_at: null,
        created_at: new Date().toISOString(),
      }, ...prev])
    },
    offer_accepted: (data) => {
      setOffers(prev => prev.filter(o => o.id !== data.offer_id))
      api.me.listings('active').then(setListings).catch(() => {})
    },
    offer_rejected: (data) => {
      setOffers(prev => prev.filter(o => o.id !== data.offer_id))
    },
    draft_ready: (data) => {
      setNotifications(prev => [{
        id: `sse-draft-${data.draft_id}`,
        type: 'draft_ready',
        title: 'Listing draft ready',
        body: `"${data.title}" — AI suggested ${formatPrice(data.suggested_price)}. Review and publish.`,
        action_type: 'approve',
        action_url: `/drafts/${data.draft_id}`,
        payload: {},
        read_at: null,
        created_at: new Date().toISOString(),
      }, ...prev])
    },
    listing_live: () => {
      api.me.listings('active').then(setListings).catch(() => {})
    },
    message_received: (data) => {
      setNotifications(prev => [{
        id: `sse-msg-${data.listing_id}-${Date.now()}`,
        type: 'message_received',
        title: 'New message',
        body: `${data.from}: "${data.preview}"`,
        action_type: 'fyi',
        action_url: `/listings/${data.listing_id}`,
        payload: {},
        read_at: null,
        created_at: new Date().toISOString(),
      }, ...prev])
    },
  })

  async function dismissNotification(id: string) {
    if (!id.startsWith('sse-')) {
      await api.notifications.read(id).catch(() => {})
    }
    setNotifications(n => n.filter(x => x.id !== id))
  }

  const pendingOffers = offers.filter(o => o.status === 'pending')
  const unread = notifications.filter(n => !n.read_at)

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-white border-b border-gray-100 px-4 pt-12 pb-0">
        <div className="max-w-lg mx-auto">
          <div className="flex items-center justify-between mb-4">
            <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
            <div className="flex items-center gap-2">
              {usage && (
                <span className={cn(
                  'text-xs font-medium px-3 py-1 rounded-full',
                  usage.remaining === 0 ? 'bg-red-100 text-red-700' :
                  usage.remaining === 1 ? 'bg-yellow-100 text-yellow-700' :
                  'bg-gray-100 text-gray-500'
                )}>
                  {usage.remaining}/{usage.limit} AI listings left
                </span>
              )}
              <button
                onClick={() => { localStorage.removeItem('agora_token'); router.push('/login') }}
                className="text-gray-400 hover:text-gray-600 p-1"
                title="Log out"
              >
                <LogOut size={16} />
              </button>
            </div>
          </div>
          <div className="flex gap-1">
            {([
              { key: 'active', label: 'Selling' },
              { key: 'offers', label: 'Offers' },
              { key: 'buying', label: 'Buying' },
              { key: 'sold',   label: 'Sold' },
            ] as { key: Tab; label: string }[]).map(({ key: t, label }) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={cn(
                  'px-4 py-2 text-sm font-medium rounded-t-lg transition-colors',
                  tab === t ? 'text-indigo-600 border-b-2 border-indigo-600' : 'text-gray-500'
                )}
              >
                {label}
                {t === 'offers' && pendingOffers.length > 0 && (
                  <span className="ml-1.5 bg-indigo-600 text-white text-xs w-4 h-4 rounded-full inline-flex items-center justify-center">
                    {pendingOffers.length}
                  </span>
                )}
                {t === 'buying' && sentOffers.filter(o => o.status === 'pending').length > 0 && (
                  <span className="ml-1.5 bg-emerald-500 text-white text-xs w-4 h-4 rounded-full inline-flex items-center justify-center">
                    {sentOffers.filter(o => o.status === 'pending').length}
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="max-w-lg mx-auto px-4 py-4 space-y-3">
        {unread.length > 0 && (
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-xs font-semibold text-gray-500 uppercase tracking-wide">
              <Bell size={12} />
              Inbox
              <span className="bg-indigo-600 text-white rounded-full w-4 h-4 flex items-center justify-center text-xs">{unread.length}</span>
            </div>
            {unread.map(n => (
              <NotificationCard key={n.id} notification={n} onDismiss={dismissNotification} />
            ))}
          </div>
        )}

        {loading && <div className="py-12 text-center text-gray-400">Loading…</div>}

        {!loading && tab === 'offers' && (
          pendingOffers.length === 0 ? (
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
          )
        )}

        {!loading && tab === 'active' && (
          listings.length === 0 ? (
            <EmptyState
              icon={<Tag size={32} className="text-gray-300" />}
              title="No active listings"
              subtitle="Use the Agora MCP to list your first item"
            />
          ) : (
            listings.map(listing => <ActiveListingRow key={listing.id} listing={listing} />)
          )
        )}

        {!loading && tab === 'buying' && <BuyingTab offers={sentOffers} />}

        {!loading && tab === 'sold' && <SoldListings />}
      </div>
    </div>
  )
}

function NotificationCard({ notification: n, onDismiss }: {
  notification: Notification
  onDismiss: (id: string) => void
}) {
  return (
    <div className={cn(
      'bg-white rounded-2xl border shadow-sm overflow-hidden',
      n.action_type === 'approve' ? 'border-indigo-200' : 'border-gray-100'
    )}>
      <div className={cn(
        'px-4 py-2.5 flex items-center gap-2',
        n.action_type === 'approve' ? 'bg-indigo-600 text-white' : 'bg-gray-50 text-gray-600'
      )}>
        <Bot size={14} />
        <span className="text-xs font-medium flex-1">{n.title}</span>
        <span className="text-xs opacity-60">{formatRelativeTime(n.created_at)}</span>
      </div>
      <div className="px-4 py-3 flex items-center justify-between gap-3">
        <p className="text-sm text-gray-600">{n.body}</p>
        <div className="flex gap-2 shrink-0">
          {n.action_type === 'approve' && n.action_url && (
            <Link href={n.action_url}
              className="bg-indigo-600 text-white text-sm font-semibold px-4 py-2 rounded-xl"
              onClick={() => onDismiss(n.id)}>
              Review →
            </Link>
          )}
          <button onClick={() => onDismiss(n.id)} className="text-gray-400 hover:text-gray-600 p-1">
            <X size={16} />
          </button>
        </div>
      </div>
    </div>
  )
}

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
        <div className="flex gap-2">
          <button onClick={() => respond('reject')} disabled={responding}
            className="flex-1 border border-gray-200 text-gray-600 font-semibold py-3 rounded-xl flex items-center justify-center gap-2 text-sm">
            <X size={16} />
            Decline
          </button>
          <button onClick={() => respond('accept')} disabled={responding}
            className="flex-2 flex-grow bg-emerald-500 text-white font-semibold py-3 rounded-xl flex items-center justify-center gap-2 text-sm">
            <CheckCircle size={16} />
            Confirm sale
          </button>
        </div>
      </div>
    </div>
  )
}

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

const OFFER_STATUS_STYLE: Record<string, string> = {
  pending:  'bg-yellow-100 text-yellow-700',
  accepted: 'bg-emerald-100 text-emerald-700',
  rejected: 'bg-red-100 text-red-600',
  countered:'bg-indigo-100 text-indigo-700',
  expired:  'bg-gray-100 text-gray-500',
  withdrawn:'bg-gray-100 text-gray-500',
}

function BuyingTab({ offers }: { offers: Offer[] }) {
  if (offers.length === 0) return (
    <EmptyState
      icon={<MessageCircle size={32} className="text-gray-300" />}
      title="No offers sent yet"
      subtitle="Browse listings and make an offer — they'll all appear here"
    />
  )
  return (
    <div className="space-y-3">
      {offers.map(offer => (
        <Link key={offer.id} href={`/listings/${offer.listing_id}`} className="block">
          <div className="bg-white rounded-2xl border border-gray-100 p-4 flex items-center gap-3 hover:border-indigo-200 transition-colors">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className={cn('text-xs font-semibold px-2 py-0.5 rounded-full capitalize', OFFER_STATUS_STYLE[offer.status] ?? 'bg-gray-100 text-gray-500')}>
                  {offer.status}
                </span>
                <span className="text-xs text-gray-400">{formatRelativeTime(offer.created_at)}</span>
              </div>
              <p className="text-lg font-bold text-gray-900">{formatPrice(offer.amount)}</p>
              {offer.message && <p className="text-sm text-gray-500 truncate italic">"{offer.message}"</p>}
              {offer.status === 'countered' && offer.counter_amount && (
                <p className="text-sm text-indigo-600 font-medium mt-1">
                  Counter: {formatPrice(offer.counter_amount)}
                  {offer.counter_message && <span className="text-gray-500 font-normal"> — "{offer.counter_message}"</span>}
                </p>
              )}
            </div>
            <ChevronRight size={16} className="text-gray-300 shrink-0" />
          </div>
        </Link>
      ))}
    </div>
  )
}

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
