"""
digest.py
=========
Formats the week's scored candidates into a readable Markdown digest that
becomes the body of the weekly GitHub Issue (and a file in /digests).
"""

from datetime import date


def _money(n):
    try:
        return f"${n:,.0f}"
    except (TypeError, ValueError):
        return "-"


def _pct(n):
    try:
        return f"{n*100:.1f}%"
    except (TypeError, ValueError):
        return "-"


def build_digest(candidates: list, mode: str) -> str:
    today = date.today().isoformat()
    passed = [c for c in candidates if c["passed"]]
    flagged = [c for c in candidates if not c["passed"]]
    passed.sort(key=lambda c: c["score"], reverse=True)
    flagged.sort(key=lambda c: c["score"], reverse=True)

    lines = []
    lines.append(f"# STR Deal Scout - weekly digest ({today})")
    lines.append("")
    if mode == "demo":
        lines.append("> **DEMO MODE** - showing built-in sample listings. "
                     "Add a `RENTCAST_API_KEY` secret for live data.")
        lines.append("")
    lines.append(f"Scanned 4 lakes. **{len(passed)} candidate(s) passed** the "
                 f"filters; {len(flagged)} flagged for review.")
    lines.append("")
    lines.append("_The agent reports; it does not decide. Verify every flag - "
                 "leasehold, zoning, dock ownership, HOA STR rules - before an offer._")
    lines.append("")

    if passed:
        lines.append("## Candidates that passed")
        lines.append("")
        lines.append("| Score | Property | Market | Price | Gross | Cap (self) | Cap (pro) | Notes |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for c in passed:
            note = "; ".join(c["flags"]) or "-"
            lines.append(
                f"| {c['score']} | {c['address']} ({c['bedrooms']}bd) | {c['market']} | "
                f"{_money(c['price'])} | {_money(c['gross_revenue'])} | "
                f"{_pct(c['cap_self'])} | {_pct(c['cap_pro'])} | {note} |"
            )
        lines.append("")

    if flagged:
        lines.append("## Flagged / did not pass")
        lines.append("")
        lines.append("| Score | Property | Market | Price | Cap (self) | Why |")
        lines.append("|---|---|---|---|---|---|")
        for c in flagged:
            why = "; ".join(c["flags"]) or f"cap {_pct(c['cap_self'])} below threshold"
            lines.append(
                f"| {c['score']} | {c['address']} | {c['market']} | "
                f"{_money(c['price'])} | {_pct(c['cap_self'])} | {why} |"
            )
        lines.append("")

    if not candidates:
        lines.append("_No listings returned this week._")

    lines.append("---")
    lines.append("_Assumptions and thresholds live in `src/config.py`. "
                 "ADR/occupancy are market estimates unless an AirDNA key is set._")
    return "\n".join(lines)
