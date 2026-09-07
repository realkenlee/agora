# Agora — close-tool

Agora is a **seller close-tool**, not a marketplace browse feed. A seller lists a physical item, shares **one Stripe Checkout URL**, the buyer pays (funds held on the platform), the seller marks shipped, and funds **release to the seller via Stripe Connect**.

Buyers never search or browse. Agents (or Telegram) talk to the seller HTTP API.

## Hold → ship → release

1. Checkout Session charges the **platform** (separate charges and transfers, `transfer_group` on the PaymentIntent). No `transfer_data` — destination charges would pay out immediately.
2. `checkout.session.completed` moves the sale to `paid_held`.
3. Seller marks shipped. Agora creates a Transfer to the seller's **Connect Express** account (`source_transaction` ties it to the charge).
4. Connect onboarding is required **at payout**, not at list time. If Express is incomplete, `mark_shipped` returns `CONNECT_ONBOARDING_REQUIRED` plus an `onboarding_url`.
5. Dispute handling is a freeze stub (`disputed` blocks payout). There is no escrow court UI.

Sale statuses: `draft` → `listed` → `paid_held` → `shipped` → `released` (or `cancelled` / `disputed`).

## Dogfood one real item (Ken)

Credentials come from env / Stripe Projects. **Do not paste secret keys into chat or this file.**

```bash
# From the repo root
stripe projects env --pull          # writes local env files the CLI manages
# or set the same names in Railway / your host
```

Required:

| Env | Purpose |
| --- | --- |
| `DATABASE_URL` or `SUPABASE_POOLER_URL` | Postgres |
| `STRIPE_SECRET_KEY` | Platform secret (from Stripe Projects / Dashboard). Restricted key is fine if it can create Checkout Sessions, Transfers, Express accounts, Account Links |
| `STRIPE_WEBHOOK_SECRET` | For `POST /webhooks/stripe` |
| `WEB_URL` | Success/cancel + Connect return URLs |

Forward webhooks (local):

```bash
stripe listen --forward-to localhost:8000/webhooks/stripe
```

Paid LLM (recommended — free OpenRouter `:free` models cap at **50 requests/day** and will sink drafts):

```
LLM_BASE_URL=<provider OpenAI-compatible base>
LLM_API_KEY=<key>
LLM_MODEL=<text model id>
VISION_MODEL=<multimodal model id>
```

Leave `OPENROUTER_API_KEY` unset if you switched providers. `LLM_*` wins.

### End-to-end

Auth is `Authorization: Bearer <user uuid>` (same as today). Create a seller user or reuse yours.

```bash
export API=http://localhost:8000
export TOKEN=<your user uuid>

# 1. Optional — payouts only. You can list first and onboard later.
curl -s -X POST $API/me/connect/onboard -H "Authorization: Bearer $TOKEN"
# Open onboarding_url as the seller, then:
curl -s $API/me/connect -H "Authorization: Bearer $TOKEN"

# 2. Create the item (photo URL + title/price/floor)
curl -s -X POST $API/me/items \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "title": "Vintage arc floor lamp",
    "description": "Works. Minor scratches on the base.",
    "price": 55,
    "min_price": 40,
    "photo_urls": ["https://example.com/lamp.jpg"]
  }'

# 3. If checkout_url is missing, mint it
curl -s -X POST $API/me/items/<listing_id>/pay-link \
  -H "Authorization: Bearer $TOKEN"

# 4. Share that checkout_url. Buyer opens it — they never browse Agora.

# 5. After Checkout + webhook → sale_status is paid_held
curl -s $API/me/items/<listing_id> -H "Authorization: Bearer $TOKEN"

# 6. Ship it (releases the Transfer). If Connect is incomplete you get onboarding_url.
curl -s -X POST $API/me/items/<listing_id>/ship \
  -H "Authorization: Bearer $TOKEN"
```

Telegram path still works: photo + caption → listing. If Stripe is configured, the bot also sends the pay link. Reply `CONNECT` to onboard, `SHIPPED` after you send the item, `UNDO` to take a listing down.

Agent path (Grok Bot / MCP): `list_my_items`, `create_item`, `mint_pay_link`, `mark_shipped`, `get_sale_status`, `get_connect_status`, `start_connect_onboarding`.

## Agent HTTP surface

| Method | Path | What |
| --- | --- | --- |
| GET | `/me/items` | Your inventory + pay link + sale status |
| POST | `/me/items` | Create from photo URLs + title/price/floor |
| GET | `/me/items/{id}` | One item + sale |
| POST | `/me/items/{id}/pay-link` | Mint Checkout URL |
| POST | `/me/items/{id}/ship` | Ship + release |
| POST | `/me/items/{id}/cancel` | Cancel a listed sale |
| GET | `/sales/{id}` | Sale status |
| GET/POST | `/me/connect`, `/me/connect/onboard` | Express onboarding |
| POST | `/webhooks/stripe` | Checkout paid, dispute freeze, account.updated |

Existing listing/offer/Telegram routes stay; this slice does not add buyer search.

## Tests

```bash
pip install -r requirements.txt
python -m pytest tests/ -q
```
