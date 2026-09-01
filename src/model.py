"""
model.py
========
The revenue-and-cap-rate model, ported from the Lake Milton Excel workbook.

Given a purchase price plus an assumed nightly rate (ADR) and occupancy, it
returns gross revenue, operating expenses, NOI, and cap rates for both a
self-managed and a professionally-managed scenario.
"""

from .config import ASSUMPTIONS


def estimate_utilities(bedrooms: int) -> float:
    """Rough annual utilities (heat/AC/water/internet/hot-tub) scaled by size."""
    bedrooms = bedrooms or 3
    return 3500 + max(0, bedrooms - 2) * 550


def run_model(price: float, adr: float, occ: float, bedrooms: int,
              tax_rate: float, is_condo: bool = False) -> dict:
    """Return a dict of revenue + cap-rate outputs for one property."""
    a = ASSUMPTIONS
    price = float(price or 0)
    if price <= 0:
        return {}

    # --- Revenue ---
    gross = adr * occ * a["days_per_year"] * a["operation_factor"]

    # --- Operating expenses ---
    property_tax = price * tax_rate
    insurance = max(price * a["insurance_rate"], a["insurance_floor"])
    utilities = estimate_utilities(bedrooms)
    maintenance = gross * a["maintenance_pct"]
    platform = gross * a["platform_pct"]
    # Condos carry an HOA; we can't see the real dues, so assume a placeholder.
    hoa = 4800 if is_condo else 0

    opex_self = property_tax + insurance + utilities + maintenance + platform + hoa
    noi_self = gross - opex_self
    cap_self = noi_self / price

    mgmt_fee = gross * a["management_pct"]
    noi_pro = noi_self - mgmt_fee
    cap_pro = noi_pro / price

    return {
        "gross_revenue": round(gross),
        "property_tax": round(property_tax),
        "insurance": round(insurance),
        "utilities": round(utilities),
        "maintenance": round(maintenance),
        "platform": round(platform),
        "hoa": round(hoa),
        "opex_self": round(opex_self),
        "noi_self": round(noi_self),
        "cap_self": round(cap_self, 4),
        "noi_pro": round(noi_pro),
        "cap_pro": round(cap_pro, 4),
    }
