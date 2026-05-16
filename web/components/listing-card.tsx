import Link from 'next/link'
import { MapPin, Bot } from 'lucide-react'
import { cn, formatPrice, formatRelativeTime, CONDITION_LABELS, CONDITION_COLORS } from '@/lib/utils'
import type { Listing } from '@/lib/types'

export default function ListingCard({ listing, distanceMi }: { listing: Listing; distanceMi?: number }) {
  const photo = listing.photos[0]

  return (
    <Link href={`/listings/${listing.id}`} className="group block">
      <div className="rounded-2xl overflow-hidden bg-gray-50 border border-gray-100 hover:border-indigo-200 hover:shadow-md transition-all">
        {/* Photo */}
        <div className="aspect-square relative overflow-hidden bg-gray-100">
          {photo ? (
            <img
              src={photo}
              alt={listing.title}
              className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-gray-300">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="currentColor">
                <path d="M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-1.1 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z"/>
              </svg>
            </div>
          )}
          {listing.listed_by === 'agent' && (
            <div className="absolute top-2 left-2 bg-indigo-600 text-white text-xs font-medium px-2 py-0.5 rounded-full flex items-center gap-1">
              <Bot size={10} />
              Agent
            </div>
          )}
          <div className={cn(
            'absolute top-2 right-2 text-xs font-medium px-2 py-0.5 rounded-full',
            CONDITION_COLORS[listing.condition]
          )}>
            {CONDITION_LABELS[listing.condition]}
          </div>
        </div>

        {/* Info */}
        <div className="p-3 space-y-1">
          <div className="flex items-start justify-between gap-2">
            <p className="font-semibold text-gray-900 text-sm leading-tight line-clamp-2">
              {listing.title}
            </p>
            <p className="font-bold text-indigo-600 text-sm shrink-0">
              {formatPrice(listing.price)}
            </p>
          </div>
          <div className="flex items-center gap-1 text-gray-400 text-xs">
            <MapPin size={11} />
            <span className="truncate">{listing.location.text}</span>
            {distanceMi != null && (
              <span className="ml-auto shrink-0 text-indigo-500 font-medium">
                {distanceMi < 0.1 ? '<0.1' : distanceMi.toFixed(1)} mi
              </span>
            )}
            {distanceMi == null && (
              <span className="ml-auto shrink-0">{formatRelativeTime(listing.created_at)}</span>
            )}
          </div>
        </div>
      </div>
    </Link>
  )
}
