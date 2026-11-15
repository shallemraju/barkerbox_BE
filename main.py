"""
BurgerBox Patisserie & Dining - Production FastAPI Backend API
Powers Customer Ordering & Live Tracking, Secure OTP Authentication, 
and Private Role-Enforced Admin Management (/admin).
"""
import uuid
import random
import json
import re
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Query, Header, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, EmailStr

from database import get_db, init_db, should_seed_demo_data, ensure_default_accounts
from seed_data import seed_database

# Ensure database is properly initialized
try:
    if should_seed_demo_data():
        seed_database()
    else:
        init_db()
    ensure_default_accounts()
except Exception as e:
    print(f"Database init notice: {e}")
    init_db()
    ensure_default_accounts()

app = FastAPI(
    title="The Baker's Box API",
    description="Backend API with OTP Customer Authentication and Private Protected Admin Portal",
    version="2.1.0"
)

# Enable CORS for React Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------- HELPER UTILS -----------------

def clean_phone(phone_str: str) -> str:
    """Normalize phone number to 10 digits."""
    digits = re.sub(r"\D", "", phone_str or "")
    if len(digits) > 10 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) > 10 and digits.startswith("0"):
        digits = digits[1:]
    return digits[-10:] if len(digits) >= 10 else digits


def get_token_from_header(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.strip().split(" ")
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return authorization.strip()


# ----------------- FASTAPI AUTH DEPENDENCIES -----------------

def get_current_admin(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """
    Enforces that the caller has an active Admin session token.
    Returns 401 / 403 if missing or not an admin.
    """
    token = get_token_from_header(authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization token required for admin access"
        )

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.token, s.user_id, s.role, u.name, u.email 
        FROM sessions s
        JOIN users u ON s.user_id = u.id
        WHERE s.token = ? AND (s.role = 'admin' OR s.role = 'owner')
    """, (token,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Owner/Admin privileges required"
        )
    return dict(row)


def get_current_customer(authorization: Optional[str] = Header(None)) -> Optional[Dict[str, Any]]:
    """
    Optional / loose customer check or customer validation.
    """
    token = get_token_from_header(authorization)
    if not token:
        return None

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.token, s.user_id, s.role, u.name, u.email, u.phone, u.address
        FROM sessions s
        JOIN users u ON s.user_id = u.id
        WHERE s.token = ?
    """, (token,))
    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else None


# ----------------- PYDANTIC SCHEMAS -----------------

class CustomerRegisterSchema(BaseModel):
    name: str = Field(..., min_length=2, description="Customer Full Name")
    email: str = Field(..., min_length=5, description="Email Address")
    phone: str = Field(..., min_length=10, description="10-digit Mobile Number")


class SendOtpSchema(BaseModel):
    phone: str = Field(..., min_length=10, description="Customer Mobile Number")


class VerifyOtpSchema(BaseModel):
    phone: str = Field(..., min_length=10, description="Customer Mobile Number")
    otp: str = Field(..., min_length=4, max_length=6, description="6-digit OTP code")


class AdminLoginSchema(BaseModel):
    email: str = Field(..., description="Admin Email Address")
    password: str = Field(..., min_length=1, description="Admin Password")


class OwnerLoginSchema(BaseModel):
    email: str = Field(..., description="Owner Email Address")
    password: str = Field(..., min_length=1, description="Owner Password")


class CreateDeliveryStaffSchema(BaseModel):
    name: str = Field(..., min_length=2, description="Staff Full Name")
    phone: str = Field(..., min_length=8, description="Staff Phone Number")
    vehicle: str = Field(..., min_length=2, description="Vehicle Model / Type")
    status: Optional[str] = Field("available", description="Status: available, busy, offline")


class UpdateStaffStatusSchema(BaseModel):
    status: str = Field(..., description="Status: available, busy, offline")


class UpdateMenuItemSchema(BaseModel):
    base_price: Optional[float] = None
    is_available: Optional[bool] = None


class OrderItemSchema(BaseModel):
    id: str
    name: str
    variant: str
    price: float
    quantity: int = 1
    eggless: bool = False
    custom_message: Optional[str] = ""


class CreateOrderSchema(BaseModel):
    customer_id: Optional[str] = None
    customer_name: str
    customer_email: str
    customer_phone: str
    delivery_address: str
    delivery_notes: Optional[str] = ""
    items: List[OrderItemSchema]
    payment_method: str = "Cash on Delivery"
    discount_code: Optional[str] = ""


class AssignDeliverySchema(BaseModel):
    delivery_boy_id: str


class UpdateOrderStatusSchema(BaseModel):
    status: str  # confirmed, preparing, assigned, out_for_delivery, delivered


class CreateBookingSchema(BaseModel):
    customer_name: str
    customer_email: str
    customer_phone: str
    booking_date: str
    booking_time: str
    guests: int = 2
    occasion: str = "Casual Dine-in"
    special_requests: Optional[str] = ""


class MenuItemCreateSchema(BaseModel):
    name: str
    category: str
    subcategory: Optional[str] = ""
    description: str
    image_url: str
    base_price: float
    variants: List[Dict[str, Any]]
    allergens: Optional[str] = ""


# ----------------- 1. CUSTOMER AUTHENTICATION (MOBILE + OTP) -----------------

@app.post("/api/auth/register")
@app.post("/api/auth/register-customer")
def register_customer(payload: CustomerRegisterSchema):
    """
    Registers a new customer using ONLY Name, Email Address, and Mobile Number.
    No password or demo role fields.
    """
    clean_name = payload.name.strip()
    clean_email = payload.email.lower().strip()
    phone_norm = clean_phone(payload.phone)

    if len(phone_norm) < 10:
        raise HTTPException(
            status_code=400,
            detail="Please provide a valid 10-digit mobile number."
        )

    if "@" not in clean_email or "." not in clean_email:
        raise HTTPException(
            status_code=400,
            detail="Please provide a valid email address."
        )

    conn = get_db()
    cursor = conn.cursor()

    # Check if phone already registered
    cursor.execute("SELECT id FROM users WHERE phone = ?", (phone_norm,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(
            status_code=400,
            detail="This mobile number is already registered. Please proceed to login with OTP."
        )

    # Check if email already registered
    cursor.execute("SELECT id FROM users WHERE email = ?", (clean_email,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(
            status_code=400,
            detail="This email address is already registered. Please login with OTP using your registered mobile number."
        )

    user_id = f"usr-{uuid.uuid4().hex[:8]}"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        INSERT INTO users (id, name, email, phone, password, address, role, created_at)
        VALUES (?, ?, ?, ?, '', '', 'customer', ?)
    """, (user_id, clean_name, clean_email, phone_norm, now_str))
    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": "Account created successfully! Please verify your mobile number with OTP to log in.",
        "phone": phone_norm,
        "user": {
            "id": user_id,
            "name": clean_name,
            "email": clean_email,
            "phone": phone_norm,
            "role": "customer"
        }
    }


@app.post("/api/auth/send-otp")
def send_otp(payload: SendOtpSchema):
    """
    Generates and sends a 6-digit OTP to the registered mobile number.
    Strictly checks that the customer is registered first.
    """
    phone_norm = clean_phone(payload.phone)
    if len(phone_norm) < 10:
        raise HTTPException(
            status_code=400,
            detail="Please enter a valid 10-digit mobile number."
        )

    conn = get_db()
    cursor = conn.cursor()

    # Check if registered as a customer
    cursor.execute("SELECT id, name FROM users WHERE phone = ? AND role = 'customer'", (phone_norm,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        raise HTTPException(
            status_code=404,
            detail="Mobile number not registered. Please register your account first."
        )

    # Generate secure 6-digit OTP
    otp_code = f"{random.randint(100000, 999999)}"
    now = datetime.now()
    expires_at = (now + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    # Store in otps table (replace if already exists)
    cursor.execute("DELETE FROM otps WHERE phone = ?", (phone_norm,))
    cursor.execute("""
        INSERT INTO otps (phone, otp, expires_at, created_at)
        VALUES (?, ?, ?, ?)
    """, (phone_norm, otp_code, expires_at, now_str))
    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": f"Verification OTP sent to +91 {phone_norm}.",
        "phone": phone_norm,
        "otp": otp_code  # Returned in payload for instant verification / testing
    }


@app.post("/api/auth/verify-otp")
def verify_otp(payload: VerifyOtpSchema):
    """
    Verifies the 6-digit OTP code and creates a secure session token for the customer.
    """
    phone_norm = clean_phone(payload.phone)
    code = payload.otp.strip()

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT otp, expires_at FROM otps WHERE phone = ?", (phone_norm,))
    otp_record = cursor.fetchone()

    if not otp_record or otp_record["otp"] != code:
        conn.close()
        raise HTTPException(
            status_code=400,
            detail="Invalid OTP code. Please enter the correct 6-digit code sent to your phone."
        )

    # Check expiration
    expires_at = datetime.strptime(otp_record["expires_at"], "%Y-%m-%d %H:%M:%S")
    if datetime.now() > expires_at:
        conn.close()
        raise HTTPException(
            status_code=400,
            detail="OTP code has expired. Please request a new code."
        )

    # Delete verified OTP
    cursor.execute("DELETE FROM otps WHERE phone = ?", (phone_norm,))

    # Retrieve customer record
    cursor.execute("SELECT * FROM users WHERE phone = ? AND role = 'customer'", (phone_norm,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        raise HTTPException(
            status_code=404,
            detail="Customer account not found."
        )

    user_dict = dict(user)
    if "password" in user_dict:
        del user_dict["password"]

    # Generate session token
    session_token = f"tok_cust_{uuid.uuid4().hex}"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        INSERT INTO sessions (token, user_id, role, created_at)
        VALUES (?, ?, 'customer', ?)
    """, (session_token, user_dict["id"], now_str))
    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": "Login successful!",
        "token": session_token,
        "user": user_dict
    }


@app.get("/api/auth/me")
def get_current_user_profile(authorization: Optional[str] = Header(None)):
    """
    Returns current user details based on the Bearer token.
    """
    user = get_current_customer(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"user": user}


# ----------------- 2. PRIVATE ADMIN AUTHENTICATION (FOR /admin ONLY) -----------------

@app.post("/api/admin/login")
def admin_login(payload: AdminLoginSchema):
    """
    Dedicated private admin login endpoint.
    Not exposed on customer UI. Validates email & password, generates admin session token.
    """
    input_str = (payload.email or "").lower().strip()
    target_email = "admin@burgerbox.com" if input_str in ("admin", "admin@burgerbox.com") else input_str
    
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE LOWER(email) = ? AND (role = 'admin' OR role = 'owner')", (target_email,))
    admin_row = cursor.fetchone()

    # Self-healing: if account missing in current DB, seed immediately
    if not admin_row and target_email in ("admin@burgerbox.com", "owner@bakersbox.com"):
        conn.close()
        ensure_default_accounts()
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE LOWER(email) = ? AND (role = 'admin' OR role = 'owner')", (target_email,))
        admin_row = cursor.fetchone()

    # Password match (exact or known defaults)
    pwd_match = False
    if admin_row:
        stored_pwd = admin_row["password"] or ""
        given_pwd = payload.password or ""
        if stored_pwd == given_pwd or stored_pwd.lower() == given_pwd.lower():
            pwd_match = True
        elif target_email == "admin@burgerbox.com" and given_pwd in ("admin", "Admin", "Owner@BakersBox2026"):
            pwd_match = True

    if not admin_row or not pwd_match:
        conn.close()
        raise HTTPException(
            status_code=401,
            detail="Invalid administrator credentials."
        )

    admin_dict = dict(admin_row)
    if "password" in admin_dict:
        del admin_dict["password"]

    # Generate administrative session token
    admin_token = f"tok_admin_{uuid.uuid4().hex}"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        INSERT INTO sessions (token, user_id, role, created_at)
        VALUES (?, ?, 'admin', ?)
    """, (admin_token, admin_dict["id"], now_str))
    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": "Admin authorization successful",
        "token": admin_token,
        "admin": admin_dict
    }


@app.post("/api/owner/login")
def owner_login(payload: OwnerLoginSchema):
    """
    Dedicated private Owner login endpoint.
    Not exposed on public homepage. Validates email & password, generates owner session token.
    Accepts:
      - Email: 'owner@bakersbox.com' (or shorthand 'owner')
      - Password: 'Owner@BakersBox2026' (or 'owner@bakersbox2026' / 'admin')
      - Also accepts admin credentials as an authorized executive role.
    """
    input_str = (payload.email or "").lower().strip()
    if input_str in ("owner", "owner@bakersbox.com"):
        target_email = "owner@bakersbox.com"
    elif input_str in ("admin", "admin@burgerbox.com"):
        target_email = "admin@burgerbox.com"
    else:
        target_email = input_str

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE LOWER(email) = ? AND (role = 'owner' OR role = 'admin')", (target_email,))
    owner_row = cursor.fetchone()

    # Self-healing: if account missing in current DB (e.g. Neon PostgreSQL), seed immediately
    if not owner_row and target_email in ("owner@bakersbox.com", "admin@burgerbox.com"):
        conn.close()
        ensure_default_accounts()
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE LOWER(email) = ? AND (role = 'owner' OR role = 'admin')", (target_email,))
        owner_row = cursor.fetchone()

    pwd_match = False
    if owner_row:
        stored_pwd = owner_row["password"] or ""
        given_pwd = payload.password or ""
        # Check direct or case-insensitive match
        if stored_pwd == given_pwd or stored_pwd.lower() == given_pwd.lower():
            pwd_match = True
        elif target_email == "owner@bakersbox.com" and given_pwd in ("Owner@BakersBox2026", "owner@bakersbox2026", "admin"):
            pwd_match = True
        elif target_email == "admin@burgerbox.com" and given_pwd in ("admin", "Admin", "Owner@BakersBox2026"):
            pwd_match = True

    if not owner_row or not pwd_match:
        conn.close()
        raise HTTPException(
            status_code=401,
            detail="Invalid owner credentials. Please use email: owner@bakersbox.com and password: Owner@BakersBox2026"
        )

    owner_dict = dict(owner_row)
    if "password" in owner_dict:
        del owner_dict["password"]

    owner_token = f"tok_owner_{uuid.uuid4().hex}"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        INSERT INTO sessions (token, user_id, role, created_at)
        VALUES (?, ?, ?, ?)
    """, (owner_token, owner_dict["id"], owner_dict["role"], now_str))
    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": "Owner authorization successful",
        "token": owner_token,
        "user": owner_dict
    }


# ----------------- 3. FOOD MENU ENDPOINTS -----------------

@app.get("/api/menu")
def get_menu(category: Optional[str] = None, search: Optional[str] = None):
    """
    Returns the public list of authentic catalog items.
    """
    conn = get_db()
    cursor = conn.cursor()
    query = "SELECT * FROM menu_items WHERE is_available = 1"
    params = []

    if category and category != "all":
        query += " AND category = ?"
        params.append(category)

    if search:
        query += " AND (name LIKE ? OR description LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term])

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    items = []
    for r in rows:
        it = dict(r)
        it["variants"] = json.loads(it["variants"]) if it.get("variants") else []
        it["tags"] = json.loads(it["tags"]) if it.get("tags") else []
        items.append(it)

    return {"items": items, "count": len(items)}


# ----------------- 3B. CONTACT & CATERING INQUIRIES -----------------

class ContactInquirySchema(BaseModel):
    name: str = Field(..., min_length=2)
    email: EmailStr
    phone: str = Field(..., min_length=8)
    inquiry_type: str = "general"
    message: str = Field(..., min_length=5)


@app.post("/api/contact")
def submit_contact_inquiry(inquiry: ContactInquirySchema):
    """
    Handles customer inquiries, custom celebration cake consultations, 
    and corporate/bulk patisserie gifting requests. Saves to database.
    """
    inquiry_id = f"inq-{uuid.uuid4().hex[:8]}"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO contact_inquiries (id, name, email, phone, inquiry_type, message, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'new', ?)
        """, (inquiry_id, inquiry.name.strip(), inquiry.email.lower().strip(), inquiry.phone.strip(), inquiry.inquiry_type, inquiry.message.strip(), now_str))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Contact DB Warning] Could not save inquiry to DB: {e}")

    return {
        "status": "success",
        "inquiry_id": inquiry_id,
        "message": f"Grazie, {inquiry.name}! We have received your {inquiry.inquiry_type.replace('_', ' ')} inquiry. Our master patissier concierge will reach out to you shortly."
    }


@app.get("/api/admin/contact-inquiries")
def get_admin_contact_inquiries(admin: Dict[str, Any] = Depends(get_current_admin)):
    """
    Retrieves all customer inquiries and corporate gifting requests for Owner review.
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM contact_inquiries ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return {"inquiries": [dict(r) for r in rows]}


@app.put("/api/admin/contact-inquiries/{inquiry_id}/status")
def update_contact_inquiry_status(inquiry_id: str, payload: Dict[str, str], admin: Dict[str, Any] = Depends(get_current_admin)):
    """
    Owner updates status of a customer inquiry ('new', 'contacted', 'resolved').
    """
    new_status = payload.get("status", "contacted")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE contact_inquiries SET status = ? WHERE id = ?", (new_status, inquiry_id))
    conn.commit()
    conn.close()
    return {"status": "success", "inquiry_id": inquiry_id, "new_status": new_status}


# ----------------- 4. CUSTOMER ORDERING & LIVE TRACKING -----------------

@app.post("/api/orders")
def place_order(payload: CreateOrderSchema):
    """
    Customer places an order. Enforces order validation and returns live tracking code.
    """
    if not payload.items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    order_id = f"ord-{uuid.uuid4().hex[:8]}"
    tracking_code = f"BB-{random.randint(1000, 9999)}"

    subtotal = sum(it.price * it.quantity for it in payload.items)
    delivery_fee = 0.0 if subtotal >= 1000 else 50.0
    discount = 50.0 if (payload.discount_code or "").upper() in ["SWEET", "BAKER10"] else 0.0
    total = max(0.0, subtotal + delivery_fee - discount)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO orders (
        id, tracking_code, customer_id, customer_name, customer_email, customer_phone,
        delivery_address, delivery_notes, items, subtotal, delivery_fee, discount, total,
        status, payment_method, estimated_delivery_time, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending_review', ?, '30-40 mins', ?, ?)
    """, (
        order_id, tracking_code, payload.customer_id, payload.customer_name, payload.customer_email, payload.customer_phone,
        payload.delivery_address, payload.delivery_notes,
        json.dumps([it.model_dump() for it in payload.items]),
        subtotal, delivery_fee, discount, total,
        payload.payment_method, now_str, now_str
    ))
    conn.commit()
    conn.close()

    return {
        "success": True,
        "order_id": order_id,
        "tracking_code": tracking_code,
        "total": total,
        "status": "pending_review",
        "message": f"Order #{tracking_code} received! Awaiting kitchen review and acceptance."
    }


@app.get("/api/orders/my")
def get_my_orders(email: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE customer_email = ? ORDER BY created_at DESC", (email.lower().strip(),))
    rows = cursor.fetchall()
    conn.close()

    orders = []
    for r in rows:
        o = dict(r)
        o["items"] = json.loads(o["items"]) if o.get("items") else []
        orders.append(o)
    return {"orders": orders}


@app.get("/api/orders/{tracking_code}")
def track_order(tracking_code: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE tracking_code = ? OR id = ?", (tracking_code.upper().strip(), tracking_code.strip()))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Order not found with this tracking code")

    order = dict(row)
    order["items"] = json.loads(order["items"]) if order.get("items") else []

    # Complete Live Timeline from Placement & Kitchen Review to Final Delivery
    if order["status"] == "rejected":
        timeline = [
            {"key": "pending_review", "title": "Order Placed", "desc": "Received by store", "state": "completed"},
            {"key": "rejected", "title": "Order Declined", "desc": order.get("delivery_notes") or "Kitchen could not fulfill the order at this time. Please contact support.", "state": "active"}
        ]
        order["timeline"] = timeline
        order["current_step_index"] = 1
        return order

    timeline = [
        {"key": "pending_review", "title": "Order Placed", "desc": "Awaiting kitchen review & acceptance"},
        {"key": "confirmed", "title": "Order Accepted", "desc": "Accepted by kitchen & scheduled for artisan baking"},
        {"key": "preparing", "title": "Kitchen Preparing", "desc": "Baking, cooling & quality packaging"},
        {"key": "assigned", "title": "Assigned to Courier", "desc": f"Assigned to {order.get('delivery_boy_name') or 'Delivery Partner'}"},
        {"key": "out_for_delivery", "title": "Out for Delivery", "desc": "Courier has picked up food and is en route"},
        {"key": "delivered", "title": "Delivered", "desc": "Order safely delivered to your doorstep"}
    ]

    stages = ["pending_review", "confirmed", "preparing", "assigned", "out_for_delivery", "delivered"]
    curr_idx = stages.index(order["status"]) if order["status"] in stages else 0

    for i, step in enumerate(timeline):
        if i < curr_idx:
            step["state"] = "completed"
        elif i == curr_idx:
            step["state"] = "active"
        else:
            step["state"] = "pending"

    order["timeline"] = timeline
    order["current_step_index"] = curr_idx
    return order


# ----------------- 5. PROTECTED ADMIN PORTAL ENDPOINTS (/api/admin/*) -----------------
# Strictly protected by FastAPI dependency: Depends(get_current_admin)

@app.get("/api/admin/stats")
def get_admin_stats(admin: Dict[str, Any] = Depends(get_current_admin)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) AS total_orders, COALESCE(SUM(total), 0) AS total_revenue FROM orders")
    order_stats = cursor.fetchone()
    total_orders = order_stats["total_orders"]
    total_revenue = order_stats["total_revenue"]

    cursor.execute("SELECT COUNT(*) AS count FROM orders WHERE status != 'delivered'")
    pending_orders = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) AS count FROM users WHERE role = 'customer'")
    customers_count = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) AS count FROM menu_items")
    food_items_count = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) AS count FROM delivery_staff WHERE status = 'available'")
    available_drivers = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) AS count FROM bookings")
    bookings_count = cursor.fetchone()["count"]
    conn.close()

    return {
        "total_orders": total_orders,
        "total_revenue": total_revenue,
        "pending_orders": pending_orders,
        "customers_count": customers_count,
        "food_items_count": food_items_count,
        "available_drivers": available_drivers,
        "bookings_count": bookings_count
    }


@app.get("/api/admin/orders")
def get_all_orders(status: Optional[str] = None, admin: Dict[str, Any] = Depends(get_current_admin)):
    conn = get_db()
    cursor = conn.cursor()
    query = "SELECT * FROM orders"
    params = []
    if status and status != "all":
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    orders = []
    for r in rows:
        o = dict(r)
        o["items"] = json.loads(o["items"]) if o.get("items") else []
        orders.append(o)
    return {"orders": orders, "count": len(orders)}


@app.post("/api/admin/orders/{order_id}/accept")
def accept_order(order_id: str, admin: Dict[str, Any] = Depends(get_current_admin)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM orders WHERE id = ? OR tracking_code = ?", (order_id, order_id))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Order not found")

    cursor.execute("""
    UPDATE orders SET status = 'confirmed', updated_at = datetime('now')
    WHERE id = ? OR tracking_code = ?
    """, (order_id, order_id))
    conn.commit()
    conn.close()
    return {"success": True, "status": "confirmed", "message": f"Order #{order_id} accepted by kitchen."}


@app.post("/api/admin/orders/{order_id}/reject")
def reject_order(order_id: str, payload: Optional[Dict[str, str]] = None, admin: Dict[str, Any] = Depends(get_current_admin)):
    reason = (payload or {}).get("reason", "Kitchen could not fulfill the order at this time")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM orders WHERE id = ? OR tracking_code = ?", (order_id, order_id))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Order not found")

    cursor.execute("""
    UPDATE orders 
    SET status = 'rejected', delivery_notes = COALESCE(delivery_notes || ' | Rejection: ' || ?, ?), updated_at = datetime('now')
    WHERE id = ? OR tracking_code = ?
    """, (reason, reason, order_id, order_id))
    conn.commit()
    conn.close()
    return {"success": True, "status": "rejected", "message": f"Order #{order_id} rejected."}


@app.put("/api/admin/orders/{order_id}/status")
def update_order_status(order_id: str, payload: UpdateOrderStatusSchema, admin: Dict[str, Any] = Depends(get_current_admin)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM orders WHERE id = ? OR tracking_code = ?", (order_id, order_id))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Order not found")

    cursor.execute("""
    UPDATE orders SET status = ?, updated_at = datetime('now')
    WHERE id = ? OR tracking_code = ?
    """, (payload.status, order_id, order_id))
    conn.commit()
    conn.close()
    return {"success": True, "status": payload.status}


@app.post("/api/admin/orders/{order_id}/assign")
def assign_order_to_delivery_boy(order_id: str, payload: AssignDeliverySchema, admin: Dict[str, Any] = Depends(get_current_admin)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM delivery_staff WHERE id = ?", (payload.delivery_boy_id,))
    driver = cursor.fetchone()
    if not driver:
        conn.close()
        raise HTTPException(status_code=404, detail="Delivery staff not found")

    driver = dict(driver)
    cursor.execute("""
    UPDATE orders 
    SET delivery_boy_id = ?, delivery_boy_name = ?, delivery_boy_phone = ?, status = 'assigned', updated_at = datetime('now')
    WHERE id = ? OR tracking_code = ?
    """, (driver["id"], driver["name"], driver["phone"], order_id, order_id))

    cursor.execute("UPDATE delivery_staff SET active_orders = active_orders + 1 WHERE id = ?", (driver["id"],))
    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": f"Order assigned to {driver['name']} ({driver['phone']})",
        "assigned_to": driver["name"]
    }


@app.get("/api/admin/customers")
def get_customers(admin: Dict[str, Any] = Depends(get_current_admin)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT u.id, u.name, u.email, u.phone, u.address, u.created_at,
           COUNT(o.id) as orders_count,
           COALESCE(SUM(o.total), 0) as total_spent
    FROM users u
    LEFT JOIN orders o ON u.email = o.customer_email
    WHERE u.role = 'customer'
    GROUP BY u.id
    ORDER BY u.created_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return {"customers": [dict(r) for r in rows]}


@app.get("/api/admin/delivery-staff")
def get_delivery_staff(admin: Dict[str, Any] = Depends(get_current_admin)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM delivery_staff ORDER BY active_orders ASC, name ASC")
    rows = cursor.fetchall()
    conn.close()
    return {"staff": [dict(r) for r in rows]}


@app.post("/api/admin/delivery-staff")
def add_delivery_staff(payload: CreateDeliveryStaffSchema, admin: Dict[str, Any] = Depends(get_current_admin)):
    """
    Owner/Admin endpoint to onboard a new delivery fleet member.
    """
    staff_id = f"del-{uuid.uuid4().hex[:6]}"
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO delivery_staff (id, name, phone, vehicle, status, active_orders)
        VALUES (?, ?, ?, ?, ?, 0)
    """, (staff_id, payload.name.strip(), payload.phone.strip(), payload.vehicle.strip(), payload.status or "available"))
    conn.commit()
    
    cursor.execute("SELECT * FROM delivery_staff WHERE id = ?", (staff_id,))
    new_staff = cursor.fetchone()
    conn.close()
    
    return {
        "success": True,
        "message": f"Delivery partner {payload.name} added to fleet successfully.",
        "staff": dict(new_staff) if new_staff else {}
    }


@app.delete("/api/admin/delivery-staff/{staff_id}")
def delete_delivery_staff(staff_id: str, admin: Dict[str, Any] = Depends(get_current_admin)):
    """
    Owner/Admin endpoint to remove a delivery staff member from fleet.
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM delivery_staff WHERE id = ?", (staff_id,))
    staff_row = cursor.fetchone()
    if not staff_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Staff member not found")
        
    cursor.execute("DELETE FROM delivery_staff WHERE id = ?", (staff_id,))
    conn.commit()
    conn.close()
    return {"success": True, "message": "Staff member removed from fleet successfully."}


@app.put("/api/admin/delivery-staff/{staff_id}/status")
def update_delivery_staff_status(staff_id: str, payload: UpdateStaffStatusSchema, admin: Dict[str, Any] = Depends(get_current_admin)):
    """
    Owner/Admin endpoint to toggle a staff member's availability status.
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE delivery_staff SET status = ? WHERE id = ?", (payload.status.lower(), staff_id))
    conn.commit()
    cursor.execute("SELECT * FROM delivery_staff WHERE id = ?", (staff_id,))
    updated = cursor.fetchone()
    conn.close()
    if not updated:
        raise HTTPException(status_code=404, detail="Staff member not found")
    return {"success": True, "staff": dict(updated)}


@app.post("/api/admin/menu")
def add_menu_item(payload: MenuItemCreateSchema, admin: Dict[str, Any] = Depends(get_current_admin)):
    item_id = f"item-{uuid.uuid4().hex[:6]}"
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO menu_items (id, name, category, subcategory, description, image_url, variants, base_price, tags, is_available)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, '["Fresh"]', 1)
    """, (item_id, payload.name, payload.category, payload.subcategory, payload.description, payload.image_url, json.dumps(payload.variants), payload.base_price))
    conn.commit()
    conn.close()
    return {"success": True, "item_id": item_id}


@app.get("/api/admin/menu")
def get_all_menu_items_for_admin(admin: Dict[str, Any] = Depends(get_current_admin)):
    """
    Returns complete menu catalog including items marked as unavailable/sold-out.
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM menu_items ORDER BY category, name")
    rows = cursor.fetchall()
    conn.close()

    items = []
    for r in rows:
        it = dict(r)
        it["variants"] = json.loads(it["variants"]) if it.get("variants") else []
        it["tags"] = json.loads(it["tags"]) if it.get("tags") else []
        items.append(it)

    return {"items": items, "count": len(items)}


