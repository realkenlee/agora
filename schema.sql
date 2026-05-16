-- Agora Marketplace Schema
-- Agent-native: every entity is designed to be readable and writable by AI agents

CREATE EXTENSION IF NOT EXISTS vector;       -- semantic search
CREATE EXTENSION IF NOT EXISTS "uuid-ossp"; -- uuid_generate_v4()
CREATE EXTENSION IF NOT EXISTS pg_trgm;     -- fast text search fallback

-- ── Users ────────────────────────────────────────────────────────────────────

CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email           TEXT UNIQUE,
    phone           TEXT UNIQUE,
    display_name    TEXT NOT NULL,
    avatar_url      TEXT,
    -- default location for listings + search
    default_lat     DOUBLE PRECISION,
    default_lng     DOUBLE PRECISION,
    default_location TEXT,
    -- trust signals
    phone_verified  BOOLEAN DEFAULT FALSE,
    trust_score     NUMERIC(3,2) DEFAULT 0.50 CHECK (trust_score BETWEEN 0 AND 1),
    -- lifetime stats (denormalized for agent queries)
    listings_total  INT DEFAULT 0,
    sold_total      INT DEFAULT 0,
    avg_rating      NUMERIC(3,2),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    last_active_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ── Agent Sessions ────────────────────────────────────────────────────────────
-- Agents get their own identity so actions are auditable and permissioned.

CREATE TABLE agent_sessions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash      TEXT UNIQUE NOT NULL,
    name            TEXT,                       -- "My Claude", "Shopping Bot"
    -- scoped permissions
    can_list        BOOLEAN DEFAULT TRUE,
    can_offer       BOOLEAN DEFAULT TRUE,
    can_message     BOOLEAN DEFAULT TRUE,
    max_offer       NUMERIC(10,2),              -- agent can't bid above this without human approval
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    last_used_at    TIMESTAMPTZ DEFAULT NOW(),
    expires_at      TIMESTAMPTZ
);

-- ── Categories ────────────────────────────────────────────────────────────────
-- Hierarchical. Stored as path strings: "electronics/phones/smartphones"

CREATE TABLE categories (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    parent_id       TEXT REFERENCES categories(id),
    common_attrs    JSONB DEFAULT '[]'  -- e.g. [{"key":"brand"},{"key":"size"}]
);

INSERT INTO categories VALUES
    ('electronics',          'Electronics',          NULL, '[{"key":"brand"},{"key":"model"}]'),
    ('electronics/phones',   'Phones',               'electronics', '[{"key":"brand"},{"key":"model"},{"key":"storage"},{"key":"color"}]'),
    ('electronics/laptops',  'Laptops',              'electronics', '[{"key":"brand"},{"key":"model"},{"key":"ram"},{"key":"storage"}]'),
    ('clothing',             'Clothing',             NULL, '[{"key":"brand"},{"key":"size"},{"key":"color"},{"key":"gender"}]'),
    ('furniture',            'Furniture',            NULL, '[{"key":"brand"},{"key":"material"},{"key":"color"},{"key":"dimensions"}]'),
    ('vehicles',             'Vehicles',             NULL, '[{"key":"make"},{"key":"model"},{"key":"year"},{"key":"mileage"},{"key":"color"}]'),
    ('sports',               'Sports & Outdoors',    NULL, '[{"key":"brand"},{"key":"size"}]'),
    ('books',                'Books',                NULL, '[{"key":"author"},{"key":"isbn"},{"key":"publisher"}]'),
    ('tools',                'Tools & Hardware',     NULL, '[{"key":"brand"},{"key":"model"}]'),
    ('garden',               'Garden & Outdoor',     NULL, '[{"key":"brand"}]'),
    ('toys',                 'Toys & Games',         NULL, '[{"key":"brand"},{"key":"age_range"}]'),
    ('other',                'Other',                NULL, '[]');

-- ── Listings ─────────────────────────────────────────────────────────────────

