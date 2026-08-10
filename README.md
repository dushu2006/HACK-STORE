# HACK STORE — Indian tech gear for hackathons

A small, real-world Indian e-commerce platform that sells hackathon gear (mouse, keyboard, notebooks, pens, earphones, headphones, laptop stand, USB hub, power bank) with prices in **₹** (MRP + sale). Built deliberately small so a separate tool **API Doctor** can diagnose the backend end-to-end in ~5 minutes.

**Stack:** Python 3.11 + FastAPI + Uvicorn + sqlite3 + Pydantic v2 (frontend: single-page static HTML/CSS/vanilla JS — no build step).

---

## Design decisions

**Frontend/backend separation (critical):** Frontend is served as static files by FastAPI and talks to the backend **ONLY over HTTP via the documented JSON API**. The frontend never duplicates business logic (no client-side price computation that mirrors server logic, no client-side order validation). All business rules — price totals, stock checks, delivery fee/ETA, payment, notification — live in the backend. This keeps API Doctor's job clean: bugs are in backend code and fixable there.

**Backend intentionally small:** Single FastAPI app (`main.py`), flat files, no layered over-engineering, no microservices, queues or workers. Max ~6 real endpoints (`/api/products`, `/api/products/{id}`, `/api/orders`, `/api/orders/{id}`, `/api/orders` list, `/api/health` + `/api/debug/bug`). Fewer files = faster code retrieval & sandbox copies for API Doctor.

**SQLite auto-seeded:** On startup `db.py` creates tables if missing and seeds 9 products + 3 users + 3 orders. One user (`rohan@example.com`) has `payment_method_token = NULL` (triggers the **code** bug) and one order has status `"shipped"` which is **outside** the response Enum `pending/paid/delivered` (triggers the **db** bug when the flag is on).

**Mock integrations behind tiny providers:** Each integration lives in its own module `providers/payment.py`, `providers/delivery.py`, `providers/notifier.py`, `db.py`, so toggle flags are trivial. Delivery uses browser Geolocation (lat/lng) + free Nominatim reverse-geocode or a 6-digit Indian pincode fallback — no Google billing.

---

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # optional
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
# open http://localhost:8000
# API docs at http://localhost:8000/docs
```

SQLite file `hack_store.db` is created & seeded automatically on first launch. Delete it to re-seed.

### Render (free tier)

- Build: `pip install -r requirements.txt`
- Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- No external DB needed. Set env vars from `.env.example` if you want (optional).

---

## API

| Method | Path | Description |
|---|---|---|
| GET | `/api/products` | list catalog |
| GET | `/api/products/{id}` | single product |
| POST | `/api/orders` | place order — validates, charges payment, computes delivery, deducts stock, writes order, notifies; body `{items:[{product_id,qty}], customer:{name,email}, delivery:{lat,lng,pincode}}` → `{order_id,total_inr,delivery_fee_inr,grand_total_inr,eta}` |
| GET | `/api/orders` | list orders (filters `shipped` when `db` flag off, includes it when on → ValidationError) |
| GET | `/api/orders/{id}` | order detail (same Enum serialization) |
| GET | `/api/health` | `{status, checks:{db,payment,delivery,notifier}, flags}` |
| POST | `/api/debug/bug?scenario=<id>&on=true` | toggle bug flags |

Health polls every 5s in the frontend header.

---

## Debug / bug-toggle endpoint (deterministic failures)

All flags are in-memory (`flags.py`). When **off**, everything works. When **on**, ordering or listing triggers a **real Python exception + traceback** returned as `{"detail": str(e), "traceback": "<full>"}` with HTTP 500.

| Scenario | How to trigger | Exception |
|---|---|---|
| `payment` | `POST /api/debug/bug?scenario=payment&on=true` then `POST /api/orders` | `ConnectionError` (mock Razorpay down) |
| `delivery` | `...?scenario=delivery&on=true` then order | `ConnectionError` (mock Nominatim down) |
| `config` | `...?scenario=config&on=true` then order | `EnvironmentError` (reads `WRONG_NAME` instead of `PAYMENT_PUBLISHABLE_KEY`) |
| `code` | `...?scenario=code&on=true` then order with `customer.email=rohan@example.com` (user has `payment_method=None`) | `AttributeError: 'NoneType' object has no attribute 'token'` |
| `db` | `...?scenario=db&on=true` then `GET /api/orders` or `GET /api/orders/3` | `pydantic.ValidationError` (`shipped` not in `pending/paid/delivered`) |

Reset: `POST /api/debug/bug?scenario=<id>&on=false` or `Debug panel → Reset all flags`.

Example with curl:

```bash
# healthy order (Mumbai pincode fallback)
curl -s http://localhost:8000/api/products | head

curl -s -X POST http://localhost:8000/api/orders -H 'Content-Type: application/json' -d '{
  "items":[{"product_id":1,"qty":1}],
  "customer":{"name":"Aarav","email":"aarav@example.com"},
  "delivery":{"pincode":"400001"}
}' | jq

# trigger payment bug
curl -s -X POST "http://localhost:8000/api/debug/bug?scenario=payment&on=true"
curl -s -X POST http://localhost:8000/api/orders -H 'Content-Type: application/json' -d '...'  # → 500 + traceback

# trigger db bug
curl -s -X POST "http://localhost:8000/api/debug/bug?scenario=db&on=true"
curl -s http://localhost:8000/api/orders  # → 500 ValidationError

# use rohan to trigger code bug
curl -s -X POST "http://localhost:8000/api/debug/bug?scenario=code&on=true"
curl -s -X POST http://localhost:8000/api/orders -H 'Content-Type: application/json' -d '{
  "items":[{"product_id":1,"qty":1}],
  "customer":{"name":"Rohan Mehta","email":"rohan@example.com"},
  "delivery":{"pincode":"110001"}
}' | jq  # → 500 AttributeError
```

All 500s include the real traceback for API Doctor to parse.

---

## Frontend

- Header: logo, cart count, live system pill (polls `/api/health`)
- Hero with tagline for hackers
- Product grid: emoji image, MRP struck, sale in ₹, stock, Add to Cart
- Cart drawer: line items, subtotal, Proceed to Checkout
- Checkout: name/email, 📍 Use my location (Geolocation + Nominatim), manual pincode, Place Order → POST `/api/orders`
- Orders view: table highlighting any serialization failure
- Debug panel (footer): toggles for all 5 bug scenarios via `/api/debug/bug`
- Dark, premium tech-store aesthetic, monospace prices/IDs, rounded cards, toasts, skeletons.

Consumes **only** real backend endpoints — no fake data.

---

## Project structure

```
main.py              # FastAPI app, 6 endpoints, static serving
db.py                # SQLite init & seed
flags.py             # in-memory bug flag store
providers/
  payment.py         # mock Razorpay (flags: payment/config/code)
  delivery.py        # mock Nominatim/pincode (flag: delivery)
  notifier.py        # mock Resend
static/
  index.html
  style.css
  app.js
requirements.txt
.env.example
hack_store.db        # git-ignored, auto-created
```

---

## Notes

- Prices are integers in INR, displayed with `₹` formatting.
- Browser Geolocation is optional; pincode (6-digit) is the fallback.
- Notifier is a mock that logs to stdout; no real email required.
- Every 500 returns `{"detail": ..., "traceback": ...}`.
