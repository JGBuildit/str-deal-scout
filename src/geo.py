"""
geo.py
======
Map-based location checks, using OpenStreetMap data via the Overpass API.

For a listing's coordinates it measures (straight-line, meters):
  * beach_m  - nearest mapped beach
  * lake_m   - nearest named lake / reservoir
  * canal_m  - nearest canal (waterfront on a canal)
  * ski_m    - nearest ski lift or downhill piste
  * coast_m  - nearest coastline (any shore, incl. bays)
and counts restaurants / bars / cafes within walking range.

It also checks the *walk*: whether a busy road (motorway / trunk / primary,
e.g. US-98) lies between the property and the feature, and whether the
property itself fronts a busy road. A 1-block walk on a quiet street passes;
a walk that has to cross US-98 does not.

Straight-line distance is used (not a routed walk) because it is stable,
free and testable. Real walking distance is typically ~1.2-1.3x longer.

If the map service cannot be reached, `get_geo` raises GeoUnavailable and the
caller reports the location as UNVERIFIED rather than guessing.
"""

import hashlib
import json
import math
import os
import time

import requests

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
CACHE_DIR = os.environ.get("GEO_CACHE_DIR", ".geo_cache")
USER_AGENT = "str-deal-scout/1.0 (personal property screening)"

BUSY = {"motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link"}
MODERATE = {"secondary", "secondary_link"}
AMENITY_POIS = "restaurant|bar|pub|cafe|ice_cream|biergarten"
LIFTS = "chair_lift|gondola|cable_car|mixed_lift|t-bar|j-bar|platter|drag_lift|magic_carpet|rope_tow"

_M_LAT = 110540.0
_M_LNG = 111320.0


class GeoUnavailable(Exception):
    """The map service could not be used (disabled, offline or rate-limited)."""


# ---------------------------------------------------------------------------
# Geometry (all in meters, relative to the property at the origin)
# ---------------------------------------------------------------------------
def _xy(lat0, lng0, lat, lng):
    return ((lng - lng0) * math.cos(math.radians(lat0)) * _M_LNG,
            (lat - lat0) * _M_LAT)


def _seg_nearest(a, b):
    """Nearest point to the origin on segment a-b -> (distance, point)."""
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    t = 0.0 if denom == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / denom))
    qx, qy = ax + t * dx, ay + t * dy
    return math.hypot(qx, qy), (qx, qy)


def _orient(p, q, r):
    return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])


def _segments_cross(p1, p2, p3, p4):
    d1, d2 = _orient(p3, p4, p1), _orient(p3, p4, p2)
    d3, d4 = _orient(p1, p2, p3), _orient(p1, p2, p4)
    return (d1 * d2 < 0) and (d3 * d4 < 0)


def _polylines(el, lat0, lng0):
    """All polylines of an Overpass element (a way, or a relation's members)."""
    lines = []
    geom = el.get("geometry")
    if geom:
        lines.append([_xy(lat0, lng0, g["lat"], g["lon"]) for g in geom])
    for m in el.get("members") or []:
        g = m.get("geometry")
        if g:
            lines.append([_xy(lat0, lng0, p["lat"], p["lon"]) for p in g])
    return lines


def _nearest(polylines):
    """Nearest (distance, point) over a list of polylines; (None, None) if empty."""
    best_d, best_p = None, None
    for pl in polylines:
        if len(pl) == 1:
            d, p = math.hypot(*pl[0]), pl[0]
            cand = [(d, p)]
        else:
            cand = [_seg_nearest(a, b) for a, b in zip(pl, pl[1:])]
        for d, p in cand:
            if best_d is None or d < best_d:
                best_d, best_p = d, p
    return best_d, best_p


def _crosses(target, road_lines):
    """Does the straight walk from the origin to `target` cross any road line?"""
    if target is None:
        return False
    o = (0.0, 0.0)
    for pl in road_lines:
        for a, b in zip(pl, pl[1:]):
            if _segments_cross(o, target, a, b):
                return True
    return False


# ---------------------------------------------------------------------------
# Analysis of Overpass results
# ---------------------------------------------------------------------------
def analyze(lat, lng, elements, ski_elements=None, poi_radius=800):
    """Turn raw Overpass elements into the distances / flags described above."""
    kinds = {"beach": [], "coast": [], "lake": [], "canal": [], "ski": []}
    busy_lines, moderate_lines = [], []
    road_candidates = []  # (class, polylines) of roads near the property
    pois = 0

    for el in elements or []:
        tags = el.get("tags") or {}
        if el.get("type") == "node":
            if "lat" in el and tags.get("amenity") and tags["amenity"] in AMENITY_POIS.split("|"):
                x, y = _xy(lat, lng, el["lat"], el["lon"])
                if math.hypot(x, y) <= poi_radius:
                    pois += 1
            continue
        lines = _polylines(el, lat, lng)
        if not lines:
            continue
        if tags.get("natural") == "beach":
            kinds["beach"].extend(lines)
        elif tags.get("natural") == "coastline":
            kinds["coast"].extend(lines)
        elif tags.get("natural") == "water" and tags.get("water") == "canal":
            kinds["canal"].extend(lines)
        elif tags.get("natural") == "water" and tags.get("name"):
            kinds["lake"].extend(lines)
        elif tags.get("waterway") == "canal":
            kinds["canal"].extend(lines)
        hw = tags.get("highway")
        if hw:
            road_candidates.append((hw, lines))
            if hw in BUSY:
                busy_lines.extend(lines)
            elif hw in MODERATE:
                moderate_lines.extend(lines)

    for el in ski_elements or []:
        tags = el.get("tags") or {}
        if tags.get("aerialway") or tags.get("piste:type") == "downhill":
            kinds["ski"].extend(_polylines(el, lat, lng))

    out = {"pois_walkable": pois, "crosses_busy": {}, "crosses_moderate": {}}
    for name, lines in kinds.items():
        d, p = _nearest(lines)
        out[f"{name}_m"] = None if d is None else round(d)
        out["crosses_busy"][name] = _crosses(p, busy_lines)
        out["crosses_moderate"][name] = _crosses(p, moderate_lines)

    # The road the property sits on: the nearest road of any class.
    nearest_cls, nearest_d = None, None
    for cls, lines in road_candidates:
        d, _ = _nearest(lines)
        if d is not None and (nearest_d is None or d < nearest_d):
            nearest_cls, nearest_d = cls, d
    out["nearest_road_class"] = nearest_cls
    out["fronts_busy_road"] = bool(nearest_cls in BUSY and nearest_d is not None and nearest_d <= 40)
    return out


