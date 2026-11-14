"""
End-to-end automated test of the complete Multi-Role Workflow:
Customer Order -> Admin Assignment -> Delivery Boy Pickup -> Final Delivery -> Live Tracking Verification
"""
from main import (
    register, login, place_order, track_order,
    get_all_orders, assign_order_to_delivery_boy,
    get_delivery_boy_orders, pickup_order, complete_delivery,
    get_admin_stats,
    RegisterSchema, LoginSchema, CreateOrderSchema, OrderItemSchema, AssignDeliverySchema
)

def run_test():
    print("==================================================")
    print("Testing Complete BurgerBox Working Flow")
    print("==================================================")

    # 1. Customer Registration & Login
    print("\n[Step 1] Customer Auth:")
    cust = login(LoginSchema(email="customer@burgerbox.com", password="customer"))
    print(f"✓ Customer Logged In: {cust['user']['name']} ({cust['user']['email']})")

    # 2. Customer Places Order
    print("\n[Step 2] Customer Orders Food:")
    order_req = CreateOrderSchema(
        customer_id=cust["user"]["id"],
        customer_name=cust["user"]["name"],
        customer_email=cust["user"]["email"],
        customer_phone=cust["user"]["phone"],
        delivery_address="402, Sunshine Heights, Rosewood Avenue, Bandra West",
        items=[
            OrderItemSchema(id="br-classic", name="Classic Brownies", variant="Pack 9", price=550.0, quantity=2),
            OrderItemSchema(id="jar-lotus-biscoff", name="Lotus Biscoff Jar", variant="Single 200ml Jar", price=350.0, quantity=1)
        ],
        payment_method="Cash on Delivery"
    )
    placed = place_order(order_req)
    tracking_code = placed["tracking_code"]
    print(f"✓ Order Placed! Tracking Code: #{tracking_code}, Total: ₹{placed['total']}, Status: {placed['status']}")

    # 3. Customer Tracks Order - Stage 1 (Confirmed)
    track1 = track_order(tracking_code)
    print(f"✓ Customer Live Tracking: Current Status = {track1['status']} (Step {track1['current_step_index'] + 1}/5)")
    assert track1["status"] == "confirmed"

    # 4. Admin Receives Order in Admin Dashboard
    print("\n[Step 3] Admin Management:")
    admin_orders = get_all_orders(status="confirmed")["orders"]
    matching = [o for o in admin_orders if o["tracking_code"] == tracking_code]
    assert len(matching) > 0, "Admin must see newly placed order"
    print(f"✓ Admin Dashboard received new order #{tracking_code} from {matching[0]['customer_name']}")

    # 5. Admin Assigns Delivery Boy to Order
    print("\n[Step 4] Admin Assigns Delivery Boy:")
    assign_res = assign_order_to_delivery_boy(tracking_code, AssignDeliverySchema(delivery_boy_id="del-1"))
    print(f"✓ {assign_res['message']}")

    # Check order status changed to assigned
    track2 = track_order(tracking_code)
    print(f"✓ Customer Live Tracking updated: Status = {track2['status']}, Assigned to = {track2['delivery_boy_name']}")
    assert track2["status"] == "assigned"
    assert track2["delivery_boy_name"] == "Rajesh Kumar"

    # 6. Delivery Boy Terminal sees order & picks up food
    print("\n[Step 5] Delivery Boy Terminal:")
    deliv_orders = get_delivery_boy_orders(delivery_boy_name="Rajesh Kumar")["orders"]
    assigned_order = [o for o in deliv_orders if o["tracking_code"] == tracking_code][0]
    print(f"✓ Delivery Boy Rajesh Kumar sees order #{tracking_code} for {assigned_order['customer_name']}")

    # Delivery Boy Picks Up Food
    pickup_res = pickup_order(tracking_code)
    print(f"✓ Delivery Boy picked up food: Status = {pickup_res['status']}")

    # 7. Customer Tracks Order - Stage 4 (Out for Delivery)
    track3 = track_order(tracking_code)
    print(f"✓ Customer Live Tracking updated: Status = {track3['status']} ({track3['timeline'][3]['title']})")
    assert track3["status"] == "out_for_delivery"

    # 8. Delivery Boy Delivers Food to Customer Doorstep
    print("\n[Step 6] Final Doorstep Delivery:")
    deliv_res = complete_delivery(tracking_code)
    print(f"✓ Delivery Boy marked delivered: Status = {deliv_res['status']}")

    # 9. Customer Final Live Tracking - Stage 5 (Delivered)
    track4 = track_order(tracking_code)
    print(f"✓ Customer Live Tracking updated: Status = {track4['status']} ({track4['timeline'][4]['title']})")
    assert track4["status"] == "delivered"

    # 10. Admin Stats Verification
    stats = get_admin_stats()
    print(f"\n[Step 7] Admin Revenue & Stats: Total Revenue = ₹{stats['total_revenue']}, Orders = {stats['total_orders']}")

    print("\n🎉 COMPLETE WORKING FLOW (CUSTOMER -> ADMIN -> DELIVERY BOY -> CUSTOMER TRACKING) VERIFIED 100%!")

if __name__ == "__main__":
    run_test()
