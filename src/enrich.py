"""
enrich.py
=========
Decides the nightly rate (ADR) and occupancy to use for a listing.

- If AIRROI_API_KEY is set, calls AirROI's revenue calculator for a live,
  comp-based estimate. AirROI is a self-serve, pay-as-you-go alternative to
  AirDNA (no sales contract) - see https://www.airroi.com/api.
- Else if AIRDNA_API_KEY is set, calls AirDNA's Rentalizer estimate endpoint
  instead (enterprise-only, sales-gated).
- Otherwise (or if the call fails/doesn't parse) it uses the market-level
  ADR/occupancy from config.py, lightly scaled by bedroom count and whether
  the listing looks like true waterfront.

Neither provider's canonical docs were reachable from this environment
(AirROI's own site and AirDNA's docs are both blocked by the network egress
policy), so both _try_* functions below are assembled from third-party/
search-result summaries of each API, not the primary reference. Both are
built to fail safe: any request error or unexpected response shape prints a
[warn] line (with the raw response, for AirROI/AirDNA respectively) and
falls back to the market estimate rather than crashing the run.
"""

import os

import requests

AIRROI_BASE = "https://api.airroi.com"
AIRDNA_BASE = "https://api.airdna.co/api/enterprise/v2"


def _bedroom_factor(bedrooms: int) -> float:
    """More beds -> higher nightly rate. Baseline is a 3-bedroom."""
    bedrooms = bedrooms or 3
    return max(0.7, min(1.6, 1 + 0.12 * (bedrooms - 3)))


def enrich(listing: dict, market: dict, has_dock: bool) -> dict:
    """Return {'adr', 'occ', 'source'} for this listing."""
    airroi_key = os.environ.get("AIRROI_API_KEY", "").strip()
    if airroi_key:
        result = _try_airroi(listing, market, airroi_key)
        if result:
            return result

    airdna_key = os.environ.get("AIRDNA_API_KEY", "").strip()
    if airdna_key:
        result = _try_airdna(listing, market, airdna_key)
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


def _try_airroi(listing: dict, market: dict, api_key: str):
    """
    Calls AirROI's revenue calculator (GET /calculator/estimate) for this
    listing's coordinates, and returns {"adr", "occ", "source": "airroi"} -
    or None to fall back, on any failure or unparseable response.

    Never raises: like sources.fetch_rentcast, a bad response here should
    degrade the run to market estimates, not fail the whole weekly scout.
    """
    lat, lng = listing.get("lat"), listing.get("lng")
    if lat is None or lng is None:
        return None  # AirROI's calculator is coordinate-based

    bedrooms = listing.get("bedrooms") or 3
    params = {
        "lat": lat,
        "lng": lng,
        "bedrooms": bedrooms,
        "baths": listing.get("bathrooms") or 2,
        "guests": max(2, bedrooms * 2),  # rough 2-per-bedroom occupancy assumption
        "currency": "usd",
    }
    headers = {"X-API-KEY": api_key, "Accept": "application/json"}

    try:
        resp = requests.get(f"{AIRROI_BASE}/calculator/estimate",
                             params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:  # noqa: BLE001 - degrade gracefully, like RentCast
        print(f"  [warn] AirROI request failed for {listing.get('address')}: {e}. "
              f"Using market estimate.")
        return None

    # Documented shape: {"percentiles": {"adr": {"p50": ...}, "occupancy":
    # {"p50": ...}, "revenue": {"p50": ...}}, ...}. Use the median (p50).
    percentiles = data.get("percentiles") or {}
    adr = (percentiles.get("adr") or {}).get("p50")
    occ = (percentiles.get("occupancy") or {}).get("p50")
    revenue = (percentiles.get("revenue") or {}).get("p50")

    if occ is not None and occ > 1:
        occ = occ / 100  # normalize if given as a percentage (e.g. 55 -> 0.55)

    if adr is None and revenue is not None and occ:
        adr = revenue / (occ * 365)  # derive ADR from revenue + occupancy

    if adr is None or occ is None:
        print(f"  [warn] AirROI response for {listing.get('address')} didn't have "
              f"the expected percentiles.adr/occupancy fields - raw response: {data}")
        return None

    return {"adr": round(adr), "occ": round(occ, 4), "source": "airroi"}


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