CREATE TABLE listings (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    seller_id       UUID REFERENCES users(id) ON DELETE SET NULL,
    -- content
    title           TEXT NOT NULL CHECK (length(title) BETWEEN 3 AND 200),
    description     TEXT NOT NULL CHECK (length(description) >= 10),
    category_id     TEXT REFERENCES categories(id),
    condition       TEXT NOT NULL CHECK (condition IN ('new','like_new','good','fair','poor')),
    -- structured attributes — agents query these directly, not prose
    -- e.g. {"brand":"Trek","size":"M","color":"red","year":2021}
    attributes      JSONB DEFAULT '{}',
    -- pricing
    price           NUMERIC(10,2) NOT NULL CHECK (price > 0),
    currency        TEXT DEFAULT 'USD',
    price_negotiable BOOLEAN DEFAULT TRUE,
    min_price       NUMERIC(10,2),  -- PRIVATE: never returned to buyers; seller/agent only
    -- location
    lat             DOUBLE PRECISION NOT NULL,
    lng             DOUBLE PRECISION NOT NULL,
    location_text   TEXT NOT NULL,
    -- status state machine: draft → active → (pending|sold|removed)
    status          TEXT DEFAULT 'active' CHECK (status IN ('draft','active','pending','sold','removed')),
    -- semantic search vector (384-dim, all-MiniLM-L6-v2)
    embedding       vector(384),
    -- audit
    listed_by       TEXT DEFAULT 'human' CHECK (listed_by IN ('human','agent')),
    views           INT DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    expires_at      TIMESTAMPTZ DEFAULT NOW() + INTERVAL '30 days'
);

CREATE TABLE listing_photos (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    listing_id      UUID NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    url             TEXT NOT NULL,
    position        SMALLINT DEFAULT 0,
    ai_caption      TEXT,   -- what Claude sees in the photo
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── Offers — the agent negotiation protocol ──────────────────────────────────
-- A state machine. Both sides can be human or agent.

CREATE TABLE offers (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    listing_id      UUID NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    buyer_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- offer
    amount          NUMERIC(10,2) NOT NULL CHECK (amount > 0),
    message         TEXT,
    -- state: pending → accepted / rejected / countered / expired / withdrawn
    status          TEXT DEFAULT 'pending'
                    CHECK (status IN ('pending','accepted','rejected','countered','expired','withdrawn')),
    -- counter (set when seller counters)
    counter_amount  NUMERIC(10,2),
    counter_message TEXT,
    -- audit: who acted (human vs agent on each side)
    offered_by      TEXT DEFAULT 'human' CHECK (offered_by  IN ('human','agent')),
    responded_by    TEXT               CHECK (responded_by IN ('human','agent')),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    responded_at    TIMESTAMPTZ,
    expires_at      TIMESTAMPTZ DEFAULT NOW() + INTERVAL '24 hours'
);

-- ── Messages ──────────────────────────────────────────────────────────────────

CREATE TABLE messages (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    listing_id      UUID NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    sender_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    recipient_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    body            TEXT NOT NULL CHECK (length(body) BETWEEN 1 AND 2000),
    sent_by         TEXT DEFAULT 'human' CHECK (sent_by IN ('human','agent')),
    read_at         TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── Reviews ───────────────────────────────────────────────────────────────────

CREATE TABLE reviews (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    listing_id      UUID NOT NULL REFERENCES listings(id),
    reviewer_id     UUID NOT NULL REFERENCES users(id),
    reviewee_id     UUID NOT NULL REFERENCES users(id),
    role            TEXT NOT NULL CHECK (role IN ('buyer','seller')),
    rating          SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment         TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (listing_id, reviewer_id)
);

-- ── Indexes ───────────────────────────────────────────────────────────────────

-- listings
CREATE INDEX idx_listings_status      ON listings(status);
CREATE INDEX idx_listings_seller      ON listings(seller_id);
CREATE INDEX idx_listings_category    ON listings(category_id);
CREATE INDEX idx_listings_price       ON listings(price);
CREATE INDEX idx_listings_condition   ON listings(condition);
CREATE INDEX idx_listings_updated     ON listings(updated_at DESC);
-- geo: distance queries
CREATE INDEX idx_listings_geo         ON listings USING GIST (ll_to_earth(lat, lng));
-- semantic: ANN search with cosine distance
CREATE INDEX idx_listings_embedding   ON listings USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
-- full-text fallback when embedding search returns nothing
CREATE INDEX idx_listings_fts         ON listings USING GIN (to_tsvector('english', title || ' ' || description));

-- offers / messages
CREATE INDEX idx_offers_listing       ON offers(listing_id, status);
CREATE INDEX idx_offers_buyer         ON offers(buyer_id, status);
CREATE INDEX idx_messages_thread      ON messages(listing_id, created_at);
CREATE INDEX idx_messages_unread      ON messages(recipient_id, read_at) WHERE read_at IS NULL;

-- ── Auto-update updated_at ────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION touch_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$;

CREATE TRIGGER listings_updated_at
    BEFORE UPDATE ON listings
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

CREATE TABLE IF NOT EXISTS listing_drafts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'processing',
    description TEXT,
    price_hint FLOAT,
    draft JSONB,
    error TEXT,
    telegram_chat_id BIGINT,
    brand_candidates JSONB,
    confirmed_brand TEXT,
    photo_urls JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS telegram_accounts (
    chat_id BIGINT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    first_name TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ai_usage_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    endpoint TEXT NOT NULL,
    user_id UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
