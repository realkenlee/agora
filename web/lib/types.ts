export type Condition = 'new' | 'like_new' | 'good' | 'fair' | 'poor'
export type ListingStatus = 'draft' | 'active' | 'pending' | 'sold' | 'removed'
export type OfferStatus = 'pending' | 'accepted' | 'rejected' | 'countered' | 'expired' | 'withdrawn'

export interface Location {
  lat: number
  lng: number
  text: string
}

export interface Seller {
  id: string
  display_name: string
  avatar_url: string | null
  trust_score: number
  sold_total: number
  avg_rating: number | null
  phone_verified: boolean
}

export interface Listing {
  id: string
  title: string
  description: string
  price: number
  condition: Condition
  category_id: string
  attributes: Record<string, string>
  location: Location
  status: ListingStatus
  price_negotiable: boolean
  photos: string[]
  seller: Seller
  listed_by: 'human' | 'agent'
  views: number
  created_at: string
  updated_at: string
}

export interface Offer {
  id: string
  listing_id: string
  buyer: Seller
  amount: number
  message: string | null
  status: OfferStatus
  counter_amount: number | null
  counter_message: string | null
  offered_by: 'human' | 'agent'
  responded_by: string | null
  created_at: string
  expires_at: string
  responded_at: string | null
}

export interface Message {
  id: string
  sender: Seller
  body: string
  sent_by: 'human' | 'agent'
  read_at: string | null
  created_at: string
}

export interface GeneratedListing {
  title: string
  description: string
  suggested_price: number
  condition: Condition
  category_id: string
  attributes: Record<string, string>
  price_negotiable: boolean
  reasoning: string
}
