"""
geo_check.py
============
Diagnostics for the map service. Run in the weekly workflow (and by hand) to
record, for each public Overpass server, whether it answers from the machine
running the job, how fast, and with what error. Writes digests/geo_diagnostics.txt
so the result is visible in the repo even when Actions logs are not.

    python -m src.geo_check
"""

import os
import time
from datetime import datetime, timezone

from . import geo

# Rosemary Beach, FL (30A) - a point with beach, roads and restaurants nearby.
LAT, LNG = 30.2737, -86.0179


def google_section(lines):
    from . import geo_google
    if not geo_google.available():
        lines.append("Google Maps: GOOGLE_MAPS_API_KEY not set - skipped")
        return False
    ok = True
    steps = [
        ("Places text search (beach access)", lambda: geo_google.find_places("beach access", LAT, LNG, 1500)),
        ("Places nearby (eateries)", lambda: geo_google.count_eateries(LAT, LNG, 800)),
        ("Routes walking", lambda: geo_google.walking_m(LAT, LNG, LAT - 0.002, LNG)),
    ]
    for name, fn in steps:
        try:
            res = fn()
            detail = ("; ".join(f"{r['name']!r} {r['straight_m']:.0f} m" for r in res[:3])
                      if isinstance(res, list) and res else res)
            lines.append(f"  Google {name}: ok ({detail})")
        except geo.GeoUnavailable as e:
            ok = False
            lines.append(f"  Google {name}: FAIL {e}")
    # Raw (unfiltered) results with their Google place types, so the type
    # whitelist can be built from evidence rather than guesses.
    lines.append("  Raw beach results near Grayton Beach (30.3226,-86.1645), with types:")
    try:
        for q in ("beach access", "beach"):
            raw = geo_google._post(geo_google.PLACES_TEXT,
                {"textQuery": q, "pageSize": 10, "rankPreference": "DISTANCE",
                 "locationBias": {"circle": {"center": {"latitude": 30.3226, "longitude": -86.1645},
                                             "radius": 1500.0}}},
                "places.displayName,places.types")
            for p in raw.get("places", []):
                lines.append(f"    [{q}] {(p.get('displayName') or {}).get('text', '')!r}: {','.join(p.get('types', []))}")
        for q, lat, lng in (("lake", 44.9100, -116.0990), ("ski lift", 37.7000, -112.8450)):
            raw = geo_google._post(geo_google.PLACES_TEXT,
                {"textQuery": q, "pageSize": 6, "rankPreference": "DISTANCE",
                 "locationBias": {"circle": {"center": {"latitude": lat, "longitude": lng}, "radius": 3000.0}}},
                "places.displayName,places.types")
            for p in raw.get("places", []):
                lines.append(f"    [{q}] {(p.get('displayName') or {}).get('text', '')!r}: {','.join(p.get('types', []))}")
    except geo.GeoUnavailable as e:
        lines.append(f"    raw lookup FAILED: {e}")
    try:
        g = geo_google.get_geo(LAT, LNG, [{"signal": "beach", "max_m": 300},
                                          {"signal": "walkable", "min_pois": 8, "radius_m": 800}])
        lines.append(f"  Google END-TO-END: beach {g['beach_m']} m {g['names'].get('beach', '')!r}, "
                     f"eateries {g['pois_walkable']}")
    except geo.GeoUnavailable as e:
        ok = False
        lines.append(f"  Google END-TO-END FAILED: {e}")
    return ok


def main():
    lines = [f"Map service check {datetime.now(timezone.utc).isoformat(timespec='seconds')}Z"]
    if google_section(lines):
        text = "\n".join(lines)
        print(text)
        os.makedirs("digests", exist_ok=True)
        with open(os.path.join("digests", "geo_diagnostics.txt"), "w", encoding="utf-8") as f:
            f.write(text + "\n")
        return  # Google works; skip probing the Overpass servers
    tiny = "[out:json][timeout:10];node(30.2737,-86.0179,30.2738,-86.0178);out;"
    tests = [("tiny", tiny),
             ("water", geo._water_query(LAT, LNG, 1000)),
             ("roads", geo._road_query(LAT, LNG, 1000)),
             ("eateries", geo._poi_query(LAT, LNG, 800))]
    lines.append("User-Agent comparison on overpass-api.de (tiny query):")
    for label, ua in (("old UA", geo.OLD_USER_AGENT), ("new UA", geo.USER_AGENT)):
        d, e = geo._post(geo.OVERPASS_URLS[0], tiny, timeout=30, user_agent=ua)
        lines.append(f"  {label}: " + (e if e else f"ok ({len(d)} elements)"))
    for url in geo.OVERPASS_URLS:
        for name, q in tests:
            t0 = time.time()
            data, err = geo._post(url, q, timeout=30)
            dt = time.time() - t0
            if err:
                lines.append(f"  {geo._host(url):32s} {name:8s} FAIL  {err}")
            else:
                lines.append(f"  {geo._host(url):32s} {name:8s} ok    {len(data):4d} elements in {dt:.1f}s")
    # End-to-end on the real code path, with a throwaway cache.
    geo.reset_breaker()
    geo.CACHE_DIR = os.path.join(".geo_cache", "diag")
    try:
        g = geo.get_geo(LAT, LNG, [{"signal": "beach", "max_m": 300},
                                   {"signal": "walkable", "min_pois": 8, "radius_m": 800}])
        lines.append(f"END-TO-END ok: beach {g['beach_m']} m, eateries {g['pois_walkable']}, "
                     f"road {g['nearest_road_class']}")
    except geo.GeoUnavailable as e:
        lines.append(f"END-TO-END FAILED: {e}")
    text = "\n".join(lines)
    print(text)
    os.makedirs("digests", exist_ok=True)
    with open(os.path.join("digests", "geo_diagnostics.txt"), "w", encoding="utf-8") as f:
        f.write(text + "\n")


if __name__ == "__main__":
    main()
