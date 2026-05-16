'use client'

import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { ChevronLeft, MapPin, Bot, Shield, MessageCircle, Tag, ChevronRight, ChevronLeft as Prev, Pencil, Check, X, Trash2 } from 'lucide-react'
import Link from 'next/link'
import { cn, formatPrice, formatRelativeTime, CONDITION_LABELS, CONDITION_COLORS } from '@/lib/utils'
import { api } from '@/lib/api'
import type { Listing } from '@/lib/types'

export default function ListingPage() {
  const { id }                    = useParams<{ id: string }>()
  const router                    = useRouter()
  const [listing, setListing]     = useState<Listing | null>(null)
  const [loading, setLoading]     = useState(true)
  const [photoIdx, setPhotoIdx]   = useState(0)
  const [showOffer, setShowOffer] = useState(false)
  const [offerAmt, setOfferAmt]   = useState('')
  const [offerMsg, setOfferMsg]   = useState('')
  const [sending, setSending]     = useState(false)
  const [sent, setSent]           = useState<'offer' | 'message' | null>(null)
  const [message, setMessage]     = useState('')
  const [showMsg, setShowMsg]     = useState(false)

  // Edit state
  const [editing, setEditing]     = useState(false)
  const [editTitle, setEditTitle] = useState('')
  const [editPrice, setEditPrice] = useState('')
  const [editDesc, setEditDesc]   = useState('')
  const [editNeg, setEditNeg]     = useState(true)
  const [saving, setSaving]       = useState(false)
  const [deleting, setDeleting]   = useState(false)
  const [isOwner, setIsOwner]     = useState(false)

  useEffect(() => {
    api.listings.get(id).then(l => {
      setListing(l)
      const token = localStorage.getItem('agora_token')
      setIsOwner(token === l.seller.id)
    }).finally(() => setLoading(false))
  }, [id])

  function startEdit() {
    if (!listing) return
    setEditTitle(listing.title)
    setEditPrice(String(listing.price))
    setEditDesc(listing.description)
    setEditNeg(listing.price_negotiable)
    setEditing(true)
  }

  async function deleteListing() {
    if (!listing) return
    if (!confirm('Remove this listing? This cannot be undone.')) return
    setDeleting(true)
    await api.listings.delete(listing.id)
    router.push('/dashboard')
  }

  async function saveEdit() {
    if (!listing) return
    setSaving(true)
    const updated = await api.listings.update(listing.id, {
      title: editTitle,
      price: parseFloat(editPrice),
      description: editDesc,
      price_negotiable: editNeg,
    })
    setListing(updated)
    setEditing(false)
    setSaving(false)
  }

  async function makeOffer() {
    if (!listing || !offerAmt) return
    setSending(true)
    await api.listings.makeOffer(listing.id, parseFloat(offerAmt), offerMsg || undefined)
    setSending(false)
    setSent('offer')
    setShowOffer(false)
  }

  async function sendMessage() {
    if (!listing || !message.trim()) return
    setSending(true)
    await api.listings.sendMessage(listing.id, message)
    setSending(false)
    setSent('message')
    setShowMsg(false)
  }

  if (loading) return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
    </div>
  )

  if (!listing) return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-4">
      <p className="text-gray-500">Listing not found</p>
      <Link href="/" className="text-indigo-600 font-medium">Go home</Link>
    </div>
  )

  const photos = listing.photos

  return (
    <div className="min-h-screen bg-white">
      {/* Back button */}
      <div className="absolute top-4 left-4 z-10">
        <Link href="/" className="w-10 h-10 bg-white/90 backdrop-blur rounded-full flex items-center justify-center shadow-sm">
          <ChevronLeft size={20} className="text-gray-700" />
        </Link>
      </div>

      {/* Edit button (owner only) */}
      {isOwner && !editing && (
        <div className="absolute top-4 right-4 z-10">
          <button
            onClick={startEdit}
            className="w-10 h-10 bg-white/90 backdrop-blur rounded-full flex items-center justify-center shadow-sm"
          >
            <Pencil size={16} className="text-gray-700" />
          </button>
        </div>
      )}

      {/* Photos */}
      <div className="relative aspect-square bg-gray-100 overflow-hidden">
        {photos.length > 0 ? (
          <>
            <img src={photos[photoIdx]} alt={listing.title} className="w-full h-full object-cover" />
            {photos.length > 1 && (
              <>
                <button onClick={() => setPhotoIdx(i => Math.max(0, i - 1))}
                  className={cn('absolute left-3 top-1/2 -translate-y-1/2 w-8 h-8 bg-black/30 text-white rounded-full flex items-center justify-center', photoIdx === 0 && 'opacity-0')}>
                  <Prev size={16} />
                </button>
                <button onClick={() => setPhotoIdx(i => Math.min(photos.length - 1, i + 1))}
                  className={cn('absolute right-3 top-1/2 -translate-y-1/2 w-8 h-8 bg-black/30 text-white rounded-full flex items-center justify-center', photoIdx === photos.length - 1 && 'opacity-0')}>
                  <ChevronRight size={16} />
                </button>
                <div className="absolute bottom-3 left-0 right-0 flex justify-center gap-1.5">
                  {photos.map((_, i) => (
                    <button key={i} onClick={() => setPhotoIdx(i)}
                      className={cn('w-1.5 h-1.5 rounded-full transition-colors', i === photoIdx ? 'bg-white' : 'bg-white/40')} />
                  ))}
                </div>
              </>
            )}
          </>
        ) : (
          <div className="w-full h-full flex items-center justify-center text-gray-300">
            <Tag size={48} />
          </div>
        )}
      </div>

      {/* Content */}
      <div className="max-w-lg mx-auto px-4 py-5 space-y-5">

        {editing ? (
          /* ── Edit form ─────────────────────────────────────────── */
          <div className="space-y-4">
            <input
              value={editTitle}
              onChange={e => setEditTitle(e.target.value)}
              className="w-full text-xl font-bold text-gray-900 border-b-2 border-indigo-400 focus:outline-none pb-1"
            />
            <div className="flex items-center gap-3">
              <div className="relative flex-1">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 font-bold">$</span>
                <input
                  type="number"
                  value={editPrice}
                  onChange={e => setEditPrice(e.target.value)}
                  className="w-full pl-7 pr-4 py-2 rounded-xl border border-gray-200 text-lg font-bold text-indigo-600 focus:outline-none focus:border-indigo-400"
                />
              </div>
              <label className="flex items-center gap-2 text-sm text-gray-600">
                <input type="checkbox" checked={editNeg} onChange={e => setEditNeg(e.target.checked)} />
                Negotiable
              </label>
            </div>
            <textarea
              value={editDesc}
              onChange={e => setEditDesc(e.target.value)}
              rows={5}
              className="w-full rounded-xl border border-gray-200 px-4 py-3 text-sm text-gray-700 leading-relaxed focus:outline-none focus:border-indigo-400 resize-none"
            />
            <div className="flex gap-2">
              <button onClick={() => setEditing(false)}
                className="flex-1 border border-gray-200 py-3 rounded-xl text-sm font-medium text-gray-600 flex items-center justify-center gap-2">
                <X size={16} /> Cancel
              </button>
              <button onClick={saveEdit} disabled={saving}
                className="flex-1 bg-indigo-600 text-white py-3 rounded-xl text-sm font-semibold flex items-center justify-center gap-2 disabled:opacity-50">
                <Check size={16} /> {saving ? 'Saving…' : 'Save'}
              </button>
            </div>
            <button onClick={deleteListing} disabled={deleting}
              className="w-full border border-red-200 text-red-500 py-3 rounded-xl text-sm font-medium flex items-center justify-center gap-2 disabled:opacity-50">
              <Trash2 size={16} /> {deleting ? 'Removing…' : 'Remove listing'}
            </button>
          </div>
        ) : (
          /* ── Normal view ───────────────────────────────────────── */
          <>
            <div className="flex items-start justify-between gap-4">
              <h1 className="text-xl font-bold text-gray-900 leading-tight">{listing.title}</h1>
              <div className="text-right shrink-0">
                <p className="text-2xl font-bold text-indigo-600">{formatPrice(listing.price)}</p>
                {listing.price_negotiable && <p className="text-xs text-gray-400">Negotiable</p>}
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              <span className={cn('text-sm font-medium px-3 py-1 rounded-full', CONDITION_COLORS[listing.condition])}>
                {CONDITION_LABELS[listing.condition]}
              </span>
              {listing.listed_by === 'agent' && (
                <span className="text-sm font-medium px-3 py-1 rounded-full bg-indigo-50 text-indigo-700 flex items-center gap-1.5">
                  <Bot size={13} /> Agent listed
                </span>
              )}
              <span className="text-sm text-gray-400 flex items-center gap-1 ml-auto">
                <MapPin size={13} /> {listing.location.text}
              </span>
            </div>

            <p className="text-gray-700 leading-relaxed">{listing.description}</p>

            {Object.keys(listing.attributes).length > 0 && (
              <div className="grid grid-cols-2 gap-2">
                {Object.entries(listing.attributes).map(([k, v]) => (
                  <div key={k} className="bg-gray-50 rounded-xl px-3 py-2">
                    <p className="text-xs text-gray-400 capitalize">{k}</p>
                    <p className="text-sm font-medium text-gray-900">{v}</p>
                  </div>
                ))}
              </div>
            )}

            <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-2xl">
              <div className="w-10 h-10 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-700 font-bold text-sm">
                {listing.seller.display_name[0].toUpperCase()}
              </div>
              <div className="flex-1">
                <p className="font-semibold text-sm text-gray-900">{listing.seller.display_name}</p>
                <div className="flex items-center gap-2 text-xs text-gray-400">
                  {listing.seller.phone_verified && (
                    <span className="flex items-center gap-1 text-emerald-600"><Shield size={11} /> Verified</span>
                  )}
                  <span>{listing.seller.sold_total} sold</span>
                  {listing.seller.avg_rating && <span>⭐ {listing.seller.avg_rating.toFixed(1)}</span>}
                </div>
              </div>
              <p className="text-xs text-gray-400">{formatRelativeTime(listing.created_at)}</p>
            </div>

            {sent === 'offer' && (
              <div className="bg-emerald-50 text-emerald-700 rounded-2xl p-4 text-sm font-medium text-center">
                ✓ Offer sent! The seller will respond shortly.
              </div>
            )}
            {sent === 'message' && (
              <div className="bg-emerald-50 text-emerald-700 rounded-2xl p-4 text-sm font-medium text-center">
                ✓ Message sent!
              </div>
            )}

            {showOffer && (
              <div className="border border-indigo-200 rounded-2xl p-4 space-y-3">
                <p className="font-semibold text-gray-900">Make an offer</p>
                <div className="relative">
                  <span className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400">$</span>
                  <input autoFocus type="number" value={offerAmt} onChange={e => setOfferAmt(e.target.value)}
                    placeholder={String(Math.round(listing.price * 0.9))}
                    className="w-full rounded-xl border border-gray-200 pl-8 pr-4 py-3 text-base focus:outline-none focus:border-indigo-400" />
                </div>
                <textarea value={offerMsg} onChange={e => setOfferMsg(e.target.value)}
                  placeholder="Message (optional)" rows={2}
                  className="w-full rounded-xl border border-gray-200 px-4 py-3 text-sm focus:outline-none focus:border-indigo-400 resize-none" />
                <div className="flex gap-2">
                  <button onClick={() => setShowOffer(false)} className="flex-1 border border-gray-200 py-3 rounded-xl text-sm font-medium text-gray-600">Cancel</button>
                  <button onClick={makeOffer} disabled={!offerAmt || sending}
                    className="flex-1 bg-indigo-600 text-white py-3 rounded-xl text-sm font-semibold disabled:opacity-50">
                    {sending ? 'Sending…' : 'Send offer'}
                  </button>
                </div>
              </div>
            )}

            {showMsg && (
              <div className="border border-gray-200 rounded-2xl p-4 space-y-3">
                <p className="font-semibold text-gray-900">Message seller</p>
                <textarea autoFocus value={message} onChange={e => setMessage(e.target.value)}
                  placeholder="Is this still available?" rows={3}
                  className="w-full rounded-xl border border-gray-200 px-4 py-3 text-sm focus:outline-none focus:border-indigo-400 resize-none" />
                <div className="flex gap-2">
                  <button onClick={() => setShowMsg(false)} className="flex-1 border border-gray-200 py-3 rounded-xl text-sm font-medium text-gray-600">Cancel</button>
                  <button onClick={sendMessage} disabled={!message.trim() || sending}
                    className="flex-1 bg-indigo-600 text-white py-3 rounded-xl text-sm font-semibold disabled:opacity-50">
                    {sending ? 'Sending…' : 'Send'}
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* Sticky CTA — buyers only, not editing */}
      {!isOwner && !showOffer && !showMsg && !editing && sent === null && listing.status === 'active' && (
        <div className="sticky bottom-20 md:bottom-6 left-0 right-0 px-4 pb-2">
          <div className="max-w-lg mx-auto flex gap-3">
            <button onClick={() => setShowMsg(true)}
              className="w-12 h-12 border border-gray-200 bg-white rounded-2xl flex items-center justify-center text-gray-600 shadow-sm">
              <MessageCircle size={20} />
            </button>
            <button onClick={() => setShowOffer(true)}
              className="flex-1 bg-indigo-600 text-white font-semibold py-3 rounded-2xl shadow-lg shadow-indigo-200 text-base">
              {listing.price_negotiable ? `Offer · asking ${formatPrice(listing.price)}` : `Buy · ${formatPrice(listing.price)}`}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
