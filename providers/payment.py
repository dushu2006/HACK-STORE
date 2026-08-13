import os
import uuid

def charge_payment(amount_inr: int, token: str | None, flags: dict):
    """
    Mock Razorpay-style payment provider.
    Raises real exceptions based on bug flags.
    """
    # delivery flag not relevant here
    if flags.get("payment"):
        # payment provider simulated down
        raise ConnectionError("Payment provider (Razorpay mock) is unreachable: dial tcp api.razorpay.com:443: connect: connection refused (simulated)")

    if flags.get("config"):
        # code reads WRONG env var name (unset) while real var is set
        # Real var: PAYMENT_PUBLISHABLE_KEY ; wrong: PAYMENT_PUB_KEY_WRONG or WRONG_NAME
        # Ensure we set a dummy real var for demo if not present.
        # But if flag is on, we intentionally read wrong name.
        val = os.getenv("WRONG_NAME")  # deliberately wrong, usually unset
        if not val:
            # The correct var might be set - show that
            correct = os.getenv("PAYMENT_PUBLISHABLE_KEY", "<unset>")
            raise EnvironmentError(
                f"Missing required env var PAYMENT_PUBLISHABLE_KEY: attempted to read WRONG_NAME which is unset (correct value present as PAYMENT_PUBLISHABLE_KEY={correct!r} but code reads wrong name)"
            )

    if flags.get("code"):
        # missing null-guard: user has no saved payment method => token is None
        # The buggy code accesses payment_method.token without guard.
        # Simulate that by constructing an object and accessing .token
        # If token is None, payment_method will be None, then .token raises AttributeError
        payment_method = None if token is None else type("PaymentMethod", (), {"token": token})()
        # Null guard: handle None payment_method/tocken gracefully
        if payment_method is None:
            _active_token = None
        else:
            _active_token = payment_method.token

        # Also demonstrate alternative: token.strip() without guard
        # _ = token.strip() # would also raise AttributeError

    # Normal mock success path
    # Even if token is None and code flag is OFF, we handle gracefully:
    # For guest or missing token we generate a temp token
    effective_token = token if token else f"tok_guest_{uuid.uuid4().hex[:8]}"
    # mock charge
    return {
        "status": "captured",
        "id": f"pay_{uuid.uuid4().hex[:10]}",
        "amount_inr": amount_inr,
        "token_used": effective_token[:12] + "...",
    }
