"""
main.py
=======
Orchestrates one weekly run:
  1. For each lake, fetch active listings (live RentCast or demo data).
  2. Drop listings that are land / mobile / under $100k before scoring.
  3. Score + flag each remaining listing against the rubric.
  4. Build a Markdown digest and an Excel workbook and write them to /digests.
  5. Print the digest path so the GitHub Action can turn it into an Issue.

Run locally with:  python -m src.main
"""

import os
from datetime import date

from openpyxl import Workbook

from .config import MARKETS, EXCLUDE_PROPERTY_TYPES, MIN_PRICE
from .sources import fetch_listings
from .score import score_listing
from .digest import build_digest


def _exclusion_reason(listing: dict) -> str:
    """Why a listing should be dropped before scoring, or "" to keep it."""
    property_type = (listing.get("property_type") or "").lower()
    price = listing.get("price") or 0

    reasons = []
    if any(kw in property_type for kw in EXCLUDE_PROPERTY_TYPES):
        reasons.append(f"property type: {listing.get('property_type')}")
    if price < MIN_PRICE:
        reasons.append(f"price under ${MIN_PRICE:,.0f}")
    return "; ".join(reasons)


def _write_excel(candidates: list, excluded: list, path: str) -> None:
    """Write the week's results to an Excel workbook: a "Candidates" sheet
    with every scored listing, and an "Excluded" sheet listing what got
    filtered out for being land/mobile or under $100k."""
    wb = Workbook()

    ws = wb.active
    ws.title = "Candidates"
    ws.append(["Score", "Passed", "Address", "Market", "Price", "Bedrooms",
               "Gross Revenue", "Cap (self)", "Cap (pro)", "Flags"])
    for c in sorted(candidates, key=lambda c: c["score"], reverse=True):
        ws.append([
            c["score"], c["passed"], c["address"], c["market"], c["price"],
            c["bedrooms"], c["gross_revenue"], c["cap_self"], c["cap_pro"],
            "; ".join(c["flags"]),
        ])

    excluded_ws = wb.create_sheet("Excluded")
    excluded_ws.append(["Address", "Market", "Price", "Property Type", "Reason"])
    for e in excluded:
        excluded_ws.append([e["address"], e["market"], e["price"],
                             e["property_type"], e["reason"]])

    wb.save(path)


def run() -> str:
    all_candidates = []
    excluded_listings = []
    overall_mode = "live"

    for market in MARKETS:
        print(f"Scanning {market['label']} ...")
        listings, mode = fetch_listings(market)
        if mode == "demo":
            overall_mode = "demo"
        print(f"  {len(listings)} listing(s) [{mode}]")
        for listing in listings:
            reason = _exclusion_reason(listing)
            if reason:
                excluded_listings.append({
                    **listing,
                    "market": market["label"],
                    "reason": reason,
                })
                continue
            scored = score_listing(listing, market)
            if scored:
                all_candidates.append(scored)

    digest_md = build_digest(all_candidates, overall_mode)

    os.makedirs("digests", exist_ok=True)
    dated_path = os.path.join("digests", f"{date.today().isoformat()}.md")
    latest_path = os.path.join("digests", "latest.md")
    for path in (dated_path, latest_path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(digest_md)

    dated_xlsx = os.path.join("digests", f"{date.today().isoformat()}.xlsx")
    latest_xlsx = os.path.join("digests", "latest.xlsx")
    for path in (dated_xlsx, latest_xlsx):
        _write_excel(all_candidates, excluded_listings, path)

    print(f"\nWrote digest -> {dated_path}")

    # Expose values to the GitHub Action via the step-output file.
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        passed = sum(1 for c in all_candidates if c["passed"])
        with open(gh_out, "a", encoding="utf-8") as f:
            f.write(f"digest_path={dated_path}\n")
            f.write(f"passed_count={passed}\n")
            f.write(f"issue_title=STR Deal Scout - {date.today().isoformat()} "
                    f"({passed} candidate(s))\n")

    return dated_path


if __name__ == "__main__":
    run()