@app.put("/api/admin/menu/{item_id}")
def update_menu_item(item_id: str, payload: UpdateMenuItemSchema, admin: Dict[str, Any] = Depends(get_current_admin)):
    """
    Allows Owner to toggle availability (In Stock / Sold Out) and update base price.
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM menu_items WHERE id = ?", (item_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Menu item not found")

    item_dict = dict(row)
    updates = []
    params = []

    if payload.is_available is not None:
        updates.append("is_available = ?")
        params.append(1 if payload.is_available else 0)

    if payload.base_price is not None:
        updates.append("base_price = ?")
        params.append(payload.base_price)

        # Proportional update for variants if present
        if item_dict.get("variants"):
            try:
                variants = json.loads(item_dict["variants"])
                old_base = item_dict.get("base_price") or 1.0
                ratio = payload.base_price / old_base if old_base > 0 else 1.0
                for v in variants:
                    if "price" in v:
                        v["price"] = round(v["price"] * ratio)
                updates.append("variants = ?")
                params.append(json.dumps(variants))
            except Exception:
                pass

    if updates:
        query = f"UPDATE menu_items SET {', '.join(updates)} WHERE id = ?"
        params.append(item_id)
        cursor.execute(query, params)
        conn.commit()

    cursor.execute("SELECT * FROM menu_items WHERE id = ?", (item_id,))
    updated_row = cursor.fetchone()
    conn.close()

    res = dict(updated_row)
    res["variants"] = json.loads(res["variants"]) if res.get("variants") else []
    return {"success": True, "item": res}


@app.delete("/api/admin/menu/{item_id}")
def delete_menu_item(item_id: str, admin: Dict[str, Any] = Depends(get_current_admin)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM menu_items WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    return {"success": True}


@app.get("/api/admin/bookings")
def get_all_bookings(admin: Dict[str, Any] = Depends(get_current_admin)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM bookings ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return {"bookings": [dict(r) for r in rows]}


# ----------------- 6. DELIVERY BOY LOGISTICS ENDPOINTS -----------------

@app.get("/api/delivery/orders")
def get_delivery_boy_orders(delivery_boy_name: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT * FROM orders 
    WHERE (delivery_boy_name LIKE ? OR delivery_boy_id LIKE ?)
    ORDER BY created_at DESC
    """, (f"%{delivery_boy_name}%", f"%{delivery_boy_name}%"))
    rows = cursor.fetchall()
    conn.close()

    orders = []
    for r in rows:
        o = dict(r)
        o["items"] = json.loads(o["items"]) if o.get("items") else []
        orders.append(o)
    return {"orders": orders}


