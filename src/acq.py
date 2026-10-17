"""
acq.py
======
The acquisition screen: for one listing in one ACQ market, decide whether it
is likely to (1) be cash-flow positive after debt service, (2) produce roughly
the target year-1 deduction, and (3) sit in a verified desirable location.

Order of work (cheapest first, so the map is only queried for listings that
already clear the money gates):
  amenities -> revenue basis -> financial model -> deduction -> map location

Status values:
  PASS         every gate cleared, revenue backed by AirDNA data
  PROVISIONAL  every gate cleared, but revenue is only an ESTIMATE
  NEEDS_MAP    money gates cleared, map lookup unavailable - check location
  FAIL         at least one hard gate failed (reasons are in `flags`)
"""

import re

from . import airdna
from .acq_config import (ACQ, FINANCING, DEPRECIATION, OPERATING,
                         LEASEHOLD_KEYWORDS, CONDO_KEYWORDS, EXCLUDE_PROPERTY_TYPES)
from .geo import get_geo, evaluate_location, GeoUnavailable
from .model import estimate_utilities


# ---------------------------------------------------------------------------
# Pre-filter
# ---------------------------------------------------------------------------
def exclusion_reason(listing):
    """Why a listing is dropped before scoring, or "" to keep it."""
    ptype = (listing.get("property_type") or "").lower()
    price = listing.get("price") or 0
    reasons = []
    if any(k in ptype for k in EXCLUDE_PROPERTY_TYPES):
        reasons.append(f"property type: {listing.get('property_type')}")
    if price < ACQ["min_price"]:
        reasons.append(f"price under ${ACQ['min_price']:,.0f}")
    if ACQ["max_price"] and price > ACQ["max_price"]:
        reasons.append(f"price over ${ACQ['max_price']:,.0f}")
    if (listing.get("bedrooms") or 0) < ACQ["min_bedrooms"]:
        reasons.append(f"under {ACQ['min_bedrooms']} bedrooms")
    if (listing.get("bathrooms") or 0) < ACQ["min_bathrooms"]:
        reasons.append(f"under {ACQ['min_bathrooms']} bathrooms")
    return "; ".join(reasons)


# ---------------------------------------------------------------------------
# Amenities
# ---------------------------------------------------------------------------
def detect_amenities(listing):
    text = f"{listing.get('property_type', '')} {listing.get('description', '')}".lower()
    for junk in ("pool table", "pool room", "pool hall", "poolside bar"):
        text = text.replace(junk, " ")
    feat = listing.get("features") or {}

    has_pool = bool(re.search(r"\bpool\b|swimming pool", text)) or bool(feat.get("pool"))
    shared_only = (bool(re.search(r"(community|shared|neighborhood|resort|association|complex|common)\W+(\w+\W+)?pool", text))
                   and not re.search(r"private\W+(\w+\W+)?pool|own pool|heated pool", text)
                   and not feat.get("pool"))
    hot_tub = bool(re.search(r"hot ?tub|jacuzzi|private spa|whirlpool tub outside", text))
    sauna = "sauna" in text
    return {"pool": has_pool and not shared_only,
            "shared_pool_only": has_pool and shared_only,
            "hot_tub": hot_tub, "sauna": sauna}


def _preference_met(market, am):
    pref = market.get("amenity_preference")
    if pref == "pool":
        return am["pool"]
    if pref == "hot_tub_or_sauna":
        return am["hot_tub"] or am["sauna"]
    return False


# ---------------------------------------------------------------------------
# Revenue basis
# ---------------------------------------------------------------------------
def revenue_basis(listing, market, am, airdna_data):
    beds = listing.get("bedrooms") or 3
    found = airdna.lookup(airdna_data, market["key"], listing.get("address", ""),
                          beds, am["pool"], am["hot_tub"] or am["sauna"])
    days = OPERATING["days_per_year"]
    if found:
        if found.get("annual_revenue"):
            gross = found["annual_revenue"]
            adr = found.get("adr") or 0
            occ = found.get("occ") or 0
        else:
            adr, occ = found["adr"], found["occ"]
            gross = adr * occ * days
        return {"gross": gross, "adr": adr, "occ": occ,
                "source": found["source"], "date": found.get("date", "")}

    bucket = min(max(int(beds), 3), 6)
    adr, occ = market["rev"][bucket]
    if am["pool"] and market.get("amenity_preference") == "pool":
        adr *= 1 + OPERATING["pool_adr_premium"]
    if (am["hot_tub"] or am["sauna"]) and market.get("amenity_preference") == "hot_tub_or_sauna":
        adr *= 1 + OPERATING["spa_adr_premium"]
    return {"gross": adr * occ * days, "adr": round(adr), "occ": occ,
            "source": "estimate", "date": ""}


