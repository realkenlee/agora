"""Seed the database with test users and listings."""
import asyncio
import asyncpg
import json
import os
from dotenv import load_dotenv

load_dotenv()

LISTINGS = [
    {
        "title": "Trek FX 3 Disc Hybrid Bike — barely ridden",
        "description": "2022 Trek FX 3 Disc in matte grey. Size M. Only ridden maybe 5 times indoors. Still has original tires. Great commuter or fitness bike.",
        "category_id": "sports",
        "condition": "like_new",
        "price": 650,
        "price_negotiable": True,
        "attributes": {"brand": "Trek", "model": "FX 3 Disc", "year": "2022", "size": "M", "color": "Matte Grey"},
        "photos": ["https://images.unsplash.com/photo-1485965120184-e220f721d03e?w=800"],
        "lat": 37.7749, "lng": -122.4194, "location_text": "Mission District, SF",
    },
    {
        "title": "Sony WH-1000XM5 Noise Cancelling Headphones",
        "description": "Sony flagship ANC headphones. Excellent sound, 30hr battery. Comes with original case and cables. Switching to AirPods Max.",
        "category_id": "electronics",
        "condition": "good",
        "price": 220,
        "price_negotiable": True,
        "attributes": {"brand": "Sony", "model": "WH-1000XM5", "color": "Black"},
        "photos": ["https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=800"],
        "lat": 37.7751, "lng": -122.4175, "location_text": "Castro, SF",
    },
    {
        "title": "IKEA KALLAX 4x4 Shelf Unit — white",
        "description": "IKEA Kallax bookshelf/room divider. 4x4 grid, white. Some minor scuffs on the back panel, invisible once placed. Moving out, must go.",
        "category_id": "furniture",
        "condition": "good",
        "price": 80,
        "price_negotiable": False,
        "attributes": {"brand": "IKEA", "model": "KALLAX", "color": "White", "dimensions": "147x147cm"},
        "photos": ["https://images.unsplash.com/photo-1555041469-a586c61ea9bc?w=800"],
        "lat": 37.7695, "lng": -122.4184, "location_text": "Noe Valley, SF",
    },
    {
        "title": "Apple iPad Pro 12.9\" M2 256GB WiFi + Cellular",
        "description": "2022 iPad Pro M2 chip, 256GB, Space Grey. With Apple Pencil 2nd gen. Minor scratches on back corner (see photos). Battery health 97%.",
        "category_id": "electronics",
        "condition": "good",
        "price": 750,
        "price_negotiable": True,
        "attributes": {"brand": "Apple", "model": "iPad Pro M2", "storage": "256GB", "color": "Space Grey", "year": "2022"},
        "photos": ["https://images.unsplash.com/photo-1544244015-0df4b3ffc6b0?w=800"],
        "lat": 37.7785, "lng": -122.3892, "location_text": "Potrero Hill, SF",
    },
    {
        "title": "West Elm Peggy Mid-Century Sofa — performance velvet",
        "description": "West Elm Peggy 68\" sofa in sand performance velvet. About 2 years old, no stains, cushions still firm. Selling because we're upgrading.",
        "category_id": "furniture",
        "condition": "good",
        "price": 500,
        "price_negotiable": True,
        "attributes": {"brand": "West Elm", "model": "Peggy", "color": "Sand", "material": "Performance Velvet", "width": "68 inches"},
        "photos": ["https://images.unsplash.com/photo-1555041469-a586c61ea9bc?w=800"],
        "lat": 37.7693, "lng": -122.4432, "location_text": "Twin Peaks, SF",
    },
    {
        "title": "Vitamix A2300 Ascent Series Blender",
        "description": "Vitamix A2300 blender with self-detect capability. Used maybe 20 times. Still has factory warranty. Comes with 64oz container and tamper.",
        "category_id": "other",
        "condition": "like_new",
        "price": 320,
        "price_negotiable": True,
        "attributes": {"brand": "Vitamix", "model": "A2300 Ascent", "color": "Black"},
        "photos": ["https://images.unsplash.com/photo-1600857062241-98e5dba7f4e0?w=800"],
        "lat": 37.7912, "lng": -122.4018, "location_text": "Russian Hill, SF",
    },
    {
        "title": "Canon EOS R6 Mark II + RF 24-105mm f/4L",
        "description": "Canon EOS R6 Mark II with RF 24-105mm f/4L IS USM kit lens. Shutter count ~1200. Pristine condition, always used with UV filter.",
        "category_id": "electronics",
        "condition": "like_new",
        "price": 2800,
        "price_negotiable": True,
        "attributes": {"brand": "Canon", "model": "EOS R6 Mark II", "shutter_count": "1200", "includes": "24-105mm lens"},
        "photos": ["https://images.unsplash.com/photo-1516035069371-29a1b244cc32?w=800"],
        "lat": 37.7837, "lng": -122.4086, "location_text": "Hayes Valley, SF",
    },
    {
        "title": "Patagonia Torrentshell 3L Rain Jacket — Men's Large",
        "description": "Patagonia Torrentshell 3L jacket in Black, Men's Large. Excellent condition, DWR still active. Selling because I have too many jackets.",
        "category_id": "clothing",
        "condition": "like_new",
        "price": 120,
        "price_negotiable": False,
        "attributes": {"brand": "Patagonia", "model": "Torrentshell 3L", "size": "L", "color": "Black", "gender": "Men's"},
        "photos": ["https://images.unsplash.com/photo-1591047139829-d91aecb6caea?w=800"],
        "lat": 37.7719, "lng": -122.4060, "location_text": "SOMA, SF",
    },
    {
        "title": "Standing Desk — Uplift V2 72\"×30\" walnut top",
        "description": "Uplift V2 Commercial standing desk with 72x30 real walnut top. Dual motor, advanced control panel with memory presets. 3 years old, no wobble, works perfectly.",
        "category_id": "furniture",
        "condition": "good",
        "price": 650,
        "price_negotiable": True,
        "attributes": {"brand": "Uplift", "model": "V2 Commercial", "top": "Walnut", "size": "72×30\""},
        "photos": ["https://images.unsplash.com/photo-1593642532454-e138e28a63f4?w=800"],
        "lat": 37.7881, "lng": -122.4075, "location_text": "Lower Nob Hill, SF",
    },
    {
        "title": "Pinarello Dogma F12 — 56cm, Dura-Ace Di2",
        "description": "2021 Pinarello Dogma F12, 56cm. Full Shimano Dura-Ace R9170 Di2. Lightweight carbon Bora Ultra 50 wheels included. Race-ready, one season of light use.",
        "category_id": "sports",
        "condition": "good",
        "price": 7500,
        "price_negotiable": True,
        "attributes": {"brand": "Pinarello", "model": "Dogma F12", "size": "56cm", "groupset": "Dura-Ace R9170 Di2", "wheels": "Bora Ultra 50"},
        "photos": ["https://images.unsplash.com/photo-1471506480208-91b3a4cc78be?w=800"],
        "lat": 37.7761, "lng": -122.3957, "location_text": "Dogpatch, SF",
    },
    {
        "title": "PS5 Disc Edition + 3 games",
        "description": "PlayStation 5 disc edition in excellent condition. Includes God of War Ragnarok, Spider-Man 2, and FF XVI. Original controller + extra DualSense.",
        "category_id": "electronics",
        "condition": "good",
        "price": 420,
        "price_negotiable": True,
        "attributes": {"brand": "Sony", "model": "PlayStation 5", "includes": "3 games, 2 controllers"},
        "photos": ["https://images.unsplash.com/photo-1607853202273-797f1c22a38e?w=800"],
        "lat": 37.7727, "lng": -122.4311, "location_text": "The Castro, SF",
    },
    {
        "title": "Bialetti Moka Pot 6-cup + bag of Illy beans",
        "description": "Classic Bialetti stovetop espresso maker, 6-cup size. Used maybe 3 times — turns out I prefer pour-over. Comes with a sealed 250g bag of Illy Classico.",
        "category_id": "other",
        "condition": "like_new",
        "price": 30,
        "price_negotiable": False,
        "attributes": {"brand": "Bialetti", "size": "6-cup", "includes": "Illy Classico 250g"},
        "photos": ["https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?w=800"],
        "lat": 37.7615, "lng": -122.4349, "location_text": "Glen Park, SF",
    },
]

