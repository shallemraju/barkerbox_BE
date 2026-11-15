"""
BurgerBox - Database Engine & Dual PostgreSQL / SQLite Support
Handles database connection, schema creation, and seeding.
"""
import os
import sqlite3
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env.local")
load_dotenv(Path(__file__).resolve().parent / ".env")
load_dotenv(PROJECT_ROOT / ".env")
DATABASE_URL = os.getenv("DATABASE_URL")

DB_SQLITE_FILE = str(Path(__file__).resolve().parent / "bakersbox.db")


class _PostgresCursor:
    def __init__(self, cursor: Any):
        self._cursor = cursor

    def execute(self, query: str, params: Optional[Any] = None) -> "_PostgresCursor":
        query = query.replace("datetime('now')", "CURRENT_TIMESTAMP::text")
        query = query.replace("?", "%s")
        if params is None:
            self._cursor.execute(query)
        else:
            self._cursor.execute(query, params)
        return self

    def fetchone(self) -> Any:
        return self._cursor.fetchone()

    def fetchall(self) -> Any:
        return self._cursor.fetchall()


class _PostgresConnection:
    def __init__(self, connection: Any):
        self._connection = connection

    def cursor(self) -> _PostgresCursor:
        return _PostgresCursor(self._connection.cursor())

    def commit(self) -> None:
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()


_USE_SQLITE = False