# ---------------------------------------------------------------------------
# Financial model
# ---------------------------------------------------------------------------
def _annual_debt_service(price):
    loan = price * (1 - FINANCING["down_pct"])
    r = FINANCING["rate"] / 12
    n = FINANCING["term_years"] * 12
    pmt = loan * r / (1 - (1 + r) ** -n) if r else loan / n
    return loan, pmt * 12


def financials(listing, market, am, rev, is_condo):
    price = float(listing.get("price") or 0)
    beds = listing.get("bedrooms") or 3
    gross = rev["gross"]

    hoa_fee = listing.get("hoa_fee")
    hoa = hoa_fee * 12 if hoa_fee else (OPERATING["hoa_default"] if is_condo else 0)

    property_tax = price * market["tax_rate"]
    insurance = max(price * market["insurance_rate"], market.get("insurance_floor", 2500))
    utilities = estimate_utilities(beds)
    maintenance = gross * OPERATING["maintenance_pct"]
    platform = gross * OPERATING["platform_pct"]
    amenity_opex = (OPERATING["pool_opex"] if am["pool"] else 0) \
        + (OPERATING["hot_tub_opex"] if am["hot_tub"] else 0) \
        + (OPERATING["sauna_opex"] if am["sauna"] else 0)

    opex_self = property_tax + insurance + utilities + maintenance + platform + hoa + amenity_opex
    noi_self = gross - opex_self
    mgmt = gross * OPERATING["management_pct"]
    noi_pro = noi_self - mgmt

    loan, debt_service = _annual_debt_service(price)
    ffe = DEPRECIATION["furnish_base"] + DEPRECIATION["furnish_per_bedroom"] * beds
    cash_invested = price * (FINANCING["down_pct"] + FINANCING["closing_pct"]) + ffe

    cf_self = noi_self - debt_service
    cf_pro = noi_pro - debt_service
    basis = cf_pro if ACQ["cash_flow_basis"] == "pro" else cf_self

    # --- Year-1 deduction: cost seg + 100% bonus on short-life property,
    #     100% bonus on furnishings, 39-yr straight line on the remainder.
    building = price * (1 - market["land_pct"])
    cs_pct = DEPRECIATION["cost_seg_pct"]
    if am["pool"]:
        cs_pct += DEPRECIATION["pool_extra_pct"]
    if am["hot_tub"] or am["sauna"]:
        cs_pct += DEPRECIATION["spa_extra_pct"]
    short_life = building * cs_pct
    remainder = (building - short_life) / 39 * DEPRECIATION["year1_fraction"]
    deduction = (short_life + ffe) * DEPRECIATION["bonus_pct"] + remainder

    return {
        "gross_revenue": round(gross), "property_tax": round(property_tax),
        "insurance": round(insurance), "utilities": round(utilities),
        "maintenance": round(maintenance), "platform": round(platform),
        "hoa": round(hoa), "amenity_opex": round(amenity_opex),
        "opex_self": round(opex_self), "noi_self": round(noi_self),
        "noi_pro": round(noi_pro), "cap_self": round(noi_self / price, 4),
        "cap_pro": round(noi_pro / price, 4),
        "loan": round(loan), "debt_service": round(debt_service),
        "cash_flow_self": round(cf_self), "cash_flow_pro": round(cf_pro),
        "cash_flow": round(basis), "cash_invested": round(cash_invested),
        "cash_on_cash": round(basis / cash_invested, 4),
        "year1_deduction": round(deduction), "furnishings": round(ffe),
    }


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------
def score_acq(listing, market, airdna_data, use_geo=True):
    text = f"{listing.get('property_type', '')} {listing.get('description', '')}".lower()
    is_leasehold = any(k in text for k in LEASEHOLD_KEYWORDS)
    is_condo = any(k in text for k in CONDO_KEYWORDS)
    am = detect_amenities(listing)
    pref_met = _preference_met(market, am)

    rev = revenue_basis(listing, market, am, airdna_data)
    price = float(listing.get("price") or 0)
    if price <= 0:
        return None
    fin = financials(listing, market, am, rev, is_condo)

    flags, fails = [], []
    if market.get("tenure_note"):
        flags.append(market["tenure_note"])
    if is_leasehold:
        fails.append("LEASEHOLD - land not owned")
    if is_condo:
        flags.append("Condo/HOA/townhome - CONFIRM the association permits nightly STR")
    if am["shared_pool_only"]:
        flags.append("Pool appears to be shared/community, not private")
    if rev["source"] == "estimate":
        flags.append("Revenue is an ESTIMATE - add AirDNA data to confirm")
    if listing.get("hoa_fee") is None and is_condo:
        flags.append(f"HOA dues unknown - ${OPERATING['hoa_default']:,}/yr placeholder used")

    min_cf = ACQ["min_cash_flow"]
    if fin["cash_flow"] < min_cf:
        fails.append(f"cash flow ${fin['cash_flow']:,}/yr after debt service")
    ded_floor = ACQ["target_year1_deduction"] * ACQ["deduction_tolerance"]
    if fin["year1_deduction"] < ded_floor:
        fails.append(f"year-1 deduction ${fin['year1_deduction']:,} below ${ded_floor:,.0f}")
    if ACQ["require_preferred_amenity"] and not pref_met:
        fails.append(f"missing preferred amenity ({market.get('amenity_preference')})")

    # --- Map check, only for listings that cleared the money gates ---
    location = {"ok": None, "matched": [], "notes": [], "checked": False}
    geo = None
    if not fails and use_geo:
        try:
            geo = get_geo(listing.get("lat"), listing.get("lng"), market["location_rules"])
            ev = evaluate_location(geo, market["location_rules"])
            location = {**ev, "checked": True}
            if not ev["ok"]:
                fails.append("location: nothing in range on the map" +
                             (f" ({'; '.join(ev['notes'])})" if ev["notes"] else ""))
        except GeoUnavailable as e:
            flags.append(f"Location UNVERIFIED - map lookup unavailable ({e})")
    elif not fails and not use_geo:
        flags.append("Location not checked (demo mode)")
    for n in location["notes"]:
        flags.append(n)

    if fails:
        status = "FAIL"
    elif location["ok"] is None:
        status = "NEEDS_MAP"
    elif rev["source"] == "estimate":
        status = "PROVISIONAL"
    else:
        status = "PASS"

    # --- Score (0-100) ---
    score = 0.0
    score += min(35, max(0, fin["cash_on_cash"] / 0.08 * 35))
    score += min(25, fin["year1_deduction"] / ACQ["target_year1_deduction"] * 25)
    if location["ok"]:
        best = min([geo.get(f"{s}_m") for s in ("beach", "lake", "canal", "ski")
                    if geo and geo.get(f"{s}_m") is not None] or [9999])
        score += 25 if best <= 200 else 20
    elif location["ok"] is None and not fails:
        score += 10
    if pref_met:
        score += 8
    if (listing.get("bedrooms") or 0) >= ACQ["preferred_bedrooms"]:
        score += 7
    score = round(min(100, score))

    return {
        **listing, **fin,
        "status": status,
        "passed": status in ("PASS", "PROVISIONAL"),
        "fails": fails, "flags": fails + flags,
        "score": score, "market": market["label"], "market_key": market["key"],
        "str_note": market.get("str_note", ""),
        "adr_used": rev["adr"], "occ_used": rev["occ"], "adr_source": rev["source"],
        "has_pool": am["pool"], "has_hot_tub": am["hot_tub"], "has_sauna": am["sauna"],
        "preferred_amenity": pref_met, "is_condo": is_condo, "is_leasehold": is_leasehold,
        "location_ok": location["ok"], "location": "; ".join(location["matched"]),
        "geo": geo,
    }