SELLER_NAMES = [
    ("Marcus", "Thompson", True, 12, 4.8),
    ("Sarah", "Chen", True, 7, 4.9),
    ("Alex", "Rivera", False, 3, 4.6),
    ("Jordan", "Kim", True, 24, 4.7),
]


async def seed():
    dsn = os.environ.get("DATABASE_URL", "postgresql://agora:agora@localhost:5432/agora")
    conn = await asyncpg.connect(dsn)

    print("Creating test users...")
    seller_ids = []
    for first, last, verified, sold, rating in SELLER_NAMES:
        user_id = await conn.fetchval("""
            INSERT INTO users (phone, display_name, phone_verified, sold_total, avg_rating)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (phone) DO UPDATE SET display_name = EXCLUDED.display_name
            RETURNING id
        """, f"+1555{len(seller_ids):07d}", f"{first} {last}", verified, sold, rating)
        seller_ids.append(user_id)
        print(f"  User: {first} {last} ({user_id})")

    print("\nCreating listings...")
    for i, listing in enumerate(LISTINGS):
        seller_id = seller_ids[i % len(seller_ids)]
        photos = listing.pop("photos")
        attributes = listing.pop("attributes")
        location_text = listing.pop("location_text")
        lat = listing.pop("lat")
        lng = listing.pop("lng")

        listing_id = await conn.fetchval("""
            INSERT INTO listings (seller_id, title, description, category_id, condition,
                attributes, price, price_negotiable, lat, lng, location_text, status, listed_by)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, $10, $11, 'active',
                CASE WHEN $12 % 3 = 0 THEN 'agent' ELSE 'human' END)
            RETURNING id
        """, seller_id, listing["title"], listing["description"], listing["category_id"],
            listing["condition"], json.dumps(attributes),
            listing["price"], listing["price_negotiable"], lat, lng, location_text, i)

        for j, photo_url in enumerate(photos):
            await conn.execute("""
                INSERT INTO listing_photos (listing_id, url, position)
                VALUES ($1, $2, $3)
            """, listing_id, photo_url, j)

        views = 10 + (i * 7) % 200
        await conn.execute("UPDATE listings SET views = $1 WHERE id = $2", views, listing_id)

        print(f"  {listing['title'][:50]}... → {listing_id}")

    print("\nSeeding complete!")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(seed())