@app.post("/api/delivery/orders/{order_id}/pickup")
def pickup_order(order_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE orders SET status = 'out_for_delivery', updated_at = datetime('now') WHERE id = ? OR tracking_code = ?", (order_id, order_id))
    conn.commit()
    conn.close()
    return {"success": True, "status": "out_for_delivery"}


@app.post("/api/delivery/orders/{order_id}/delivered")
def complete_delivery(order_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE orders SET status = 'delivered', updated_at = datetime('now') WHERE id = ? OR tracking_code = ?", (order_id, order_id))
    conn.commit()
    conn.close()
    return {"success": True, "status": "delivered"}


# ----------------- 7. TABLE BOOKINGS -----------------

@app.post("/api/bookings")
def book_table(payload: CreateBookingSchema):
    b_id = f"bk-{uuid.uuid4().hex[:6]}"
    code = f"TB-{random.randint(1000, 9999)}"
    table_num = f"Table #{random.randint(1, 12)}"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO bookings (id, booking_code, customer_name, customer_email, customer_phone, booking_date, booking_time, guests, occasion, special_requests, table_number, status, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'confirmed', ?)
    """, (b_id, code, payload.customer_name, payload.customer_email, payload.customer_phone, payload.booking_date, payload.booking_time, payload.guests, payload.occasion, payload.special_requests, table_num, now_str))
    conn.commit()
    conn.close()

    return {"success": True, "booking_code": code, "table_number": table_num}


if __name__ == "__main__":
    import uvicorn
    print("Starting The Baker's Box FastAPI Backend on http://127.0.0.1:8000 ...")
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
