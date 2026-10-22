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
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
]
CACHE_DIR = os.environ.get("GEO_CACHE_DIR", ".geo_cache")
USER_AGENT = "str-deal-scout/1.0 (+https://github.com/JGBuildit/str-deal-scout; personal property screening)"
OLD_USER_AGENT = "str-deal-scout/1.0 (personal property screening)"  # kept only for geo_check comparison

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
        name = (geo.get("names") or {}).get(sig)
        matched.append(f"{label} {d} m ({tier})" + (f" [{name}]" if name else ""))
        if geo["crosses_moderate"].get(sig):
            notes.append(f"walk to {label} crosses a secondary road")
    if geo.get("fronts_busy_road"):
        notes.append("property fronts a busy road (noise/safety)")
    if geo.get("source") == "google" and matched:
        notes.append("walk is by Google route; whether it crosses a busy road is NOT checked - view on a map")
    return {"ok": bool(matched), "matched": matched, "notes": notes}


# ---------------------------------------------------------------------------
# Overpass access
# ---------------------------------------------------------------------------
def _clip(lat, lng, radius):
    """Bounding box (south,west,north,east) used to clip returned geometry.

    Without clipping, Overpass sends the FULL outline of every matching
    feature - for the Gulf coastline or a large bay that is huge and slow.
    """
    dlat = radius / _M_LAT
    dlng = radius / (_M_LNG * math.cos(math.radians(lat)))
    return f"{lat - dlat:.5f},{lng - dlng:.5f},{lat + dlat:.5f},{lng + dlng:.5f}"


def _water_query(lat, lng, radius):
    clip = _clip(lat, lng, radius)
    return f"""[out:json][timeout:25];
(
  way(around:{radius},{lat},{lng})[natural=beach];
  way(around:{radius},{lat},{lng})[natural=coastline];
  way(around:{radius},{lat},{lng})[natural=water][name];
  rel(around:{radius},{lat},{lng})[natural=water][name];
  way(around:{radius},{lat},{lng})[natural=water][water=canal];
  way(around:{radius},{lat},{lng})[waterway=canal];
);
out geom({clip}) tags;"""


def _road_query(lat, lng, radius):
    clip = _clip(lat, lng, radius)
    return f"""[out:json][timeout:25];
(
  way(around:{radius},{lat},{lng})[highway~"^(motorway|motorway_link|trunk|trunk_link|primary|primary_link|secondary|secondary_link)$"];
  way(around:60,{lat},{lng})[highway];
);
out geom({clip}) tags;"""


def _poi_query(lat, lng, poi_radius):
    return f"""[out:json][timeout:25];
node(around:{poi_radius},{lat},{lng})[amenity~"^({AMENITY_POIS})$"];
out body;"""


def _ski_query(lat, lng, radius):
    clip = _clip(lat, lng, radius)
    return f"""[out:json][timeout:25];
(
  way(around:{radius},{lat},{lng})[aerialway~"^({LIFTS})$"];
  way(around:{radius},{lat},{lng})["piste:type"="downhill"];
);
out geom({clip}) tags;"""


def _host(url):
    return url.split("//", 1)[-1].split("/", 1)[0]


def _post(url, query, timeout, user_agent=None):
    """One request to one server. Returns (elements, None) or (None, short_error)."""
    t0 = time.time()
    try:
        r = requests.post(url, data={"data": query}, timeout=timeout,
                          headers={"User-Agent": user_agent or USER_AGENT})
        dt = time.time() - t0
        if r.status_code != 200:
            body = " ".join(r.text.split())[:60]
            return None, f"{_host(url)} HTTP {r.status_code} in {dt:.0f}s {body}"
        try:
            return r.json().get("elements", []), None
        except ValueError:
            return None, f"{_host(url)} bad JSON in {dt:.0f}s {' '.join(r.text.split())[:60]}"
    except requests.exceptions.Timeout:
        return None, f"{_host(url)} timeout after {time.time() - t0:.0f}s"
    except Exception as e:  # noqa: BLE001
        return None, f"{_host(url)} {type(e).__name__}"


# Circuit breaker: a server that fails FAIL_LIMIT times in one run is skipped for
# the rest of the run, so a dead service costs minutes, not hours. When every
# server is skipped, lookups fail instantly with the recorded reasons.
FAIL_LIMIT = 2
_FAILS = {}
_LAST_ERR = {}


def reset_breaker():
    _FAILS.clear()
    _LAST_ERR.clear()


def _run(query):
    """Run a query against each live server in turn; cache successes."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, hashlib.sha1(query.encode()).hexdigest() + ".json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    errors = []
    for attempt in range(2):
        live = [u for u in OVERPASS_URLS if _FAILS.get(u, 0) < FAIL_LIMIT]
        if not live:
            break
        for url in live:
            data, err = _post(url, query, timeout=30)
            if data is not None:
                _FAILS[url] = 0
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                time.sleep(1.0)  # be polite to the free public services
                return data
            _FAILS[url] = _FAILS.get(url, 0) + 1
            _LAST_ERR[url] = err
            errors.append(err)
        if attempt == 0 and all(_FAILS.get(u, 0) >= FAIL_LIMIT for u in OVERPASS_URLS):
            break
        time.sleep(3)
    if not errors:  # every server already tripped earlier in this run
        errors = [_LAST_ERR[u] for u in OVERPASS_URLS if u in _LAST_ERR]
    # De-duplicate while keeping order, and keep the message short for the digest.
    seen = []
    for e in errors:
        if e not in seen:
            seen.append(e)
    raise GeoUnavailable(" | ".join(seen)[:400])


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

    elements = []
    elements += _run(_water_query(lat, lng, near_radius))
    elements += _run(_road_query(lat, lng, near_radius))
    if any(r["signal"] == "walkable" for r in rules):
        elements += _run(_poi_query(lat, lng, poi_radius))

    ski_elements = None
    ski_rules = [r for r in rules if r["signal"] == "ski"]
    if ski_rules:
        ski_elements = _run(_ski_query(lat, lng, int(max(r["max_m"] for r in ski_rules) * 3)))
    return analyze(lat, lng, elements, ski_elements, poi_radius)
