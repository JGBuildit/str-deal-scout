"""
airdna.py
=========
Loads revenue data you export from your AirDNA subscription (no API needed).

Two optional CSV files live in data/airdna/ (headers are already there):

  market_stats.csv   - one row per market x bedroom count, from AirDNA's
                       market view filtered by bedrooms (and pool / hot tub
                       if you want amenity-specific numbers).
      market_key,bedrooms,adr,occupancy,pool,hot_tub,source_date,notes
      scenic_30a,4,640,0.51,y,,2026-10-17,Market Minder 4BR w/ pool

  rentalizer.csv     - address-level results you get by running AirDNA's
                       Rentalizer on a shortlisted property. Overrides the
                       market row for that address.
      address,annual_revenue,adr,occupancy,source_date,notes
      123 Gulf Dr Santa Rosa Beach FL,142000,,,2026-10-17,Rentalizer

Values are forgiving: "$640", "51%", "0.51" and "51" all parse.
Leave pool / hot_tub blank for a row that applies to any home.
"""

import csv
import os
import re

DEFAULT_DIR = os.environ.get("AIRDNA_DIR", "data/airdna")


def _num(v):
    if v is None:
        return None
    s = str(v).strip().replace("$", "").replace(",", "")
    if not s:
        return None
    pct = s.endswith("%")
    s = s.rstrip("%")
    try:
        x = float(s)
    except ValueError:
        return None
    return x / 100 if pct else x


def _occ(v):
    x = _num(v)
    if x is None:
        return None
    return x / 100 if x > 1.5 else x


def _flag(v):
    s = (str(v or "")).strip().lower()
    if s in ("y", "yes", "true", "1", "x"):
        return True
    if s in ("n", "no", "false", "0"):
        return False
    return None  # blank = applies to any


def _read(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = []
        for r in csv.DictReader(f):
            rows.append({(k or "").strip().lower(): (v or "").strip() for k, v in r.items()})
        return rows


def addr_key(address):
    """Normalise an address so '123 Gulf Dr.' and '123 gulf dr' match."""
    return re.sub(r"[^a-z0-9]", "", (address or "").lower())


def load(directory=None):
    d = directory or DEFAULT_DIR
    market = []
    for r in _read(os.path.join(d, "market_stats.csv")):
        adr, occ = _num(r.get("adr")), _occ(r.get("occupancy"))
        beds = _num(r.get("bedrooms"))
        if not r.get("market_key") or adr is None or occ is None or beds is None:
            continue
        market.append({"market_key": r["market_key"], "bedrooms": int(beds),
                       "adr": adr, "occ": occ,
                       "pool": _flag(r.get("pool")), "hot_tub": _flag(r.get("hot_tub")),
                       "date": r.get("source_date", "")})
    prop = {}
    for r in _read(os.path.join(d, "rentalizer.csv")):
        rev, adr, occ = _num(r.get("annual_revenue")), _num(r.get("adr")), _occ(r.get("occupancy"))
        if not r.get("address") or (rev is None and (adr is None or occ is None)):
            continue
        prop[addr_key(r["address"])] = {"annual_revenue": rev, "adr": adr, "occ": occ,
                                        "date": r.get("source_date", "")}
    return {"market": market, "property": prop}


def lookup(data, market_key, address, bedrooms, has_pool, has_hot_tub):
    """
    Best available revenue basis for a listing, most specific first:
      property (Rentalizer) -> market row matching bedrooms+amenities
      -> market row matching bedrooms -> None.
    Returns {"annual_revenue"?, "adr", "occ", "source", "date"} or None.
    """
    p = data["property"].get(addr_key(address))
    if p:
        out = {"source": "airdna-property", "date": p["date"],
               "annual_revenue": p["annual_revenue"], "adr": p["adr"], "occ": p["occ"]}
        return out

    rows = [r for r in data["market"] if r["market_key"] == market_key]
    if not rows:
        return None
    bucket = min(max(int(bedrooms or 3), 3), 6)

    def beds_ok(r):
        return min(max(r["bedrooms"], 3), 6) == bucket

    def amen_score(r):
        # exact amenity match beats generic row; a row for the wrong amenity is out
        s = 0
        for want, have in ((r["pool"], has_pool), (r["hot_tub"], has_hot_tub)):
            if want is None:
                continue
            if want != have:
                return -1
            s += 1
        return s

    best, best_s = None, -1
    for r in rows:
        if not beds_ok(r):
            continue
        s = amen_score(r)
        if s > best_s:
            best, best_s = r, s
    if best is None:
        return None
    return {"source": "airdna-market", "date": best["date"], "adr": best["adr"],
            "occ": best["occ"], "annual_revenue": None,
            "amenity_matched": best_s > 0}
