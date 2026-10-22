"""
main.py
=======
Orchestrates one weekly run:
  1. For each lake, fetch active listings (live RentCast or demo data).
  2. Drop listings that are land / mobile / under $100k / not waterfront,
     before scoring.
  3. Score + flag each remaining listing against the rubric.
  4. Build a Markdown digest and an interactive HTML dashboard, and write
     them to /digests.
  5. Print the digest path so the GitHub Action can turn it into an Issue.

Run locally with:  python -m src.main
"""

import os
from datetime import date

from .config import MARKETS, EXCLUDE_PROPERTY_TYPES, MIN_PRICE, DOCK_KEYWORDS
from .acq_config import ACQ_MARKETS
from . import acq, airdna
from .acq_digest import build_acq_digest
from .sources import fetch_listings
from .score import score_listing
from .digest import build_digest
from .dashboard import build_dashboard_html


def _exclusion_reason(listing: dict) -> str:
    """Why a listing should be dropped before scoring, or "" to keep it."""
    property_type = (listing.get("property_type") or "").lower()
    text = f"{property_type} {listing.get('description', '')}".lower()
    price = listing.get("price") or 0

    reasons = []
    if any(kw in property_type for kw in EXCLUDE_PROPERTY_TYPES):
        reasons.append(f"property type: {listing.get('property_type')}")
    if price < MIN_PRICE:
        reasons.append(f"price under ${MIN_PRICE:,.0f}")
    if not any(kw in text for kw in DOCK_KEYWORDS):
        reasons.append("not waterfront")
    return "; ".join(reasons)


def _profiles() -> set:
    """Which profiles to run. Default: both. Set STR_PROFILES=acq or legacy."""
    raw = os.environ.get("STR_PROFILES", "acq,legacy")
    return {p.strip().lower() for p in raw.split(",") if p.strip()}


def run() -> str:
    profiles = _profiles()
    all_candidates = []
    excluded_listings = []
    overall_mode = "live"
    lake_candidates, acq_candidates = [], []
    acq_mode = "live"

    if "legacy" in profiles:
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
                    lake_candidates.append(scored)

    if "acq" in profiles:
        airdna_data = airdna.load()
        print(f"AirDNA files: {len(airdna_data['market'])} market row(s), "
              f"{len(airdna_data['property'])} property row(s)")
        for market in ACQ_MARKETS:
            print(f"Scanning {market['label']} ...")
            listings, mode = fetch_listings(market)
            if mode == "demo":
                acq_mode = "demo"
            print(f"  {len(listings)} listing(s) [{mode}]")
            for listing in listings:
                reason = acq.exclusion_reason(listing)
                if reason:
                    excluded_listings.append({**listing, "market": market["label"],
                                              "reason": reason})
                    continue
                # Map lookups only on live data (demo coordinates are made up).
                scored = acq.score_acq(listing, market, airdna_data, use_geo=(mode == "live"))
                if scored:
                    acq_candidates.append(scored)
        if acq_mode == "demo":
            overall_mode = "demo"

    all_candidates = acq_candidates + lake_candidates

    parts = []
    if "acq" in profiles:
        parts.append(build_acq_digest(acq_candidates, acq_mode, len(ACQ_MARKETS)))
    if "legacy" in profiles:
        parts.append(build_digest(lake_candidates, overall_mode if "legacy" in profiles else acq_mode))
    digest_md = "\n\n---\n\n".join(parts)

    os.makedirs("digests", exist_ok=True)
    dated_path = os.path.join("digests", f"{date.today().isoformat()}.md")
    latest_path = os.path.join("digests", "latest.md")
    for path in (dated_path, latest_path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(digest_md)

    dashboard_html = build_dashboard_html(all_candidates, excluded_listings, overall_mode)
    dated_html = os.path.join("digests", f"{date.today().isoformat()}.html")
    latest_html = os.path.join("digests", "latest.html")
    for path in (dated_html, latest_html):
        with open(path, "w", encoding="utf-8") as f:
            f.write(dashboard_html)

    print(f"\nWrote digest -> {dated_path}")

    # Expose values to the GitHub Action via the step-output file.
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        passed = sum(1 for c in all_candidates if c["passed"])
        strict = sum(1 for c in acq_candidates if c["status"] == "PASS")
        with open(gh_out, "a", encoding="utf-8") as f:
            f.write(f"digest_path={dated_path}\n")
            f.write(f"passed_count={passed}\n")
            f.write(f"issue_title=STR Deal Scout - {date.today().isoformat()} "
                    f"({passed} candidate(s), {strict} AirDNA-confirmed)\n")

    return dated_path


if __name__ == "__main__":
    run()
