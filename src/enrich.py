"""
enrich.py
=========
Decides the nightly rate (ADR) and occupancy to use for a listing.

- If AIRDNA_API_KEY is set, calls AirDNA's Rentalizer estimate endpoint for a
  true address-level projection.
- Otherwise (or if that call fails/doesn't parse) it uses the market-level
  ADR/occupancy from config.py, lightly scaled by bedroom count and whether
  the listing looks like true waterfront.

AirDNA's API is enterprise-only: there's no public self-serve spec, and this
environment's network policy blocks the vendor's own docs (docs.airdna.co /
airdna.redoc.ly), so _try_airdna() below is assembled from third-party
summaries of the endpoint, not the primary reference. VERIFY the endpoint
path, request params, and response field names against your actual AirDNA
account docs/Postman collection - if the shape is off, the run keeps working
(it falls back to market estimates) but will print a [warn] line showing the
raw response so you can see exactly what to fix.
"""

import os

import requests

AIRDNA_BASE = "https://api.airdna.co/api/enterprise/v2"


def _bedroom_factor(bedrooms: int) -> float:
    """More beds -> higher nightly rate. Baseline is a 3-bedroom."""
    bedrooms = bedrooms or 3
    return max(0.7, min(1.6, 1 + 0.12 * (bedrooms - 3)))


def enrich(listing: dict, market: dict, has_dock: bool) -> dict:
    """Return {'adr', 'occ', 'source'} for this listing."""
    api_key = os.environ.get("AIRDNA_API_KEY", "").strip()
    if api_key:
        result = _try_airdna(listing, market, api_key)
        if result:
            return result

    # Fallback: scale the market ADR by size and waterfront premium.
    adr = market["adr"] * _bedroom_factor(listing.get("bedrooms", 3))
    if has_dock:
        adr *= 1.15  # waterfront/dock premium
    occ = market["occ"]
    return {"adr": round(adr), "occ": occ, "source": "market-estimate"}


def _first(data: dict, *keys):
    """Return the first present, non-None value among these keys."""
    for key in keys:
        if data.get(key) is not None:
            return data[key]
    return None


def _try_airdna(listing: dict, market: dict, api_key: str):
    """
    Calls AirDNA's Rentalizer estimate endpoint (GET /rentalizer/estimate)
    for this listing's address, and returns {"adr", "occ", "source": "airdna"}
    - or None to fall back to the market estimate, on any failure or if the
    response doesn't parse the way we expect.

    Never raises: like sources.fetch_rentcast, a bad response here should
    degrade the run to market estimates, not fail the whole weekly scout.
    """
    params = {
        "address": listing.get("address"),
        "bedrooms": listing.get("bedrooms") or 3,
        "bathrooms": listing.get("bathrooms") or 2,
    }
    if listing.get("lat") and listing.get("lng"):
        params["lat"] = listing["lat"]
        params["lng"] = listing["lng"]
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}

    try:
        resp = requests.get(f"{AIRDNA_BASE}/rentalizer/estimate",
                             params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:  # noqa: BLE001 - degrade gracefully, like RentCast
        print(f"  [warn] AirDNA request failed for {listing.get('address')}: {e}. "
              f"Using market estimate.")
        return None

    # Some AirDNA responses nest the estimate under "data" or "result" -
    # unwrap if so, then try a few plausible field-name variants for each
    # value. Adjust these keys once you've seen a real response shape.
    result = data.get("data", data.get("result", data))
    adr = _first(result, "adr", "average_daily_rate", "avg_daily_rate")
    occ = _first(result, "occupancy", "occupancy_rate")
    revenue = _first(result, "revenue", "projected_revenue", "annual_revenue")

    if occ is not None and occ > 1:
        occ = occ / 100  # normalize if given as a percentage (e.g. 55 -> 0.55)

    if adr is None and revenue is not None and occ:
        adr = revenue / (occ * 365)  # derive ADR from revenue + occupancy

    if adr is None or occ is None:
        print(f"  [warn] AirDNA response for {listing.get('address')} didn't have "
              f"the expected adr/occupancy/revenue fields - raw response: {data}")
        return None

    return {"adr": round(adr), "occ": round(occ, 4), "source": "airdna"}
