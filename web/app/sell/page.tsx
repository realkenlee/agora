'use client'

import { useState, useRef } from 'react'
import { Camera, X, ArrowRight, Sparkles, CheckCircle, ChevronLeft, Loader2 } from 'lucide-react'
import { cn, formatPrice, CONDITION_LABELS } from '@/lib/utils'
import { api } from '@/lib/api'
import type { GeneratedListing } from '@/lib/types'

type Step = 'capture' | 'describe' | 'generating' | 'review' | 'done'

export default function SellPage() {
  const [step, setStep]               = useState<Step>('capture')
  const [photos, setPhotos]           = useState<string[]>([])    // base64 previews
  const [photoFiles, setPhotoFiles]   = useState<File[]>([])
  const [description, setDescription] = useState('')
  const [priceHint, setPriceHint]     = useState('')
  const [draft, setDraft]             = useState<GeneratedListing | null>(null)
  const [error, setError]             = useState<string | null>(null)
  const [listingId, setListingId]     = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  // ── Photo capture ──────────────────────────────────────────────────────────

  function handleFiles(files: FileList | null) {
    if (!files) return
    const newFiles = Array.from(files).slice(0, 8 - photos.length)
    newFiles.forEach(file => {
      const reader = new FileReader()
      reader.onload = e => {
        setPhotos(prev => [...prev, e.target?.result as string])
        setPhotoFiles(prev => [...prev, file])
      }
      reader.readAsDataURL(file)
    })
  }

  function removePhoto(i: number) {
    setPhotos(p => p.filter((_, idx) => idx !== i))
    setPhotoFiles(p => p.filter((_, idx) => idx !== i))
  }

  // ── Generate listing ────────────────────────────────────────────────────────

  async function generate() {
    setStep('generating')
    setError(null)
    try {
      const result = await api.ai.generate(
        description,
        priceHint ? parseFloat(priceHint) : undefined,
        undefined,
        photos,
      )
      setDraft(result)
      setStep('review')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Something went wrong')
      setStep('describe')
    }
  }

  // ── Publish ─────────────────────────────────────────────────────────────────

  async function publish() {
    if (!draft) return
    setError(null)
    try {
      const listing = await api.listings.create({
        ...draft,
        price: draft.suggested_price,
        location: { lat: 0, lng: 0, text: 'Location TBD' }, // TODO: get from device
        photo_urls: photos,
        listed_by: 'agent',
      })
      setListingId(listing.id)
      setStep('done')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to publish')
    }
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-white">
      {/* Header */}
      <div className="sticky top-0 bg-white/95 backdrop-blur border-b border-gray-100 z-10">
        <div className="flex items-center h-14 px-4 max-w-lg mx-auto">
          {step !== 'capture' && step !== 'done' && (
            <button
              onClick={() => setStep(step === 'review' ? 'describe' : step === 'describe' ? 'capture' : 'describe')}
              className="p-2 -ml-2 text-gray-500"
            >
              <ChevronLeft size={24} />
            </button>
          )}
          <h1 className="font-semibold text-gray-900 mx-auto">
            {step === 'capture'    && 'Add photos'}
            {step === 'describe'   && 'Describe it'}
            {step === 'generating' && 'Writing your listing…'}
            {step === 'review'     && 'Review listing'}
            {step === 'done'       && "You're live!"}
          </h1>
        </div>
        {/* Progress bar */}
        {step !== 'done' && (
          <div className="h-0.5 bg-gray-100">
            <div
              className="h-full bg-indigo-600 transition-all duration-500"
              style={{ width: { capture: '25%', describe: '50%', generating: '75%', review: '87%', done: '100%' }[step] }}
            />
          </div>
        )}
      </div>

      <div className="max-w-lg mx-auto px-4 py-6">

        {/* ── Step 1: Capture ────────────────────────────────────────────── */}
        {step === 'capture' && (
          <div className="space-y-6">
            <p className="text-gray-500 text-center text-sm">
              Take up to 8 photos. First photo is the cover.
            </p>

            {/* Photo grid */}
            <div className="grid grid-cols-3 gap-2">
              {photos.map((src, i) => (
                <div key={i} className="relative aspect-square rounded-xl overflow-hidden bg-gray-100">
                  <img src={src} alt="" className="w-full h-full object-cover" />
                  <button
                    onClick={() => removePhoto(i)}
                    className="absolute top-1 right-1 bg-black/60 text-white rounded-full p-0.5"
                  >
                    <X size={14} />
                  </button>
                  {i === 0 && (
                    <span className="absolute bottom-1 left-1 bg-black/60 text-white text-xs px-1.5 py-0.5 rounded-md">
                      Cover
                    </span>
                  )}
                </div>
              ))}

              {photos.length < 8 && (
                <button
                  onClick={() => fileRef.current?.click()}
                  className={cn(
                    'aspect-square rounded-xl border-2 border-dashed border-gray-200 flex flex-col items-center justify-center gap-2 text-gray-400 hover:border-indigo-300 hover:text-indigo-400 transition-colors',
                    photos.length === 0 && 'col-span-3 aspect-video'
                  )}
                >
                  <Camera size={photos.length === 0 ? 40 : 24} />
                  {photos.length === 0 && (
                    <span className="text-sm font-medium">Take or upload photos</span>
                  )}
                </button>
              )}
            </div>

            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              multiple
              capture="environment"
              className="hidden"
              onChange={e => handleFiles(e.target.files)}
            />

            <button
              onClick={() => setStep('describe')}
              disabled={photos.length === 0}
              className="w-full bg-indigo-600 text-white font-semibold py-4 rounded-2xl disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2 text-base"
            >
              Continue
              <ArrowRight size={20} />
            </button>
          </div>
        )}

        {/* ── Step 2: Describe ───────────────────────────────────────────── */}
        {step === 'describe' && (
          <div className="space-y-6">
            {/* Photo strip */}
            <div className="flex gap-2 overflow-x-auto no-scrollbar pb-1">
              {photos.map((src, i) => (
                <img key={i} src={src} alt="" className="w-20 h-20 rounded-xl object-cover shrink-0" />
              ))}
            </div>

            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium text-gray-700 block mb-2">
                  What is it? <span className="text-gray-400 font-normal">(one sentence)</span>
                </label>
                <textarea
                  autoFocus
                  value={description}
                  onChange={e => setDescription(e.target.value)}
                  placeholder="e.g. Trek mountain bike, barely used, medium frame"
                  rows={3}
                  className="w-full rounded-xl border border-gray-200 px-4 py-3 text-base placeholder-gray-400 focus:outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 resize-none"
                />
              </div>

              <div>
                <label className="text-sm font-medium text-gray-700 block mb-2">
                  Price in mind? <span className="text-gray-400 font-normal">(optional)</span>
                </label>
                <div className="relative">
                  <span className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 font-medium">$</span>
                  <input
                    type="number"
                    value={priceHint}
                    onChange={e => setPriceHint(e.target.value)}
                    placeholder="Agent will suggest if blank"
                    className="w-full rounded-xl border border-gray-200 pl-8 pr-4 py-3 text-base placeholder-gray-400 focus:outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
                  />
                </div>
              </div>
            </div>

            {error && (
              <p className="text-red-500 text-sm text-center">{error}</p>
            )}

            <button
              onClick={generate}
              disabled={description.trim().length < 5}
              className="w-full bg-indigo-600 text-white font-semibold py-4 rounded-2xl disabled:opacity-40 flex items-center justify-center gap-2 text-base"
            >
              <Sparkles size={20} />
              Write my listing
            </button>

            <p className="text-xs text-gray-400 text-center">
              Agent will write your title, description, and suggest a price
            </p>
          </div>
        )}

        {/* ── Step 3: Generating ─────────────────────────────────────────── */}
        {step === 'generating' && (
          <div className="flex flex-col items-center justify-center py-24 gap-6">
            <div className="relative">
              <div className="w-20 h-20 rounded-full bg-indigo-50 flex items-center justify-center">
                <Sparkles size={36} className="text-indigo-600 animate-pulse" />
              </div>
              <Loader2 size={80} className="absolute inset-0 text-indigo-200 animate-spin" strokeWidth={1} />
            </div>
            <div className="text-center space-y-2">
              <p className="font-semibold text-gray-900">Writing your listing…</p>
              <p className="text-sm text-gray-500">Analysing photos, crafting description, researching price</p>
            </div>
          </div>
        )}

        {/* ── Step 4: Review ─────────────────────────────────────────────── */}
        {step === 'review' && draft && (
          <div className="space-y-6">
            <div className="bg-indigo-50 rounded-2xl p-4 text-sm text-indigo-700">
              <span className="font-medium">Agent reasoning: </span>{draft.reasoning}
            </div>

            {/* Editable fields */}
            <div className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide block mb-1">Title</label>
                <input
                  value={draft.title}
                  onChange={e => setDraft({ ...draft, title: e.target.value })}
                  className="w-full rounded-xl border border-gray-200 px-4 py-3 text-base font-medium focus:outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
                />
              </div>

              <div className="flex gap-3">
                <div className="flex-1">
                  <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide block mb-1">Price</label>
                  <div className="relative">
                    <span className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400">$</span>
                    <input
                      type="number"
                      value={draft.suggested_price}
                      onChange={e => setDraft({ ...draft, suggested_price: parseFloat(e.target.value) })}
                      className="w-full rounded-xl border border-gray-200 pl-8 pr-4 py-3 text-base font-semibold focus:outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
                    />
                  </div>
                </div>
                <div className="flex-1">
                  <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide block mb-1">Condition</label>
                  <select
                    value={draft.condition}
                    onChange={e => setDraft({ ...draft, condition: e.target.value as GeneratedListing['condition'] })}
                    className="w-full rounded-xl border border-gray-200 px-4 py-3 text-base focus:outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 bg-white"
                  >
                    {Object.entries(CONDITION_LABELS).map(([v, l]) => (
                      <option key={v} value={v}>{l}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide block mb-1">Description</label>
                <textarea
                  value={draft.description}
                  onChange={e => setDraft({ ...draft, description: e.target.value })}
                  rows={4}
                  className="w-full rounded-xl border border-gray-200 px-4 py-3 text-base placeholder-gray-400 focus:outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 resize-none"
                />
              </div>
            </div>

            {/* Attributes */}
            {Object.keys(draft.attributes).length > 0 && (
              <div>
                <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide block mb-2">Details</label>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(draft.attributes).map(([k, v]) => (
                    <span key={k} className="bg-gray-100 text-gray-700 text-sm px-3 py-1 rounded-full">
                      <span className="text-gray-400">{k}: </span>{v}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {error && <p className="text-red-500 text-sm text-center">{error}</p>}

            <button
              onClick={publish}
              className="w-full bg-indigo-600 text-white font-semibold py-4 rounded-2xl flex items-center justify-center gap-2 text-base"
            >
              Post listing — {formatPrice(draft.suggested_price)}
              <ArrowRight size={20} />
            </button>

            <p className="text-xs text-gray-400 text-center">
              Your agent will handle buyer questions and notify you when there&apos;s an offer
            </p>
          </div>
        )}

        {/* ── Step 5: Done ───────────────────────────────────────────────── */}
        {step === 'done' && (
          <div className="flex flex-col items-center justify-center py-16 gap-6 text-center">
            <div className="w-24 h-24 rounded-full bg-emerald-50 flex items-center justify-center">
              <CheckCircle size={48} className="text-emerald-500" />
            </div>
            <div className="space-y-2">
              <h2 className="text-2xl font-bold text-gray-900">You&apos;re live!</h2>
              <p className="text-gray-500 max-w-xs">
                Your agent is on it. We&apos;ll send you a notification the moment there&apos;s a buyer.
              </p>
            </div>

            <div className="w-full bg-gray-50 rounded-2xl p-4 text-left space-y-3">
              <p className="text-sm font-semibold text-gray-700">Your agent will:</p>
              {[
                'Answer buyer questions automatically',
                'Negotiate within your price rules',
                'Notify you when it\'s time to confirm',
              ].map(item => (
                <div key={item} className="flex items-center gap-3 text-sm text-gray-600">
                  <CheckCircle size={16} className="text-emerald-500 shrink-0" />
                  {item}
                </div>
              ))}
            </div>

            <div className="flex gap-3 w-full">
              <a
                href={`/listings/${listingId}`}
                className="flex-1 border border-gray-200 text-gray-700 font-semibold py-3 rounded-2xl text-center text-sm"
              >
                View listing
              </a>
              <a
                href="/sell"
                onClick={() => {
                  setStep('capture'); setPhotos([]); setPhotoFiles([])
                  setDescription(''); setPriceHint(''); setDraft(null)
                }}
                className="flex-1 bg-indigo-600 text-white font-semibold py-3 rounded-2xl text-center text-sm"
              >
                Sell another
              </a>
            </div>
          </div>
        )}

      </div>
    </div>
  )
}
