"""
enrich.py
=========
Decides the nightly rate (ADR) and occupancy to use for a listing.

- If AIRDNA_API_KEY is set, this is where you'd call AirDNA's Rentalizer for a
  true address-level projection. A stub is provided; AirDNA API access is
  gated/enterprise, so wire in the exact endpoint when you have credentials.
- Otherwise it uses the market-level ADR/occupancy from config.py, lightly
  scaled by bedroom count and whether the listing looks like true waterfront.
"""

import os


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


def _try_airdna(listing, market, api_key):
    """
    Placeholder for a real AirDNA Rentalizer call. Returns None so the caller
    falls back to market estimates until you implement the live request.

    When ready, POST the address/lat-lng to AirDNA's property endpoint and
    return {"adr": ..., "occ": ..., "source": "airdna"}.
    """
    return None
