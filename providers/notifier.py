def send_order_confirmation(email: str, order_id: int, grand_total_inr: int, flags: dict):
    """
    Mock Resend/SendGrid-style email provider.
    Currently always succeeds unless flags['notifier'] is set (optional).
    """
    # Optional future bug toggle for notifier - not in required 5 but health checks it
    if flags.get("notifier"):
        raise ConnectionError("Notification provider (Resend mock) is down: dial tcp api.resend.com:443: connection refused (simulated)")

    # mock send - just log
    print(f"[notifier] Sending order confirmation to {email} for order #{order_id} (₹{grand_total_inr})")
    return {"status": "sent", "to": email, "order_id": order_id}
