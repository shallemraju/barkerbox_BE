import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import (
    health_check, get_stats, get_menu, get_menu_item,
    create_order, track_order, advance_order_status,
    create_booking, create_custom_request, get_reviews,
    CreateOrderSchema, OrderItemSchema, CreateBookingSchema, CustomRequestSchema
)

def test_all():
    # 1. Health
    h = health_check()
    print("✓ Health Check:", h)
    assert h["status"] == "healthy"

    # 2. Stats
    s = get_stats()
    print("✓ Stats:", s)
    assert s["menu_items_count"] >= 60

    # 3. Menu items
    menu = get_menu()
    items = menu["items"]
    print(f"✓ Menu Items loaded: {len(items)}")
    assert len(items) >= 60

    # 4. Filter categories
    brownies = get_menu(category="brownies")["items"]
    print(f"✓ Brownies count: {len(brownies)}")
    assert len(brownies) >= 10

    # 5. Track sample order
    t = track_order("BB-7829")
    print(f"✓ Track sample order {t['tracking_code']}: status = {t['status']}, steps = {len(t['timeline'])}")
    assert len(t["timeline"]) == 5

    # 6. Advance order status
    adv = advance_order_status("BB-7829")
    print(f"✓ Advanced status: {adv}")

    # 7. Create new order
    order_req = CreateOrderSchema(
        customer_name="Aanya Sharma",
        customer_email="aanya@example.com",
        customer_phone="+91 98201 45678",
        delivery_address="Flat 402, Sunshine Heights, Rosewood Avenue, Bandra West",
        delivery_notes="Leave at door",
        items=[
            OrderItemSchema(id="br-kunafa", name="Kunafa Brownies", variant="Pack 9", price=850.0, quantity=1, eggless=True)
        ],
        discount_code="SWEET"
    )
    new_ord = create_order(order_req)
    print(f"✓ Created order: {new_ord['tracking_code']}, total = {new_ord['total']}")

    # 8. Create booking
    book_req = CreateBookingSchema(
        customer_name="Rohan Verma",
        customer_email="rohan@example.com",
        customer_phone="+91 98989 89898",
        booking_date="2026-11-20",
        booking_time="17:30",
        guests=2,
        occasion="Dessert Tasting"
    )
    new_bk = create_booking(book_req)
    print(f"✓ Created booking: {new_bk['booking_code']}, table = {new_bk['table_number']}")

    # 9. Custom cake request
    cust_req = CustomRequestSchema(
        customer_name="Kavita Sen",
        customer_email="kavita@example.com",
        customer_phone="+91 97777 88888",
        request_type="custom_cake",
        event_date="2026-12-01",
        flavor_preference="Lotus Biscoff",
        weight_kg=2.5,
        tier_count=2,
        is_eggless=True,
        theme_details="Pink vintage roses"
    )
    new_cust = create_custom_request(cust_req)
    print(f"✓ Custom cake request: {new_cust['request_id']}")

    # 10. Reviews
    revs = get_reviews()
    print(f"✓ Reviews count: {len(revs['reviews'])}")

    print("\n🎉 ALL 10 DIRECT FASTAPI FUNCTION TESTS PASSED!")

if __name__ == "__main__":
    test_all()