def evaluate_location(geo, rules):
    """
    Apply a market's location rules to an analyze() result.
    Returns {"ok": bool, "matched": [...], "notes": [...]}. A rule passes when
    its feature is within max_m and (unless allowed) no busy road is crossed.
    """
    matched, notes = [], []
    for rule in rules:
        sig = rule["signal"]
        if sig == "walkable":
            if geo["pois_walkable"] >= rule["min_pois"]:
                matched.append(f"walkable ({geo['pois_walkable']} eateries/bars within {rule.get('radius_m', 800)} m)")
            continue
        d = geo.get(f"{sig}_m")
        if d is None or d > rule["max_m"]:
            continue
        if geo["crosses_busy"].get(sig) and not rule.get("allow_busy_crossing", False):
            notes.append(f"{sig} is {d} m away but the walk crosses a busy road")
            continue
        label = {"beach": "beach", "lake": "lake", "canal": "canal frontage",
                 "ski": "ski lift/run"}[sig]
        tier = "adjacent" if d <= 60 else ("~1 block" if d <= 200 else "short walk")
        matched.append(f"{label} {d} m ({tier})")
        if geo["crosses_moderate"].get(sig):
            notes.append(f"walk to {label} crosses a secondary road")
    if geo.get("fronts_busy_road"):
        notes.append("property fronts a busy road (noise/safety)")
    return {"ok": bool(matched), "matched": matched, "notes": notes}


# ---------------------------------------------------------------------------
# Overpass access
# ---------------------------------------------------------------------------
def _near_query(lat, lng, radius, poi_radius):
    return f"""[out:json][timeout:45];
(
  way(around:{radius},{lat},{lng})[natural=beach];
  way(around:{radius},{lat},{lng})[natural=coastline];
  way(around:{radius},{lat},{lng})[natural=water][name];
  rel(around:{radius},{lat},{lng})[natural=water][name];
  way(around:{radius},{lat},{lng})[natural=water][water=canal];
  way(around:{radius},{lat},{lng})[waterway=canal];
  way(around:{radius},{lat},{lng})[highway~"^(motorway|motorway_link|trunk|trunk_link|primary|primary_link|secondary|secondary_link)$"];
  way(around:60,{lat},{lng})[highway];
  node(around:{poi_radius},{lat},{lng})[amenity~"^({AMENITY_POIS})$"];
);
out geom tags;"""


def _ski_query(lat, lng, radius):
    return f"""[out:json][timeout:45];
(
  way(around:{radius},{lat},{lng})[aerialway~"^({LIFTS})$"];
  way(around:{radius},{lat},{lng})["piste:type"="downhill"];
);
out geom tags;"""


def _run(query):
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, hashlib.sha1(query.encode()).hexdigest() + ".json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    last = None
    for url in OVERPASS_URLS:
        try:
            r = requests.post(url, data={"data": query}, timeout=70,
                              headers={"User-Agent": USER_AGENT})
            r.raise_for_status()
            data = r.json().get("elements", [])
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            time.sleep(1.0)  # be polite to the free public service
            return data
        except Exception as e:  # noqa: BLE001
            last = e
    raise GeoUnavailable(str(last))


def get_geo(lat, lng, rules):
    """Fetch map data for one listing and return the analysis dict."""
    if os.environ.get("GEO_PROVIDER", "").lower() == "off":
        raise GeoUnavailable("map lookups disabled (GEO_PROVIDER=off)")
    if lat is None or lng is None:
        raise GeoUnavailable("listing has no coordinates")
    lat, lng = round(float(lat), 5), round(float(lng), 5)

    max_m = max([r.get("max_m", 0) for r in rules] + [300])
    poi_radius = max([r.get("radius_m", 0) for r in rules if r["signal"] == "walkable"] + [800])
    near_radius = int(max(1000, max_m * 2))
    elements = _run(_near_query(lat, lng, near_radius, poi_radius))

    ski_elements = None
    ski_rules = [r for r in rules if r["signal"] == "ski"]
    if ski_rules:
        ski_elements = _run(_ski_query(lat, lng, int(max(r["max_m"] for r in ski_rules) * 3)))
    return analyze(lat, lng, elements, ski_elements, poi_radius)
