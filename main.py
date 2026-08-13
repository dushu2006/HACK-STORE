import os
import json
import traceback
import sqlite3
import datetime
from enum import Enum
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from db import init_db, get_conn
from flags import bug_flags
from providers.payment import charge_payment
from providers.delivery import compute_delivery
from providers.notifier import send_order_confirmation

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = FastAPI(title="HACK STORE API", version="1.0.0")

# Ensure a dummy real env var exists so config bug message is meaningful
os.environ.setdefault("PAYMENT_PUBLISHABLE_KEY", "pk_test_razorpay_mock_12345")

# Init DB on startup
@app.on_event("startup")
def startup():
    init_db()
    print("[main] HACK STORE ready — flags:", bug_flags)

# Also init synchronously for cases where startup event isn't triggered (e.g., import)
try:
    init_db()
except Exception as e:
    print(f"[main] init_db fallback error: {e}")

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class ProductOut(BaseModel):
    id: int
    name: str
    category: str
    description: str
    image: str
    mrp_inr: int
    price_inr: int
    stock: int

class OrderStatus(str, Enum):
    pending = "pending"
    paid = "paid"
    delivered = "delivered"
    # NOTE: "shipped" is intentionally NOT in Enum -> triggers db bug when stored

class CustomerIn(BaseModel):
    name: str = Field(..., min_length=1)
    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

class DeliveryIn(BaseModel):
    lat: Optional[float] = None
    lng: Optional[float] = None
    pincode: Optional[str] = None

class OrderItemIn(BaseModel):
    product_id: int
    qty: int = Field(..., gt=0)

class OrderCreate(BaseModel):
    items: List[OrderItemIn]
    customer: CustomerIn
    delivery: DeliveryIn

class OrderOut(BaseModel):
    order_id: int
    customer: CustomerIn
    items: list
    total_inr: int
    delivery_fee_inr: int
    grand_total_inr: int
    status: OrderStatus
    delivery_city: Optional[str] = None
    delivery_pincode: Optional[str] = None
    delivery_lat: Optional[float] = None
    delivery_lng: Optional[float] = None
    eta: Optional[str] = None
    created_at: str

class HealthOut(BaseModel):
    status: str
    checks: dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def row_to_dict(row):
    return {k: row[k] for k in row.keys()}

def make_traceback_response(e: Exception, status_code: int = 500):
    tb = traceback.format_exc()
    # log for server
    print(f"[error] {type(e).__name__}: {e}\n{tb}")
    return JSONResponse(status_code=status_code, content={"detail": str(e), "traceback": tb})

# ---------------------------------------------------------------------------
# API endpoints (<=6 real work endpoints as per spec)
# ---------------------------------------------------------------------------
@app.get("/api/products", response_model=List[ProductOut])
def list_products():
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM products ORDER BY id")
        rows = cur.fetchall()
        conn.close()
        return [row_to_dict(r) for r in rows]
    except Exception as e:
        # real traceback
        return make_traceback_response(e)

@app.get("/api/products/{product_id}", response_model=ProductOut)
def get_product(product_id: int):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM products WHERE id=?", (product_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            raise HTTPException(status_code=404, detail="Product not found")
        return row_to_dict(row)
    except HTTPException:
        raise
    except Exception as e:
        return make_traceback_response(e)

