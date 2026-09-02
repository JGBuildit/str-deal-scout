"""
sources.py
==========
Fetches for-sale listings for a market.

- If RENTCAST_API_KEY is set (a GitHub Secret), it queries the RentCast
  active-sale-listings endpoint around each lake's coordinates.
- If not, it returns a small built-in SAMPLE set so the whole pipeline runs
  end-to-end in "demo mode" the very first time, before you buy any API access.

NOTE: RentCast's exact field names/params can change. This targets their v1
`/listings/sale` endpoint. If live results look wrong, check the current docs
at https://developers.rentcast.io and adjust the params/keys below.

RentCast does not return a browsable listing URL, only `daysOnMarket` /
`listedDate` and an MLS number. `url` is kept in case a future API version
adds one; the dashboard falls back to a Zillow address search when it's empty.
"""

import os
from datetime import date, datetime

import requests

RENTCAST_BASE = "https://api.rentcast.io/v1"


def _days_on_market(raw: dict):
    """Prefer RentCast's own daysOnMarket; fall back to listedDate math."""
    dom = raw.get("daysOnMarket")
    if dom is not None:
        return dom
    listed = raw.get("listedDate")
    if listed:
        try:
            listed_date = datetime.fromisoformat(listed.replace("Z", "+00:00")).date()
            return (date.today() - listed_date).days
        except (ValueError, TypeError):
            return None
    return None


def _normalize(raw: dict) -> dict:
    """Map a RentCast listing record onto the fields our pipeline expects."""
    return {
        "address": raw.get("formattedAddress") or raw.get("addressLine1") or "Unknown address",
        "city": raw.get("city", ""),
        "state": raw.get("state", ""),
        "price": raw.get("price") or 0,
        "bedrooms": raw.get("bedrooms") or 0,
        "bathrooms": raw.get("bathrooms") or 0,
        "sqft": raw.get("squareFootage") or 0,
        "property_type": raw.get("propertyType", ""),
        "description": (raw.get("description") or ""),
        "url": raw.get("listingUrl") or "",
        "days_on_market": _days_on_market(raw),
        "lat": raw.get("latitude"),
        "lng": raw.get("longitude"),
    }


def fetch_rentcast(market: dict, api_key: str) -> list:
    """Query RentCast for active sale listings around a lake's coordinates."""
    params = {
        "latitude": market["lat"],
        "longitude": market["lng"],
        "radius": market["radius_miles"],
        "status": "Active",
        "limit": 50,
    }
    headers = {"X-Api-Key": api_key, "Accept": "application/json"}
    resp = requests.get(f"{RENTCAST_BASE}/listings/sale",
                        params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    records = data if isinstance(data, list) else data.get("listings", data.get("data", []))
    return [_normalize(r) for r in records]


def fetch_listings(market: dict) -> tuple:
    """
    Return (listings, mode). mode is "live" or "demo".
    Never raises: on any API error it falls back to demo data so the weekly
    run still produces a digest instead of failing the whole Action.
    """
    api_key = os.environ.get("RENTCAST_API_KEY", "").strip()
    if api_key:
        try:
            listings = fetch_rentcast(market, api_key)
            return listings, "live"
        except Exception as e:  # noqa: BLE001 - we want to degrade gracefully
            print(f"  [warn] RentCast failed for {market['label']}: {e}. Using demo data.")
    return SAMPLE_LISTINGS.get(market["key"], []), "demo"


# ---------------------------------------------------------------------------
# DEMO DATA — realistic-looking placeholders so you can see the pipeline work
# before wiring in a paid API. These are illustrative, not real active listings.
# ---------------------------------------------------------------------------
SAMPLE_LISTINGS = {
    "lake_milton": [
        {"address": "259 NE River Rd, Lake Milton, OH", "city": "Lake Milton", "state": "OH",
         "price": 295000, "bedrooms": 3, "bathrooms": 2, "sqft": 1584,
         "property_type": "Single Family", "url": "", "days_on_market": 12,
         "description": "Updated lakefront with private dock access, true lake living."},
        {"address": "17544 Pine Ct, Lake Milton, OH", "city": "Lake Milton", "state": "OH",
         "price": 839900, "bedrooms": 5, "bathrooms": 5, "sqft": 3200,
         "property_type": "Single Family", "url": "", "days_on_market": 64,
         "description": "Two homes, direct lake frontage with 3 private boat slips."},
        {"address": "506 Milton Commons Blvd A6, Lake Milton, OH", "city": "Lake Milton", "state": "OH",
         "price": 379500, "bedrooms": 2, "bathrooms": 2, "sqft": 1680,
         "property_type": "Condo", "url": "", "days_on_market": 5,
         "description": "Lakefront condo in gated community with own boat dock. HOA applies."},
    ],
    "berlin_reservoir": [
        {"address": "10024 Cummins Ln, Berlin Center, OH", "city": "Berlin Center", "state": "OH",
         "price": 389000, "bedrooms": 3, "bathrooms": 2, "sqft": 1900,
         "property_type": "Single Family", "url": "", "days_on_market": 31,
         "description": "Summer retreat, full-time home or secondary income rental near Berlin Lake waterfront."},
    ],
    "bemus_point": [
        {"address": "12 Lakeside Dr, Bemus Point, NY", "city": "Bemus Point", "state": "NY",
         "price": 675000, "bedrooms": 4, "bathrooms": 3, "sqft": 2400,
         "property_type": "Single Family", "url": "", "days_on_market": 98,
         "description": "Walkable village lakefront with dock on Chautauqua Lake."},
    ],
    "findley_lake": [
        {"address": "8024 Northgate, Clymer, NY", "city": "Clymer", "state": "NY",
         "price": 250000, "bedrooms": 2, "bathrooms": 2, "sqft": 1227,
         "property_type": "Condo", "url": "", "days_on_market": 21,
         "description": "Slopeside ski-in/ski-out condo at Peek'n Peak. Association/HOA applies."},
    ],
}
