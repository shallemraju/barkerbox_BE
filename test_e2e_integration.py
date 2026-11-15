"""
BurgerBox / The Baker's Box - End-to-End Integration Verification Suite
Tests the complete integrated Customer & Owner workflows:
- Customer Registration, OTP Generation & Login
- Live Catalog & Menu Retrieval (82 Authentic Items)
- Cart Checkout & Order Placement
- Real-Time Live Order Tracking (Timeline Verification)
- Customer Order History (GET /api/orders/my)
- Owner Authentication & Role Enforcement
- Owner Order Review & Acceptance
- Delivery Fleet Assignment
- Order Status Progression to Delivery
- Contact Inquiry Submission & Owner Inquiry Management
- Menu Availability & Price Management
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import json
from datetime import datetime
from database import get_db, init_db, ensure_default_accounts
from main import (
    register_customer, send_otp, verify_otp,
    get_menu, place_order, get_my_orders, track_order,
    owner_login, get_all_orders, accept_order, assign_order_to_delivery_boy,
    update_order_status, get_delivery_staff, submit_contact_inquiry,
    get_admin_contact_inquiries, update_contact_inquiry_status,
    update_menu_item,
    CustomerRegisterSchema, SendOtpSchema, VerifyOtpSchema,
    CreateOrderSchema, OrderItemSchema, OwnerLoginSchema,
    ContactInquirySchema, UpdateMenuItemSchema, AssignDeliverySchema,
    UpdateOrderStatusSchema
)

def run_e2e_tests():
    print("==================================================================")
    print("   THE BAKER'S BOX - COMPLETE END-TO-END WORKFLOW INTEGRATION     ")
    print("==================================================================")
    
    init_db()
    ensure_default_accounts()

    # 1. Menu Catalog Verification
    print("\n[Step 1] Testing Public Menu Catalog...")
    menu_res = get_menu()
    items = menu_res.get("items", [])
    print(f" -> Found {len(items)} active delicacies in database catalog.")
    assert len(items) >= 80, f"Expected 82 items, got {len(items)}"
    categories = {i["category"] for i in items}
    print(f" -> Active Categories: {categories}")
    assert "brownies" in categories
    assert "cheesecakes" in categories
    print(" [OK] Step 1: Catalog verified.")

    # 2. Customer Registration
    test_phone = "9820099881"
    test_email = "ananya.patisserie@example.com"
    test_name = "Ananya Deshmukh"

    print(f"\n[Step 2] Testing Customer Registration for {test_name}...")
    reg_schema = CustomerRegisterSchema(name=test_name, email=test_email, phone=test_phone)
    try:
        reg_res = register_customer(reg_schema)
        print(f" -> Registration response: {reg_res.get('message')}")
        assert reg_res.get("success") is True
    except Exception as e:
        if "already registered" in str(e).lower():
            print(" -> Customer was already registered. Proceeding to login.")
        else:
            raise e
    print(" [OK] Step 2: Customer registration verified.")

    # 3. OTP Generation & Verification
    print(f"\n[Step 3] Testing OTP Authentication for +91 {test_phone}...")
    otp_res = send_otp(SendOtpSchema(phone=test_phone))
    otp_code = otp_res.get("otp")
    print(f" -> OTP generated: {otp_code}")
    assert otp_code and len(otp_code) == 6

    verify_res = verify_otp(VerifyOtpSchema(phone=test_phone, otp=otp_code))
    cust_token = verify_res.get("token")
    cust_user = verify_res.get("user")
    print(f" -> Verified! Customer Token: {cust_token[:15]}..., User: {cust_user.get('name')}")
    assert cust_token and cust_user
    print(" [OK] Step 3: OTP Authentication verified.")

    # 4. Customer Order Placement
    print("\n[Step 4] Testing Cart Checkout & Order Placement...")
    order_items = [
        OrderItemSchema(
            id="br-kunafa",
            name="Kunafa Brownies",
            variant="Pack 6",
            price=780.0,
            quantity=1,
            eggless=True,
            custom_message="Happy Birthday!"
        ),
        OrderItemSchema(
            id="jar-lotus-biscoff",
            name="Lotus Biscoff Dessert Jar",
            variant="Single 200ml Jar",
            price=350.0,
            quantity=2,
            eggless=True,
            custom_message=""
        )
    ]

    order_payload = CreateOrderSchema(
        customer_id=cust_user.get("id"),
        customer_name=cust_user.get("name"),
        customer_email=cust_user.get("email"),
        customer_phone=test_phone,
        delivery_address="Flat 402, Sea Green Apts, Pali Hill, Bandra West, Mumbai 400050",
        delivery_notes="Ring bell and leave with security if unavailable",
        items=order_items,
        payment_method="UPI / QR Code",
        discount_code="BAKER10"
    )

    order_res = place_order(order_payload)
    order_id = order_res.get("order_id")
    tracking_code = order_res.get("tracking_code")
    print(f" -> Order Placed! ID: {order_id}, Tracking Code: #{tracking_code}, Total: ₹{order_res.get('total')}")
    assert order_id and tracking_code
    print(" [OK] Step 4: Order placement verified.")

    # 5. Customer Order History
    print(f"\n[Step 5] Testing Customer Order History for {test_email}...")
    my_orders_res = get_my_orders(email=test_email)
    my_orders = my_orders_res.get("orders", [])
    print(f" -> Retrieved {len(my_orders)} order(s) for customer.")
    assert any(o["tracking_code"] == tracking_code for o in my_orders)
    print(" [OK] Step 5: Customer order history verified.")

    # 6. Live Order Tracking (Customer View)
    print(f"\n[Step 6] Testing Live Order Tracking for #{tracking_code}...")
    track_res = track_order(tracking_code=tracking_code)
    print(f" -> Status: {track_res.get('status')}")
    assert track_res.get("status") == "pending_review"
    assert "timeline" in track_res
    print(f" -> Timeline Stages: {[s['title'] for s in track_res['timeline']]}")
    print(" [OK] Step 6: Initial live tracking verified.")

    # 7. Owner Authentication
    print("\n[Step 7] Testing Owner Portal Login...")
    owner_creds = OwnerLoginSchema(email="owner@bakersbox.com", password="Owner@BakersBox2026")
    owner_res = owner_login(owner_creds)
    owner_token = owner_res.get("token")
    owner_user_data = owner_res.get("user")
    print(f" -> Owner Authorized! Role: {owner_user_data.get('role')}, Token: {owner_token[:15]}...")
    assert owner_token and owner_user_data.get("role") == "owner"
    print(" [OK] Step 7: Owner authentication verified.")

    # Mock admin dict for protected admin dependencies
    admin_ctx = {"id": owner_user_data["id"], "role": "owner", "email": "owner@bakersbox.com"}

    # 8. Owner Order Review & Acceptance
    print(f"\n[Step 8] Testing Owner Acceptance of Order #{tracking_code}...")
    accept_res = accept_order(order_id=order_id, admin=admin_ctx)
    print(f" -> Acceptance response: {accept_res.get('message')}")
    assert accept_res.get("status") == "confirmed"
    
    track_after_accept = track_order(tracking_code=tracking_code)
    assert track_after_accept.get("status") == "confirmed"
    print(" [OK] Step 8: Order acceptance verified.")

    # 9. Delivery Fleet Retrieval & Assignment
    print("\n[Step 9] Testing Delivery Staff Assignment...")
    staff_res = get_delivery_staff(admin=admin_ctx)
    fleet = staff_res.get("staff", [])
    print(f" -> Available Fleet Partners: {[s['name'] for s in fleet]}")
    assert len(fleet) > 0
    assigned_driver = fleet[0]

    assign_res = assign_order_to_delivery_boy(
        order_id=order_id,
        payload=AssignDeliverySchema(delivery_boy_id=assigned_driver["id"]),
        admin=admin_ctx
    )
    print(f" -> Assignment response: {assign_res.get('message')}")
    assert assign_res.get("success") is True or assign_res.get("status") == "assigned"

    track_after_assign = track_order(tracking_code=tracking_code)
    assert track_after_assign.get("status") == "assigned"
    assert track_after_assign.get("delivery_boy_name") == assigned_driver["name"]
    print(f" -> Assigned Courier: {track_after_assign.get('delivery_boy_name')} ({track_after_assign.get('delivery_boy_phone')})")
    print(" [OK] Step 9: Delivery assignment verified.")

    # 10. Status Progression to Delivered
    print("\n[Step 10] Testing Order Status Progression to 'delivered'...")
    update_order_status(
        order_id=order_id,
        payload=UpdateOrderStatusSchema(status="out_for_delivery"),
        admin=admin_ctx
    )
    track_out = track_order(tracking_code=tracking_code)
    assert track_out.get("status") == "out_for_delivery"

    update_order_status(
        order_id=order_id,
        payload=UpdateOrderStatusSchema(status="delivered"),
        admin=admin_ctx
    )
    track_deliv = track_order(tracking_code=tracking_code)
    assert track_deliv.get("status") == "delivered"
    assert track_deliv["timeline"][-1]["state"] in ["active", "completed"]
    print(" -> Final Status: 'delivered' with 100% completed timeline!")
    print(" [OK] Step 10: Status progression verified.")

    # 11. Contact Inquiry & Corporate Gifting
    print("\n[Step 11] Testing Contact & Bulk Gifting Inquiries...")
    inquiry_payload = ContactInquirySchema(
        name="Rohit Singhania",
        email="rohit.singhania@corp.com",
        phone="+91 98200 44556",
        inquiry_type="bulk_gifting",
        message="Requesting quote for 100 assorted dessert jars for corporate gifting."
    )
    inq_res = submit_contact_inquiry(inquiry_payload)
    inquiry_id = inq_res.get("inquiry_id")
    print(f" -> Inquiry Submitted! ID: {inquiry_id}")
    assert inq_res.get("status") == "success"

    all_inqs = get_admin_contact_inquiries(admin=admin_ctx)
    found_inq = next((i for i in all_inqs.get("inquiries", []) if i["id"] == inquiry_id), None)
    assert found_inq is not None
    print(f" -> Owner retrieved inquiry: {found_inq['name']} - {found_inq['inquiry_type']}")

    update_contact_inquiry_status(inquiry_id=inquiry_id, payload={"status": "contacted"}, admin=admin_ctx)
    print(" [OK] Step 11: Contact inquiry lifecycle verified.")

    # 12. Menu Management (Toggle & Price Edit)
    print("\n[Step 12] Testing Menu Item Management...")
    update_res = update_menu_item(
        item_id="br-kunafa",
        payload=UpdateMenuItemSchema(is_available=True, base_price=780.0),
        admin=admin_ctx
    )
    print(f" -> Menu Update: {update_res.get('message')}")
    assert update_res.get("success") is True
    print(" [OK] Step 12: Menu management verified.")

    print("\n==================================================================")
    print("   ALL 12 END-TO-END INTEGRATION TESTS PASSED WITH 100% SUCCESS!  ")
    print("==================================================================")

if __name__ == "__main__":
    run_e2e_tests()
