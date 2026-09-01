"""
main.py
=======
Orchestrates one weekly run:
  1. For each lake, fetch active listings (live RentCast or demo data).
  2. Score + flag each listing against the rubric.
  3. Build a Markdown digest and write it to /digests.
  4. Print the digest path so the GitHub Action can turn it into an Issue.

Run locally with:  python -m src.main
"""

import os
from datetime import date

from .config import MARKETS
from .sources import fetch_listings
from .score import score_listing
from .digest import build_digest


def run() -> str:
    all_candidates = []
    overall_mode = "live"

    for market in MARKETS:
        print(f"Scanning {market['label']} ...")
        listings, mode = fetch_listings(market)
        if mode == "demo":
            overall_mode = "demo"
        print(f"  {len(listings)} listing(s) [{mode}]")
        for listing in listings:
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
