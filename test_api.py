import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import app
from fastapi.testclient import TestClient

def run_tests():
    client = TestClient(app)
    
    # 1. Health
    res = client.get("/api/health")
    assert res.status_code == 200, f"Health check failed: {res.text}"
    print("✓ Health Check Passed:", res.json()["brand"])

    # 2. Stats
    res = client.get("/api/stats")
    assert res.status_code == 200
    print("✓ Stats Endpoint Passed:", res.json())

    # 3. Menu
    res = client.get("/api/menu")
    assert res.status_code == 200
    data = res.json()
    items = data["items"]
    print(f"✓ Menu Endpoint Passed: {len(items)} items found.")
    assert len(items) >= 60, f"Expected 60+ menu items, got {len(items)}"

    # 4. Filter Brownies
    res = client.get("/api/menu?category=brownies")
    assert res.status_code == 200
    brownies = res.json()["items"]
    print(f"✓ Category Filter 'brownies' Passed: {len(brownies)} brownies.")

    # 5. Track sample order
    res = client.get("/api/orders/BB-7829")
    assert res.status_code == 200, f"Tracking failed: {res.text}"
    order = res.json()
    print("✓ Order Tracking Passed:", order["tracking_code"], "Status:", order["status"])
    assert len(order["timeline"]) == 5, "Timeline must have 5 steps"

    # 6. Create new order
    order_payload = {
        "customer_name": "Priya Sharma",
        "customer_email": "priya@example.com",
        "customer_phone": "+91 98200 99999",
        "delivery_address": "Ocean Drive, Bandra West",
        "delivery_notes": "Ring twice",
        "items": [
            {
                "id": "br-kunafa",
                "name": "Kunafa Brownies",
                "variant": "Pack 9",
                "price": 850,
                "quantity": 1,
                "eggless": True,
                "custom_message": "Happy Birthday!"
            }
        ],
        "payment_method": "UPI",
        "discount_code": "SWEET"
    }
    res = client.post("/api/orders", json=order_payload)
    assert res.status_code == 200, f"Order placement failed: {res.text}"
    new_order = res.json()
    code = new_order["tracking_code"]
    print("✓ Create Order Passed:", code, "Total:", new_order["total"])

    # 7. Track newly created order
    res = client.get(f"/api/orders/{code}")
    assert res.status_code == 200
    print("✓ Track Newly Placed Order Passed:", res.json()["tracking_code"])

    # 8. Create table booking
    booking_payload = {
        "customer_name": "Arjun Kapoor",
        "customer_email": "arjun@example.com",
        "customer_phone": "+91 99887 76655",
        "booking_date": "2026-11-22",
        "booking_time": "18:00",
        "guests": 4,
        "occasion": "Birthday Celebration",
        "special_requests": "Window seat please"
    }
    res = client.post("/api/bookings", json=booking_payload)
    assert res.status_code == 200
    bk = res.json()
    print("✓ Table Booking Passed:", bk["booking_code"], bk["table_number"])

    # 9. Custom request
    custom_payload = {
        "customer_name": "Ananya Roy",
        "customer_email": "ananya@example.com",
        "customer_phone": "+91 91234 56789",
        "request_type": "custom_cake",
        "event_date": "2026-12-10",
        "flavor_preference": "Belgium Chocolate",
        "weight_kg": 3.0,
        "tier_count": 2,
        "is_eggless": True,
        "theme_details": "Pastel Pink Carousel theme with edible lace"
    }
    res = client.post("/api/custom-request", json=custom_payload)
    assert res.status_code == 200
    print("✓ Custom Cake Request Passed:", res.json()["request_id"])

    # 10. Reviews
    res = client.get("/api/reviews")
    assert res.status_code == 200
    print("✓ Get Reviews Passed: Count =", len(res.json()["reviews"]))

    print("\n🎉 ALL 10 FASTAPI BACKEND TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_tests()
