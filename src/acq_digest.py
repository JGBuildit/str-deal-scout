"""
acq_digest.py
=============
Markdown digest for the acquisition profile (cash flow + year-1 deduction +
map-verified location). Sorted so the closest-to-qualifying deals are first.
"""

from datetime import date

_ORDER = {"PASS": 0, "PROVISIONAL": 1, "NEEDS_MAP": 2, "FAIL": 3}


def _m(n):
    try:
        return f"${n:,.0f}"
    except (TypeError, ValueError):
        return "-"


def _p(n):
    try:
        return f"{n * 100:.1f}%"
    except (TypeError, ValueError):
        return "-"


def _amen(c):
    bits = [n for n, k in (("pool", "has_pool"), ("hot tub", "has_hot_tub"), ("sauna", "has_sauna")) if c.get(k)]
    return ", ".join(bits) or "-"


def build_acq_digest(cands, mode, markets_count):
    cands = sorted(cands, key=lambda c: (_ORDER[c["status"]], -c["score"]))
    counts = {k: sum(1 for c in cands if c["status"] == k) for k in _ORDER}
    L = [f"# STR Acquisition Screen - {date.today().isoformat()}", ""]
    if mode == "demo":
        L += ["> **DEMO MODE** - built-in sample listings, map checks skipped. "
              "Add a `RENTCAST_API_KEY` secret for live data.", ""]
    L.append(f"Scanned {markets_count} markets, {len(cands)} listings scored. "
             f"**{counts['PASS']} PASS** (AirDNA-backed), **{counts['PROVISIONAL']} PROVISIONAL** "
             f"(revenue still an estimate), {counts['NEEDS_MAP']} need a map check, "
             f"{counts['FAIL']} failed a gate.")
    L += ["", "_Gates: cash flow after debt service, modeled year-1 deduction near target, "
          "and a feature verified on the map (beach / lake / canal / ski / walkable). "
          "PASS needs revenue from your AirDNA files in `data/airdna/`. "
          "Rates, taxes, insurance and the deduction model are estimates - verify before an offer._", ""]

    keep = [c for c in cands if c["status"] != "FAIL"]
    if keep:
        L += ["## Worth a closer look", "",
              "| Score | Status | Property | Market | Price | Bd/Ba | Amenities | Location (map) | Gross | Cash flow | CoC | Yr-1 deduction |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for c in keep:
            L.append(f"| {c['score']} | {c['status']} | {c['address']} | {c['market']} | {_m(c['price'])} | "
                     f"{c['bedrooms']}/{c['bathrooms']} | {_amen(c)} | {c['location'] or '-'} | "
                     f"{_m(c['gross_revenue'])} | {_m(c['cash_flow'])} | {_p(c['cash_on_cash'])} | "
                     f"{_m(c['year1_deduction'])} |")
        L.append("")
        L += ["### Flags to verify on the shortlist", ""]
        for c in keep:
            fl = [f for f in c["flags"] if "ESTIMATE" not in f]
            L.append(f"- **{c['address']}** - " + ("; ".join(fl) if fl else "none") +
                     (f". STR rules: {c['str_note']}" if c.get("str_note") else ""))
        L.append("")

    failed = [c for c in cands if c["status"] == "FAIL"]
    if failed:
        L += ["## Did not qualify (closest first)", "",
              "| Score | Property | Market | Price | Cash flow | Yr-1 deduction | Why |",
              "|---|---|---|---|---|---|---|"]
        for c in failed[:40]:
            L.append(f"| {c['score']} | {c['address']} | {c['market']} | {_m(c['price'])} | "
                     f"{_m(c['cash_flow'])} | {_m(c['year1_deduction'])} | {'; '.join(c['fails'])} |")
        if len(failed) > 40:
            L.append(f"\n_...and {len(failed) - 40} more (see the dashboard)._")
        L.append("")
    if not cands:
        L.append("_No listings returned this week._")
    return "\n".join(L)
