import sqlite3
import os
import json
from pathlib import Path

DB_PATH = os.getenv("DATABASE_PATH", "hack_store.db")
# allow override via env for sandbox copy; default file in project root

def get_conn():
    conn = sqlite3.connect(DB_PATHS, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    # products
    cur.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        description TEXT NOT NULL,
        image TEXT NOT NULL,
        mrp_inr INTEGER NOT NULL,
        price_inr INTEGER NOT NULL,
        stock INTEGER NOT NULL
    )
    """)
    # users
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        payment_method_token TEXT
    )
    """)
    # orders
    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_name TEXT NOT NULL,
        customer_email TEXT NOT NULL,
        user_id INTEGER,
        items_json TEXT NOT NULL,
        total_inr INTEGER NOT NULL,
        delivery_fee_inr INTEGER NOT NULL,
        grand_total_inr INTEGER NOT NULL,
        status TEXT NOT NULL,
        delivery_city TEXT,
        delivery_pincode TEXT,
        delivery_lat REAL,
        delivery_lng REAL,
        eta TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)
    conn.commit()
    conn.close()
    seed_db()

def seed_db():
    conn = get_conn()
    cur = conn.cursor()
    # check if products already seeded
    cur.execute("SELECT COUNT(*) as c FROM products")
    cnt = cur.fetchone()["c"]
    if cnt > 0:
        conn.close()
        return

    products = [
        (1, "Wireless Mouse", "Accessories", "Ergonomic 2.4GHz wireless mouse with silent clicks, perfect for long coding sessions.", "🖱️", 999, 799, 50),
        (2, "Mechanical Keyboard", "Accessories", "Compact 87-key mechanical keyboard with blue switches and RGB backlight.", "⌨️", 3499, 2799, 30),
        (3, "Hackathon Notebook", "Stationery", "A5 dotted notebook with 200 pages, ideal for system design sketches.", "📓", 199, 149, 100),
        (4, "Gel Pens (Pack of 10)", "Stationery", "Smooth 0.5mm gel pens, assorted colors for notes and diagrams.", "🖊️", 120, 99, 200),
        (5, "Wireless Earphones", "Audio", "True wireless earphones with 24h battery and deep bass.", "🎧", 2999, 2299, 40),
        (6, "Over-ear Headphones", "Audio", "ANC over-ear headphones with 40h playback and hi-res audio.", "🎧", 5499, 4199, 25),
        (7, "Laptop Stand", "Accessories", "Aluminium foldable stand, improves posture and cooling.", "💻", 1499, 1199, 60),
        (8, "USB-C Hub 6-in-1", "Accessories", "6-in-1 hub with HDMI, USB 3.0, SD card and PD charging.", "🔌", 1999, 1599, 45),
        (9, "Power Bank 20000mAh", "Power", "Fast-charging power bank with dual output and LED display.", "🔋", 2499, 1899, 35),
    ]
    cur.executemany("INSERT INTO products (id, name, category, description, image, mrp_inr, price_inr, stock) VALUES (?,?,?,?,?,?,?,?)", products)

    users = [
        (1, "Aarav Sharma", "aarav@example.com", "tok_aarav_razorpay_123"),
        (2, "Priya Verma", "priya@example.com", "tok_priya_razorpay_456"),
        (3, "Rohan Mehta", "rohan@example.com", None), # no saved payment method -> triggers code bug
    ]
    cur.executemany("INSERT INTO users (id, name, email, payment_method_token) VALUES (?,?,?,?)", users)

    import datetime
    now = datetime.datetime.utcnow().isoformat()

    # seed a few orders
    # order 1: normal paid
    items1 = json.dumps([{"product_id": 1, "qty": 1, "name": "Wireless Mouse", "price_inr": 799}, {"product_id": 5, "qty": 1, "name": "Wireless Earphones", "price_inr": 2299}])
    cur.execute("""
        INSERT INTO orders (customer_name, customer_email, user_id, items_json, total_inr, delivery_fee_inr, grand_total_inr, status, delivery_city, delivery_pincode, delivery_lat, delivery_lng, eta, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, ("Aarav Sharma", "aarav@example.com", 1, items1, 3098, 49, 3147, "paid", "Mumbai", "400001", 19.0760, 72.8777, "2-3 days", now))

    items2 = json.dumps([{"product_id": 2, "qty": 1, "name": "Mechanical Keyboard", "price_inr": 2799}])
    cur.execute("""
        INSERT INTO orders (customer_name, customer_email, user_id, items_json, total_inr, delivery_fee_inr, grand_total_inr, status, delivery_city, delivery_pincode, delivery_lat, delivery_lng, eta, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, ("Priya Verma", "priya@example.com", 2, items2, 2799, 49, 2848, "delivered", "Bengaluru", "560001", 12.9716, 77.5946, "1-2 days", now))

    # bug order: status "shipped" is out of allowed Enum (pending/paid/delivered) -> triggers db bug when flag on
    items3 = json.dumps([{"product_id": 3, "qty": 2, "name": "Hackathon Notebook", "price_inr": 149}])
    cur.execute("""
        INSERT INTO orders (customer_name, customer_email, user_id, items_json, total_inr, delivery_fee_inr, grand_total_inr, status, delivery_city, delivery_pincode, delivery_lat, delivery_lng, eta, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, ("Test User", "test@example.com", None, items3, 298, 79, 377, "shipped", "Delhi", "110001", 28.6139, 77.2090, "3-4 days", now))

    conn.commit()
    conn.close()
    print("[db] seeded products, users, orders")
