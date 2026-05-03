'use client'

import { useState, useCallback } from 'react'
import { Search, SlidersHorizontal, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { api } from '@/lib/api'
import ListingCard from '@/components/listing-card'
import type { Listing } from '@/lib/types'

const CATEGORIES = [
  { id: '', label: 'All' },
  { id: 'electronics', label: 'Electronics' },
  { id: 'clothing', label: 'Clothing' },
  { id: 'furniture', label: 'Furniture' },
  { id: 'vehicles', label: 'Vehicles' },
  { id: 'sports', label: 'Sports' },
  { id: 'books', label: 'Books' },
  { id: 'tools', label: 'Tools' },
  { id: 'other', label: 'Other' },
]

export default function BrowsePage() {
  const [query, setQuery]         = useState('')
  const [category, setCategory]   = useState('')
  const [maxPrice, setMaxPrice]   = useState('')
  const [results, setResults]     = useState<Listing[]>([])
  const [loading, setLoading]     = useState(false)
  const [searched, setSearched]   = useState(false)
  const [showFilters, setShowFilters] = useState(false)

  const search = useCallback(async (q = query, cat = category, max = maxPrice) => {
    if (!q.trim()) return
    setLoading(true)
    setSearched(true)
    try {
      const res = await api.search({
        query: q,
        category_id: cat || undefined,
        max_price: max ? parseFloat(max) : undefined,
        limit: 24,
      })
      setResults(res.results.map(r => r.listing))
    } catch {
      setResults([])
    } finally {
      setLoading(false)
    }
  }, [query, category, maxPrice])

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === 'Enter') search()
  }

  return (
    <div className="min-h-screen bg-white">
      {/* Sticky search header */}
      <div className="sticky top-0 bg-white/95 backdrop-blur border-b border-gray-100 z-10">
        <div className="max-w-3xl mx-auto px-4 py-3 space-y-3">
          {/* Search bar */}
          <div className="flex gap-2">
            <div className="flex-1 relative">
              <Search size={18} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={handleKey}
                placeholder="Search for anything…"
                className="w-full pl-10 pr-4 py-3 rounded-2xl border border-gray-200 text-base focus:outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 bg-gray-50"
              />
              {query && (
                <button onClick={() => { setQuery(''); setResults([]); setSearched(false) }} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400">
                  <X size={16} />
                </button>
              )}
            </div>
            <button
              onClick={() => search()}
              disabled={!query.trim()}
              className="bg-indigo-600 text-white px-5 rounded-2xl font-semibold text-sm disabled:opacity-40"
            >
              Search
            </button>
            <button
              onClick={() => setShowFilters(f => !f)}
              className={cn('w-12 rounded-2xl border flex items-center justify-center transition-colors', showFilters ? 'border-indigo-400 bg-indigo-50 text-indigo-600' : 'border-gray-200 text-gray-500')}
            >
              <SlidersHorizontal size={18} />
            </button>
          </div>

          {/* Category pills */}
          <div className="flex gap-2 overflow-x-auto no-scrollbar pb-1">
            {CATEGORIES.map(c => (
              <button
                key={c.id}
                onClick={() => { setCategory(c.id); search(query, c.id, maxPrice) }}
                className={cn(
                  'shrink-0 px-4 py-1.5 rounded-full text-sm font-medium transition-colors',
                  category === c.id
                    ? 'bg-indigo-600 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                )}
              >
                {c.label}
              </button>
            ))}
          </div>

          {/* Filters panel */}
          {showFilters && (
            <div className="bg-gray-50 rounded-2xl p-4 flex gap-4">
              <div className="flex-1">
                <label className="text-xs font-semibold text-gray-500 block mb-1">Max price</label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">$</span>
                  <input
                    type="number"
                    value={maxPrice}
                    onChange={e => setMaxPrice(e.target.value)}
                    onKeyDown={handleKey}
                    placeholder="Any"
                    className="w-full pl-7 pr-3 py-2 rounded-xl border border-gray-200 text-sm focus:outline-none focus:border-indigo-400 bg-white"
                  />
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Results */}
      <div className="max-w-3xl mx-auto px-4 py-6">
        {loading && (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="rounded-2xl overflow-hidden bg-gray-100 animate-pulse">
                <div className="aspect-square bg-gray-200" />
                <div className="p-3 space-y-2">
                  <div className="h-3 bg-gray-200 rounded w-3/4" />
                  <div className="h-3 bg-gray-200 rounded w-1/2" />
                </div>
              </div>
            ))}
          </div>
        )}

        {!loading && searched && results.length === 0 && (
          <div className="text-center py-16 space-y-2">
            <p className="text-gray-500 font-medium">No listings found for &ldquo;{query}&rdquo;</p>
            <p className="text-sm text-gray-400">Try a different search or check back later</p>
          </div>
        )}

        {!loading && results.length > 0 && (
          <>
            <p className="text-sm text-gray-400 mb-4">{results.length} results for &ldquo;{query}&rdquo;</p>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {results.map(listing => (
                <ListingCard key={listing.id} listing={listing} />
              ))}
            </div>
          </>
        )}

        {!loading && !searched && (
          <div className="text-center py-20 space-y-4">
            <div className="w-16 h-16 bg-indigo-50 rounded-full flex items-center justify-center mx-auto">
              <Search size={28} className="text-indigo-400" />
            </div>
            <p className="font-medium text-gray-700">What are you looking for?</p>
            <p className="text-sm text-gray-400">Search works with natural language — try &ldquo;something for my home gym&rdquo;</p>
          </div>
        )}
      </div>
    </div>
  )
}