def get_db():
    global _USE_SQLITE, DATABASE_URL
    if DATABASE_URL and not _USE_SQLITE:
        if not DATABASE_URL.startswith(("postgres://", "postgresql://")):
            raise ValueError("DATABASE_URL must be a PostgreSQL connection URL")
        clean_url = DATABASE_URL.replace("&channel_binding=require", "").replace("channel_binding=require&", "").replace("channel_binding=require", "")
        try:
            import psycopg
            from psycopg.rows import dict_row

            connection = psycopg.connect(
                clean_url,
                connect_timeout=3,
                row_factory=dict_row,
            )
            return _PostgresConnection(connection)
        except Exception as e:
            _USE_SQLITE = True
            print(f"[DB Notice] Cloud PostgreSQL unavailable in current network context ({e}). Seamlessly using local storage.")

    conn = sqlite3.connect(DB_SQLITE_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # 1. Users Table (Customer registration requires Name, Email, Phone)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        phone TEXT UNIQUE NOT NULL,
        password TEXT, -- Used for Admin accounts
        address TEXT,
        role TEXT NOT NULL DEFAULT 'customer', -- 'customer', 'admin'
        created_at TEXT NOT NULL
    )
    """)
    
    # 2. OTP Verification Table for Customer Login
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS otps (
        phone TEXT PRIMARY KEY,
        otp TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)
    
    # 3. Active Sessions / Tokens Table for Role-Based Enforcement
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        role TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)

    # 4. Menu Items Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS menu_items (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        subcategory TEXT,
        description TEXT,
        image_url TEXT,
        variants TEXT NOT NULL,
        base_price REAL NOT NULL,
        tags TEXT,
        is_popular BOOLEAN DEFAULT 0,
        is_seasonal BOOLEAN DEFAULT 0,
        is_available BOOLEAN DEFAULT 1,
        rating REAL DEFAULT 4.9,
        allergens TEXT
    )
    """)
    
    # 5. Orders Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id TEXT PRIMARY KEY,
        tracking_code TEXT UNIQUE NOT NULL,
        customer_id TEXT,
        customer_name TEXT NOT NULL,
        customer_email TEXT NOT NULL,
        customer_phone TEXT NOT NULL,
        delivery_address TEXT NOT NULL,
        delivery_notes TEXT,
        items TEXT NOT NULL,
        subtotal REAL NOT NULL,
        delivery_fee REAL DEFAULT 50.0,
        discount REAL DEFAULT 0.0,
        total REAL NOT NULL,
        status TEXT NOT NULL DEFAULT 'confirmed', -- 'confirmed', 'preparing', 'assigned', 'out_for_delivery', 'delivered'
        payment_method TEXT NOT NULL,
        delivery_boy_id TEXT,
        delivery_boy_name TEXT,
        delivery_boy_phone TEXT,
        estimated_delivery_time TEXT DEFAULT '30-40 mins',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)
    
    # 6. Delivery Fleet Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS delivery_staff (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        phone TEXT NOT NULL,
        vehicle TEXT NOT NULL,
        status TEXT DEFAULT 'available',
        active_orders INTEGER DEFAULT 0
    )
    """)
    
    # 7. Bookings Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bookings (
        id TEXT PRIMARY KEY,
        booking_code TEXT UNIQUE NOT NULL,
        customer_name TEXT NOT NULL,
        customer_email TEXT NOT NULL,
        customer_phone TEXT NOT NULL,
        booking_date TEXT NOT NULL,
        booking_time TEXT NOT NULL,
        guests INTEGER NOT NULL,
        occasion TEXT NOT NULL,
        special_requests TEXT,
        table_number TEXT,
        status TEXT DEFAULT 'confirmed',
        created_at TEXT NOT NULL
    )
    """)

    # 8. Contact Inquiries & Bulk Gifting Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS contact_inquiries (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        phone TEXT NOT NULL,
        inquiry_type TEXT NOT NULL,
        message TEXT NOT NULL,
        status TEXT DEFAULT 'new',
        created_at TEXT NOT NULL
    )
    """)

    # 9. Performance Indexes for Rapid Data Retrieval
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_customer_email ON orders(customer_email)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_tracking_code ON orders(tracking_code)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_menu_category ON menu_items(category)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_contact_email ON contact_inquiries(email)")
    
    conn.commit()
    conn.close()

    # Guarantee owner, admin, and staff accounts are seeded in active database
    ensure_default_accounts()


def ensure_default_accounts():
    """
    Guarantees that the Owner account, Admin account, and Delivery staff exist
    in whichever database is currently active (Neon Cloud PostgreSQL or local SQLite).
    """
    try:
        conn = get_db()
        cursor = conn.cursor()

        # 1. Ensure Owner Account
        cursor.execute("SELECT id FROM users WHERE email = ?", ("owner@bakersbox.com",))
        owner_exists = cursor.fetchone()
        if not owner_exists:
            cursor.execute("""
                INSERT INTO users (id, name, email, phone, password, role, created_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            """, (
                "usr-owner-root",
                "The Baker's Box Owner",
                "owner@bakersbox.com",
                "9820000001",
                "Owner@BakersBox2026",
                "owner"
            ))
        else:
            cursor.execute("""
                UPDATE users SET password = ?, role = ? WHERE email = ?
            """, ("Owner@BakersBox2026", "owner", "owner@bakersbox.com"))

        # 2. Ensure Admin Account
        cursor.execute("SELECT id FROM users WHERE email = ?", ("admin@burgerbox.com",))
        admin_exists = cursor.fetchone()
        if not admin_exists:
            cursor.execute("""
                INSERT INTO users (id, name, email, phone, password, role, created_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            """, (
                "usr-admin-root",
                "System Administrator",
                "admin@burgerbox.com",
                "9820000000",
                "admin",
                "admin"
            ))
        else:
            cursor.execute("""
                UPDATE users SET password = ?, role = ? WHERE email = ?
            """, ("admin", "admin", "admin@burgerbox.com"))

        # 3. Ensure Delivery Fleet Staff exists
        cursor.execute("SELECT COUNT(*) FROM delivery_staff")
        staff_row = cursor.fetchone()
        count_val = staff_row[0] if (staff_row and not isinstance(staff_row, dict)) else (staff_row.get('count', 0) if isinstance(staff_row, dict) else 0)
        if not count_val:
            fleet = [
                ("del-1", "Rajesh Kumar", "+91 98765 43210", "Honda Activa 6G (Insulated Box)", "available", 0),
                ("del-2", "Amit Verma", "+91 98112 34567", "Hero Electric Optima (Thermal Bag)", "available", 0),
                ("del-3", "Suresh Patil", "+91 98200 89123", "TVS Jupiter (Chilled Caddy)", "available", 0)
            ]
            for s in fleet:
                cursor.execute("""
                    INSERT INTO delivery_staff (id, name, phone, vehicle, status, active_orders)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, s)

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Auth Setup Warning] ensure_default_accounts exception: {e}")


def should_seed_demo_data() -> bool:
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM menu_items")
        row = cursor.fetchone()
        conn.close()
        if not row:
            return True
        val = row[0] if not isinstance(row, dict) else list(row.values())[0]
        return val == 0
    except Exception:
        return True


if __name__ == "__main__":
    init_db()
    print("Database schema successfully initialized.")
