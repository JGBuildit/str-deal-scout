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


def main():
    lines = [f"Map service check {datetime.now(timezone.utc).isoformat(timespec='seconds')}Z"]
    tiny = "[out:json][timeout:10];node(30.2737,-86.0179,30.2738,-86.0178);out;"
    tests = [("tiny", tiny),
             ("water", geo._water_query(LAT, LNG, 1000)),
             ("roads", geo._road_query(LAT, LNG, 1000)),
             ("eateries", geo._poi_query(LAT, LNG, 800))]
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
    os.environ["GEO_CACHE_DIR"] = ""
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