@app.post("/api/orders")
async def place_order(payload: OrderCreate):
    """
    Ordering flow: validates -> charges payment -> computes delivery -> deducts stock -> writes order -> notifies
    Fires integrations: payment, delivery, notifier, db
    Bug flags cause REAL exceptions with tracebacks.
    """
    try:
        # Basic validation
        if not payload.items:
            raise HTTPException(status_code=400, detail="Cart is empty")

        conn = get_conn()
        cur = conn.cursor()

        # Fetch products and validate stock
        total_inr = 0
        enriched_items = []
        for it in payload.items:
            cur.execute("SELECT * FROM products WHERE id=?", (it.product_id,))
            prod = cur.fetchone()
            if not prod:
                conn.close()
                raise HTTPException(status_code=400, detail=f"Product {it.product_id} not found")
            if prod["stock"] < it.qty:
                conn.close()
                raise HTTPException(status_code=400, detail=f"Insufficient stock for {prod['name']}: have {prod['stock']}, need {it.qty}")
            total_inr += prod["price_inr"] * it.qty
            enriched_items.append({
                "product_id": prod["id"],
                "name": prod["name"],
                "price_inr": prod["price_inr"],
                "qty": it.qty,
                "subtotal_inr": prod["price_inr"] * it.qty,
            })

        # Delivery: compute fee + ETA (may raise ConnectionError if delivery flag on, or ValueError for bad pincode)
        try:
            delivery_info = compute_delivery(payload.delivery.lat, payload.delivery.lng, payload.delivery.pincode, bug_flags)
        except ValueError as ve:
            # invalid pincode -> client error, not 500
            conn.close()
            raise HTTPException(status_code=400, detail=str(ve))
        delivery_fee = delivery_info["fee_inr"]
        delivery_city = delivery_info["city"]
        eta = delivery_info["eta"]
        grand_total = total_inr + delivery_fee

        # Payment: lookup user by email to get saved payment token (code bug path)
        cur.execute("SELECT * FROM users WHERE email=?", (payload.customer.email,))
        user_row = cur.fetchone()
        user_id = user_row["id"] if user_row else None
        token = user_row["payment_method_token"] if user_row else None
        # For guest checkout (no user), token will be None but code bug only triggers for known user rohan@example.com
        # charge_payment will raise AttributeError if code flag is on and token is None (missing guard)
        charge_result = charge_payment(grand_total, token, bug_flags)

        # Deduct stock (within transaction)
        for it in payload.items:
            cur.execute("UPDATE products SET stock = stock - ? WHERE id=?", (it.qty, it.product_id))

        # Write order
        now = datetime.datetime.utcnow().isoformat()
        items_json = json.dumps(enriched_items)
        cur.execute("""
            INSERT INTO orders (customer_name, customer_email, user_id, items_json, total_inr, delivery_fee_inr, grand_total_inr, status, delivery_city, delivery_pincode, delivery_lat, delivery_lng, eta, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            payload.customer.name,
            payload.customer.email,
            user_id,
            items_json,
            total_inr,
            delivery_fee,
            grand_total,
            "paid",  # new orders are paid after charge
            delivery_city,
            payload.delivery.pincode,
            payload.delivery.lat,
            payload.delivery.lng,
            eta,
            now,
        ))
        order_id = cur.lastrowid
        conn.commit()
        conn.close()

        # Notify (mock email) - failures are not fatal for order, but we log
        try:
            send_order_confirmation(payload.customer.email, order_id, grand_total, bug_flags)
        except Exception as ne:
            # log but don't fail order; however if notifier flag is used we could propagate
            print(f"[notifier] failed: {ne}")

        return {
            "order_id": order_id,
            "total_inr": total_inr,
            "delivery_fee_inr": delivery_fee,
            "grand_total_inr": grand_total,
            "eta": eta,
            "status": "paid",
            "delivery_city": delivery_city,
            "payment": charge_result,
        }

    except HTTPException:
        raise
    except Exception as e:
        # Includes ConnectionError (payment/delivery), EnvironmentError (config), AttributeError (code), ValueError (pincode)
        return make_traceback_response(e)

@app.get("/api/orders")
def list_orders():
    try:
        conn = get_conn()
        cur = conn.cursor()
        # When db bug flag is OFF, we hide the bad 'shipped' order to keep API working.
        # When ON, we include it and Pydantic validation will fail (shipped not in Enum)
        if bug_flags.get("db"):
            cur.execute("SELECT * FROM orders ORDER BY id DESC")
        else:
            cur.execute("SELECT * FROM orders WHERE status IN ('pending','paid','delivered') ORDER BY id DESC")
        rows = cur.fetchall()
        conn.close()

        # Build response list and validate via Pydantic OrderOut (this is where db bug triggers)
        result = []
        for r in rows:
            # Attempt to construct OrderOut - will raise ValidationError if status is 'shipped' and flag is on
            order_dict = {
                "order_id": r["id"],
                "customer": {"name": r["customer_name"], "email": r["customer_email"]},
                "items": json.loads(r["items_json"]),
                "total_inr": r["total_inr"],
                "delivery_fee_inr": r["delivery_fee_inr"],
                "grand_total_inr": r["grand_total_inr"],
                "status": r["status"],  # ValidationError if 'shipped'
                "delivery_city": r["delivery_city"],
                "delivery_pincode": r["delivery_pincode"],
                "delivery_lat": r["delivery_lat"],
                "delivery_lng": r["delivery_lng"],
                "eta": r["eta"],
                "created_at": r["created_at"],
            }
            # Normalize 'shipped' status to 'delivered' for schema compatibility
            if order_dict.get("status") == "shipped":
                order_dict["status"] = "delivered"
            # Explicit validation - will raise if status invalid
            validated = OrderOut(**order_dict)
            result.append(validated.model_dump())

        return result
    except ValidationError as ve:
        # This is the intended db bug path: Pydantic ValidationError for 'shipped'
        return make_traceback_response(ve)
    except Exception as e:
        return make_traceback_response(e)

@app.get("/api/orders/{order_id}")
def get_order(order_id: int):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM orders WHERE id=?", (order_id,))
        r = cur.fetchone()
        conn.close()
        if not r:
            raise HTTPException(status_code=404, detail="Order not found")

        # If db bug flag is off and this is the shipped order, we could normalize or hide.
        # But spec says GET /api/orders/{id} should also trigger the enum serialization bug.
        # So when flag is on, we let it fail; when off, we map shipped -> pending to avoid crash.
        # However simpler: when flag off, return 404 or normalized? Let's normalize to avoid confusion.
        # Let's implement: if flag is off and status == 'shipped', map to pending for response compatibility.
        status_val = r["status"]
        if not bug_flags.get("db") and status_val == "shipped":
            # hide bug: map to pending so validation passes when flag off
            status_val = "pending"

        order_dict = {
            "order_id": r["id"],
            "customer": {"name": r["customer_name"], "email": r["customer_email"]},
            "items": json.loads(r["items_json"]),
            "total_inr": r["total_inr"],
            "delivery_fee_inr": r["delivery_fee_inr"],
            "grand_total_inr": r["grand_total_inr"],
            "status": status_val,
            "delivery_city": r["delivery_city"],
            "delivery_pincode": r["delivery_pincode"],
            "delivery_lat": r["delivery_lat"],
            "delivery_lng": r["delivery_lng"],
            "eta": r["eta"],
            "created_at": r["created_at"],
        }
        validated = OrderOut(**order_dict)  # may raise ValidationError when flag on and status == shipped
        return validated.model_dump()
    except HTTPException:
        raise
    except ValidationError as ve:
        return make_traceback_response(ve)
    except Exception as e:
        return make_traceback_response(e)

@app.get("/api/health")
def health():
    checks = {}
    # db check
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        conn.close()
        checks["db"] = "up"
        # but if db flag is on, we consider db check degraded? The flag simulates data bug, not connection
        if bug_flags.get("db"):
            # indicate that data validation is failing, but connection is up
            # For health we can mark as degraded to signal issue
            checks["db"] = "degraded (invalid status enum present)"
    except Exception:
        checks["db"] = "down"

    checks["payment"] = "down" if bug_flags.get("payment") else "up"
    checks["delivery"] = "down" if bug_flags.get("delivery") else "up"
    checks["notifier"] = "down" if bug_flags.get("notifier", False) else "up"
    # config bug affects payment as well
    if bug_flags.get("config"):
        checks["payment"] = "down (config error)"
    if bug_flags.get("code"):
        checks["payment"] = "down (code null-guard bug active)"

    overall = "ok" if all(v == "up" for v in checks.values()) else "degraded"
    return {"status": overall, "checks": checks, "flags": bug_flags}

@app.post("/api/debug/bug")
def toggle_bug(scenario: str = Query(..., description="payment|config|db|code|delivery"), on: bool = Query(True)):
    """
    Toggle bug flags. Each sets a flag that makes a REAL failure occur elsewhere.
    """
    allowed = {"payment", "config", "db", "code", "delivery", "notifier"}
    if scenario not in allowed:
        raise HTTPException(status_code=400, detail=f"Unknown scenario {scenario!r}. Allowed: {sorted(allowed)}")
    # normalize bool - FastAPI already parses ?on=true/false, but also handle string
    bug_flags[scenario] = bool(on)
    print(f"[debug] bug_flags[{scenario!r}] = {on} -> {bug_flags}")
    return {"scenario": scenario, "on": bug_flags[scenario], "flags": bug_flags}

@app.get("/api/debug/flags")
def get_flags():
    return bug_flags

# ---------------------------------------------------------------------------
# Static frontend serving (must be after API routes)
# ---------------------------------------------------------------------------
from pathlib import Path
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

# Mount static assets if they exist; also serve index.html at root
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
def serve_frontend():
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return JSONResponse({"detail": "Frontend not built yet. API is at /api/products"})

@app.get("/{path:path}")
def serve_spa_fallback(path: str):
    # Let API routes 404 normally; this fallback is for SPA refresh
    if path.startswith("api/") or path.startswith("static/"):
        raise HTTPException(status_code=404, detail="Not found")
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    raise HTTPException(status_code=404, detail="Not found")
