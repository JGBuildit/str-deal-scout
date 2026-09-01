"""
score.py
========
Turns a raw listing into a scored, flagged candidate by applying the
due-diligence rubric we built up over the analysis:

  * fee-simple only  (reject leasehold / MWCD cottage-lease patterns)
  * flag condo/HOA/gated  (these often BAN short-term rentals)
  * flag village limits    (verify STR zoning / density caps)
  * reward a deeded dock / waterfront (biggest driver of nightly rate)
  * require the base-case self-managed cap rate to clear MIN_CAP_RATE

Each candidate gets a 0-100 score and a list of human-readable flags.
The agent reports; it does not decide — always verify flags before an offer.
"""

from .config import (LEASEHOLD_KEYWORDS, CONDO_KEYWORDS, DOCK_KEYWORDS,
                     MIN_CAP_RATE)
from .enrich import enrich
from .model import run_model


def _text(listing: dict) -> str:
    return f"{listing.get('property_type','')} {listing.get('description','')}".lower()


def _has(text: str, words) -> bool:
    return any(w in text for w in words)


def score_listing(listing: dict, market: dict) -> dict:
    text = _text(listing)

    is_leasehold = _has(text, LEASEHOLD_KEYWORDS)
    is_condo = _has(text, CONDO_KEYWORDS)
    has_dock = _has(text, DOCK_KEYWORDS)
    in_village = (listing.get("city", "") in market["village_names"])

    enr = enrich(listing, market, has_dock)
    m = run_model(
        price=listing.get("price", 0),
        adr=enr["adr"], occ=enr["occ"],
        bedrooms=listing.get("bedrooms", 3),
        tax_rate=market["tax_rate"],
        is_condo=is_condo,
    )
    if not m:
        return None

    # --- Build flags ---
    flags = []
    if is_leasehold:
        flags.append("LEASEHOLD - land not owned (likely disqualifying)")
    if is_condo:
        flags.append("Condo/HOA/gated - CONFIRM the association permits STR")
    if in_village:
        flags.append("In village limits - verify STR zoning / density cap")
    if has_dock:
        flags.append("Dock/waterfront - confirm dock is DEEDED, not a leased slip")

    cap_self = m["cap_self"]

    # --- Composite score (0-100), transparent and easy to tweak ---
    score = 0.0
    # Cap rate is ~60% of the score: 5% cap -> ~30 pts, 10% cap -> ~60 pts.
    score += min(60, max(0, cap_self * 600))
    if has_dock:
        score += 15
    if not is_condo:
        score += 10
    if not in_village:
        score += 10
    if not is_leasehold:
        score += 5
    score = round(min(100, score))

    # --- Pass/fail gate ---
    passed = (not is_leasehold) and (cap_self >= MIN_CAP_RATE)

    return {
        **listing,
        **m,
        "adr_used": enr["adr"],
        "occ_used": enr["occ"],
        "adr_source": enr["source"],
        "has_dock": has_dock,
        "is_condo": is_condo,
        "is_leasehold": is_leasehold,
        "in_village": in_village,
        "flags": flags,
        "score": score,
        "passed": passed,
        "market": market["label"],
    }
