"""
Direct unit test for FastAPI endpoints:
1. Customer Registration (Name, Email, Phone)
2. OTP Generation
3. OTP Verification
4. Role-based Admin protection
5. Admin Login
6. Customer Order placement
7. Order Tracking
8. Delivery Assignment
"""
import sys
import main
from main import (
    CustomerRegisterSchema, SendOtpSchema, VerifyOtpSchema, AdminLoginSchema,
    CreateOrderSchema, OrderItemSchema, AssignDeliverySchema, UpdateOrderStatusSchema,
    register_customer, send_otp, verify_otp, admin_login,
    get_all_orders, get_admin_stats, update_order_status, assign_order_to_delivery_boy,
    place_order, track_order, get_current_admin
)
from fastapi import HTTPException

def run_tests():
    print("1. Testing Customer Registration...")
    reg_data = CustomerRegisterSchema(
        name="Aarav Sharma",
        email="aarav.test@example.com",
        phone="9820123456"
    )
    try:
        reg_res = register_customer(reg_data)
        print(f"   Success: {reg_res['message']}")
    except HTTPException as e:
        if "already registered" in e.detail:
            print(f"   Customer already registered: {e.detail}")
        else:
            raise e

    print("\n2. Testing OTP Generation (POST /api/auth/send-otp)...")
    otp_res = send_otp(SendOtpSchema(phone="9820123456"))
    assert otp_res["success"] is True
    generated_otp = otp_res["otp"]
    print(f"   Success: OTP generated is {generated_otp}")

    print("\n3. Testing OTP Verification with wrong code...")
    try:
        verify_otp(VerifyOtpSchema(phone="9820123456", otp="000000"))
        assert False, "Should have raised HTTPException for wrong OTP"
    except HTTPException as e:
        assert e.status_code == 400
        print("   Success: Wrong OTP correctly rejected with 400")

    print("\n4. Testing OTP Verification with valid code...")
    login_res = verify_otp(VerifyOtpSchema(phone="9820123456", otp=generated_otp))
    assert login_res["success"] is True
    customer_token = login_res["token"]
    customer_user = login_res["user"]
    print(f"   Success: Customer signed in! Name: {customer_user['name']}, Token: {customer_token[:15]}...")

    print("\n5. Testing Security: require_admin rejection of customer token...")
    try:
        get_current_admin(authorization=f"Bearer {customer_token}")
        assert False, "Should have raised HTTPException 403"
    except HTTPException as e:
        assert e.status_code == 403
        print(f"   Success: Customer token was blocked from admin access ({e.detail})")

    print("\n6. Testing Security: require_admin rejection of missing token...")
    try:
        get_current_admin(authorization=None)
        assert False, "Should have raised HTTPException 401"
    except HTTPException as e:
        assert e.status_code == 401
        print(f"   Success: Unauthenticated request was blocked ({e.detail})")

    print("\n7. Testing Admin Login (POST /api/admin/login)...")
    admin_auth = admin_login(AdminLoginSchema(email="admin@burgerbox.com", password="admin"))
    assert admin_auth["success"] is True
    admin_token = admin_auth["token"]
    print(f"   Success: Admin authorized! Token: {admin_token[:15]}...")

    print("\n8. Testing Admin Authorized Access with valid admin token...")
    admin_ctx = get_current_admin(authorization=f"Bearer {admin_token}")
    assert admin_ctx["role"] == "admin"
    stats = get_admin_stats(admin=admin_ctx)
    print(f"   Success: Admin retrieved stats: total orders = {stats['total_orders']}, customers = {stats['customers_count']}")

    print("\n9. Testing Customer Order Placement (POST /api/orders)...")
    order_payload = CreateOrderSchema(
        customer_id=customer_user["id"],
        customer_name=customer_user["name"],
        customer_email=customer_user["email"],
        customer_phone=customer_user["phone"],
        delivery_address="Flat 402, Sea Green Apartments, Bandra West, Mumbai",
        delivery_notes="Leave at door",
        items=[
            OrderItemSchema(
                id="br-classic",
                name="Classic Brownies",
                variant="Pack 9",
                price=550.0,
                quantity=1,
                eggless=True,
                custom_message="Best Wishes!"
            )
        ],
        payment_method="Cash on Delivery"
    )
    placed_order = place_order(order_payload)
    assert placed_order["success"] is True
    tracking_code = placed_order["tracking_code"]
    print(f"   Success: Order #{tracking_code} placed! Initial status: {placed_order['status']}")
    assert placed_order["status"] == "pending_review"

    print("\n10. Testing Live Order Tracking (GET /api/orders/{code}) while Awaiting Review...")
    track_info = track_order(tracking_code)
    assert track_info["status"] == "pending_review"
    assert len(track_info["timeline"]) == 6
    print(f"   Success: Timeline has 6 stages, current stage: {track_info['status']}")

    print("\n11. Testing Admin Order Review (Accept Order)...")
    from main import accept_order
    accept_res = accept_order(order_id=tracking_code, admin=admin_ctx)
    assert accept_res["success"] is True
    assert accept_res["status"] == "confirmed"
    print(f"   Success: Admin accepted order #{tracking_code}!")

    print("\n12. Testing Admin Delivery Boy Assignment...")
    assign_res = assign_order_to_delivery_boy(
        order_id=tracking_code,
        payload=AssignDeliverySchema(delivery_boy_id="del-1"),
        admin=admin_ctx
    )
    assert assign_res["success"] is True
    print(f"   Success: {assign_res['message']}")

    # Verify status changed to assigned
    track_info2 = track_order(tracking_code)
    assert track_info2["status"] == "assigned"
    assert track_info2["delivery_boy_name"] == "Rajesh Kumar"
    print(f"   Success: Order live tracking shows assigned to {track_info2['delivery_boy_name']}!")

    print("\n13. Testing Owner Login & Role Authorization...")
    from main import OwnerLoginSchema, owner_login, get_all_menu_items_for_admin, update_menu_item, UpdateMenuItemSchema
    # Test standard credentials
    owner_res = owner_login(OwnerLoginSchema(email="owner@bakersbox.com", password="Owner@BakersBox2026"))
    assert owner_res["success"] is True
    assert owner_res["user"]["role"] == "owner"
    owner_token = owner_res["token"]
    owner_ctx = get_current_admin(authorization=f"Bearer {owner_token}")
    assert owner_ctx["role"] == "owner"
    print(f"   Success: Owner logged in securely! Role: {owner_ctx['role']}, Token: {owner_token[:15]}...")

    # Test shorthand "owner" username and case-insensitive password tolerance
    owner_res_short = owner_login(OwnerLoginSchema(email="owner", password="owner@bakersbox2026"))
    assert owner_res_short["success"] is True
    assert owner_res_short["user"]["email"] == "owner@bakersbox.com"
    print("   Success: Shorthand 'owner' username and lowercase password tolerated perfectly!")

    # Test admin executive login through owner endpoint
    admin_owner_res = owner_login(OwnerLoginSchema(email="admin", password="admin"))
    assert admin_owner_res["success"] is True
    print("   Success: Admin executive allowed access through Owner portal!")

    print("\n14. Testing Owner Menu Management (List & Toggle)...")
    menu_catalog = get_all_menu_items_for_admin(admin=owner_ctx)
    assert menu_catalog["count"] == 82
    first_item = menu_catalog["items"][0]
    first_id = first_item["id"]
    print(f"   Success: Owner retrieved {menu_catalog['count']} delicacies.")

    # Toggle to unavailable
    toggle_res = update_menu_item(item_id=first_id, payload=UpdateMenuItemSchema(is_available=False), admin=owner_ctx)
    assert toggle_res["success"] is True
    assert toggle_res["item"]["is_available"] == 0

    # Restore to available
    restore_res = update_menu_item(item_id=first_id, payload=UpdateMenuItemSchema(is_available=True), admin=owner_ctx)
    assert restore_res["success"] is True
    assert restore_res["item"]["is_available"] == 1
    print(f"   Success: Owner toggled availability of {first_item['name']} successfully!")

    print("\n15. Testing Owner Delivery Fleet & Staff Onboarding...")
    from main import CreateDeliveryStaffSchema, UpdateStaffStatusSchema, add_delivery_staff, delete_delivery_staff, update_delivery_staff_status, get_delivery_staff
    
    # Onboard
    new_driver_res = add_delivery_staff(
        payload=CreateDeliveryStaffSchema(
            name="Vikram Singh",
            phone="+91 98200 99887",
            vehicle="Ather 450X (Chilled Box)"
        ),
        admin=owner_ctx
    )
    assert new_driver_res["success"] is True
    driver_id = new_driver_res["staff"]["id"]
    print(f"   Success: Onboarded {new_driver_res['staff']['name']} (ID: {driver_id})")

    # Toggle status to offline then available
    status_res = update_delivery_staff_status(
        staff_id=driver_id,
        payload=UpdateStaffStatusSchema(status="offline"),
        admin=owner_ctx
    )
    assert status_res["success"] is True
    assert status_res["staff"]["status"] == "offline"
    print("   Success: Staff status successfully toggled to offline")

    # Delete / offboard
    del_res = delete_delivery_staff(staff_id=driver_id, admin=owner_ctx)
    assert del_res["success"] is True
    print(f"   Success: Delivery partner {driver_id} offboarded successfully!")

    print("\n=======================================================")
    print("ALL FASTAPI AUTHENTICATION & RBAC ENDPOINT TESTS PASSED!")
    print("=======================================================")

if __name__ == "__main__":
    run_tests()
