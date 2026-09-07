"""
API contract — Pydantic schemas for every request/response.

These are intentionally structured (not free-text blobs) so agents
can reason about them without parsing prose.
"""

from __future__ import annotations
from decimal import Decimal
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────────────────────

class Condition(str, Enum):
    new       = "new"
    like_new  = "like_new"
    good      = "good"
    fair      = "fair"
    poor      = "poor"


class ListingStatus(str, Enum):
    draft    = "draft"
    active   = "active"
    pending  = "pending"
    sold     = "sold"
    removed  = "removed"


class OfferStatus(str, Enum):
    pending   = "pending"
    accepted  = "accepted"
    rejected  = "rejected"
    countered = "countered"
    expired   = "expired"
    withdrawn = "withdrawn"


# ── Shared primitives ─────────────────────────────────────────────────────────

class Location(BaseModel):
    lat:  float
    lng:  float
    text: str   # "Austin, TX"


class UserSummary(BaseModel):
    id:            UUID
    display_name:  str
    avatar_url:    Optional[str] = None
    trust_score:   float
    sold_total:    int
    avg_rating:    Optional[float] = None
    phone_verified: bool


# ── Listings ──────────────────────────────────────────────────────────────────

class CreateListingRequest(BaseModel):
    title:               str     = Field(..., min_length=3, max_length=200)
    description:         str     = Field(..., min_length=10, max_length=2000)
    price:               Decimal = Field(..., gt=0)
    condition:           Condition
    category_id:         str
    location:            Location
    # Structured attributes are key for agent search — agents filter on these,
    # not on prose description. e.g. {"brand":"Trek","size":"M","color":"red"}
    attributes:          dict    = {}
    price_negotiable:    bool    = True
    # Private floor — never returned to buyers; only seller/their agent sees it
    min_price:           Optional[Decimal] = None
    photo_urls:          list[str] = []
    listed_by:           str    = "human"


class UpdateListingRequest(BaseModel):
    title:            Optional[str]     = None
    description:      Optional[str]     = None
    price:            Optional[Decimal] = None
    condition:        Optional[Condition] = None
    attributes:       Optional[dict]    = None
    price_negotiable: Optional[bool]    = None
    min_price:        Optional[Decimal] = None
    status:           Optional[ListingStatus] = None


class ListingResponse(BaseModel):
    id:               UUID
    title:            str
    description:      str
    price:            Decimal
    condition:        Condition
    category_id:      Optional[str]
    attributes:       dict
    location:         Location
    status:           ListingStatus
    price_negotiable: bool
    photos:           list[str]
    seller:           UserSummary
    listed_by:        str
    views:            int
    created_at:       datetime
    updated_at:       datetime
    # min_price intentionally excluded — private
    # agent-readable state: valid next actions, key metadata
    state:            Optional[dict] = None


# ── Search ────────────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query:        str
    location:     Optional[Location]   = None
    radius_miles: float                = Field(25, gt=0, le=500)
    max_price:    Optional[Decimal]    = None
    min_price:    Optional[Decimal]    = None
    category_id:  Optional[str]        = None
    condition:    Optional[list[Condition]] = None
    limit:        int                  = Field(20, ge=1, le=100)
    offset:       int                  = Field(0,  ge=0)


class SearchResult(BaseModel):
    listing:      ListingResponse
    score:        float   # relevance 0-1
    distance_mi:  Optional[float] = None


class SearchResponse(BaseModel):
    results:  list[SearchResult]
    total:    int
    query:    str


# ── Offers ────────────────────────────────────────────────────────────────────

class CreateOfferRequest(BaseModel):
    amount:   Decimal = Field(..., gt=0)
    message:  Optional[str] = None
    offered_by: str = "human"


class RespondOfferRequest(BaseModel):
    action:         str     = Field(..., pattern="^(accept|reject|counter)$")
    counter_amount: Optional[Decimal] = None
    message:        Optional[str]     = None
    responded_by:   str = "human"


class OfferResponse(BaseModel):
    id:              UUID
    listing_id:      UUID
    buyer:           UserSummary
    amount:          Decimal
    message:         Optional[str]
    status:          OfferStatus
    counter_amount:  Optional[Decimal]
    counter_message: Optional[str]
    offered_by:      str
    responded_by:    Optional[str]
    created_at:      datetime
    expires_at:      datetime
    responded_at:    Optional[datetime]
    state:           Optional[dict] = None


# ── Messages ──────────────────────────────────────────────────────────────────

class SendMessageRequest(BaseModel):
    body:    str = Field(..., min_length=1, max_length=2000)
    sent_by: str = "human"


class MessageResponse(BaseModel):
    id:           UUID
    sender:       UserSummary
    body:         str
    sent_by:      str
    read_at:      Optional[datetime]
    created_at:   datetime


# ── AI endpoints ──────────────────────────────────────────────────────────────

class GenerateListingRequest(BaseModel):
    """Casual description → structured listing draft."""
    description:  str             = ""
    price_hint:   Optional[float] = None
    location:     Optional[Location] = None
    photo_urls:   list[str]       = []


class GenerateListingResponse(BaseModel):
    """Structured draft ready to review and post via POST /listings."""
    title:            str
    description:      str
    suggested_price:  float
    condition:        Condition
    category_id:      str
    attributes:       dict
    price_negotiable: bool
    reasoning:        str


class GenerateJobResponse(BaseModel):
    """Returned immediately from POST /ai/generate — processing happens async."""
    draft_id: UUID
    status:   str = "processing"


class DraftResponse(BaseModel):
    id:         UUID
    status:     str
    draft:      Optional[dict]     = None
    error:      Optional[str]      = None
    created_at: datetime


class NotificationResponse(BaseModel):
    id:          UUID
    type:        str
    title:       str
    body:        str
    action_type: str
    action_url:  Optional[str]     = None
    payload:     dict
    read_at:     Optional[datetime] = None
    created_at:  datetime


# ── Close-tool (seller inventory + pay link) ──────────────────────────────────

class CreateItemRequest(BaseModel):
    """Seller inventory item. Not a browse-feed listing."""
    title:       str = Field(..., min_length=3, max_length=200)
    description: Optional[str] = None
    price:       Decimal = Field(..., gt=0)
    min_price:   Optional[Decimal] = None  # private floor
    photo_urls:  list[str] = []
    condition:   Condition = Condition.good
    category_id: str = "other"
    mint_pay_link: bool = True


class ConnectOnboardResponse(BaseModel):
    account_id:      Optional[str] = None
    onboarding_url:  Optional[str] = None
    required_for:    str = "payout"
    note:            Optional[str] = None
