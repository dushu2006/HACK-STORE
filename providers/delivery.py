import re

# Simple Indian pincode -> city mapping for demo (no external API needed, but we mock Nominatim)
PINCODE_CITY = {
    "110001": "New Delhi",
    "400001": "Mumbai",
    "560001": "Bengaluru",
    "600001": "Chennai",
    "700001": "Kolkata",
    "380001": "Ahmedabad",
    "500001": "Hyderabad",
    "302001": "Jaipur",
    "411001": "Pune",
    "682001": "Kochi",
}

def _city_from_pincode(pincode: str) -> str | None:
    if not pincode:
        return None
    return PINCODE_CITY.get(pincode.strip())

def _fee_for_city(city: str | None, pincode: str | None) -> int:
    # metro cities 49, others 79, remote 99
    metro = {"New Delhi", "Mumbai", "Bengaluru", "Chennai", "Kolkata", "Hyderabad", "Pune"}
    if city in metro:
        return 49
    if pincode:
        # first digit heuristic: 1-2 north, 4 west, 5 south etc - all metro-ish
        # fallback
        return 79
    return 79

def compute_delivery(lat: float | None, lng: float | None, pincode: str | None, flags: dict):
    """
    Mock maps/delivery provider. Uses browser Geolocation lat/lng + pincode fallback.
    When flags['delivery'] is True, simulates maps API down.
    """
    if flags.get("delivery"):
        raise ConnectionError("Delivery/Map provider (Nominatim) is down: dial tcp nominatim.openstreetmap.org:443: connect: connection refused (simulated)")

    # validate pincode if provided
    city = None
    if pincode:
        pincode = str(pincode).strip()
        if not re.fullmatch(r"\d{6}", pincode):
            raise ValueError(f"Invalid pincode: {pincode!r} — must be 6 digits")
        city = _city_from_pincode(pincode)
        if city is None:
            # unknown pincode, fallback to generic city based on first digits
            prefix = pincode[:2]
            # mock city inference
            city = f"Zone {prefix} - India"

    # if lat/lng provided, try to infer city via lat/lng bounding boxes (mock, no network)
    # For demo, we don't call real Nominatim to keep sandbox offline.
    # But structure is ready to call Nominatim if needed.
    if lat is not None and lng is not None:
        # simple bounding mock
        if 28 < lat < 28.8 and 77 < lng < 77.3:
            inferred = "New Delhi"
        elif 18.9 < lat < 19.3 and 72.7 < lng < 73:
            inferred = "Mumbai"
        elif 12.8 < lat < 13.1 and 77.4 < lng < 77.8:
            inferred = "Bengaluru"
        elif 13 < lat < 13.2 and 80 < lng < 80.4:
            inferred = "Chennai"
        else:
            inferred = city or "India"
        # prefer pincode city if both provided, else inferred
        city = city or inferred

    if not city:
        city = "India"
        # if no pincode and no lat/lng, default fee still applies but we require at least one?
        # We'll allow delivery with no location but fee higher
    fee = _fee_for_city(city, pincode)
    # ETA logic
    if city in {"Mumbai", "New Delhi", "Bengaluru"}:
        eta = "1-2 days"
    elif fee == 49:
        eta = "2-3 days"
    else:
        eta = "3-4 days"

    # Mock distance calculation if lat/lng present
    # We could compute haversine to a warehouse (Mumbai) but keep simple.
    return {
        "city": city,
        "fee_inr": fee,
        "eta": eta,
    }
