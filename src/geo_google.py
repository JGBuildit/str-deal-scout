"""
geo_google.py
=============
Map checks using Google Maps Platform instead of OpenStreetMap/Overpass (whose
public servers refuse requests from GitHub-hosted runners).

Needs the environment variable GOOGLE_MAPS_API_KEY (a GitHub Actions secret).
The key is only ever sent in a request header - never in a URL, a log line,
an exception message, or a file.

APIs used (enable all in the Google Cloud project that owns the key):
  * Places API (New)  - nearest beach / lake / ski area, and a count of
                        restaurants, bars and cafes within walking range
  * Routes API        - real WALKING distance from the property to the place

The result has the same shape as geo.analyze(), so geo.evaluate_location()
works unchanged. Differences from the OpenStreetMap version:
  * distances are walking meters along the street network, not straight-line
  * "does the walk cross a busy road" is NOT checked (Google does not expose
    road classes) - every listing carries a flag telling you to eyeball it
  * canal frontage cannot be detected, so a 'canal' rule never matches

Cost control: only listings that already clear the cash-flow and deduction
gates reach this module (a handful per week). Each costs roughly 3-8 requests.
"""

import math
import os

import requests

PLACES_TEXT = "https://places.googleapis.com/v1/places:searchText"
PLACES_NEARBY = "https://places.googleapis.com/v1/places:searchNearby"
ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
TIMEOUT = 20
MAX_WALK_CANDIDATES = 3

# signal -> Text Search queries used to find the nearest one. Several phrasings
# because public beach access points are rarely named just "beach".
QUERIES = {
    "beach": ["beach access", "beach"],
    "lake": ["lake"],
    "ski": ["ski lift", "ski resort"],
}


def _geo_error():
    # Imported lazily so this module has no import cycle with geo.py
    from .geo import GeoUnavailable
    return GeoUnavailable


def available():
    return bool(os.environ.get("GOOGLE_MAPS_API_KEY", "").strip())


def _key():
    k = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    if not k:
        raise _geo_error()("GOOGLE_MAPS_API_KEY is not set")
    return k


def _scrub(text, key):
    return (text or "").replace(key, "[key]")


def _post(url, body, field_mask):
    """POST to a Google API. Returns parsed JSON or raises GeoUnavailable."""
    key = _key()
    try:
        r = requests.post(url, json=body, timeout=TIMEOUT,
                          headers={"X-Goog-Api-Key": key,
                                   "X-Goog-FieldMask": field_mask,
                                   "Content-Type": "application/json"})
    except requests.exceptions.Timeout:
        raise _geo_error()("Google API timeout")
    except Exception as e:  # noqa: BLE001
        raise _geo_error()(f"Google API {type(e).__name__}")
    if r.status_code != 200:
        msg = ""
        try:
            msg = r.json().get("error", {}).get("message", "")
        except ValueError:
            msg = r.text
        api = url.split("//", 1)[-1].split("/", 1)[0]
        raise _geo_error()(_scrub(f"{api} HTTP {r.status_code}: {' '.join(msg.split())[:200]}", key))
    try:
        return r.json()
    except ValueError:
        raise _geo_error()("Google API returned invalid JSON")


def haversine_m(lat1, lng1, lat2, lng2):
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2 +
         math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lng2 - lng1) * p / 2) ** 2)
    return 2 * 6371000 * math.asin(math.sqrt(a))


def find_places(query, lat, lng, radius_m):
    """Places matching `query` near the point, nearest first, as
    [{name, lat, lng, types, straight_m}]. Asks Google to rank by DISTANCE (the
    default ranks by relevance, which can bury a closer beach access); if the
    API rejects that option it retries with the default."""
    body = {"textQuery": query, "pageSize": 10, "rankPreference": "DISTANCE",
            "locationBias": {"circle": {"center": {"latitude": lat, "longitude": lng},
                                        "radius": float(min(radius_m, 50000))}}}
    mask = "places.displayName,places.location,places.types"
    try:
        data = _post(PLACES_TEXT, body, mask)
    except _geo_error() as e:
        if "rankPreference" not in str(e) and "HTTP 400" not in str(e):
            raise
        body.pop("rankPreference")
        data = _post(PLACES_TEXT, body, mask)
    out = []
    for p in data.get("places", []):
        loc = p.get("location") or {}
        if "latitude" not in loc:
            continue
        out.append({"name": (p.get("displayName") or {}).get("text", ""),
                    "lat": loc["latitude"], "lng": loc["longitude"],
                    "types": p.get("types", []),
                    "straight_m": haversine_m(lat, lng, loc["latitude"], loc["longitude"])})
    return sorted(out, key=lambda x: x["straight_m"])


def walking_m(lat, lng, dest_lat, dest_lng):
    """Walking distance in meters, or None if Google finds no walking route."""
    body = {"origin": {"location": {"latLng": {"latitude": lat, "longitude": lng}}},
            "destination": {"location": {"latLng": {"latitude": dest_lat, "longitude": dest_lng}}},
            "travelMode": "WALK"}
    data = _post(ROUTES_URL, body, "routes.distanceMeters,routes.duration")
    routes = data.get("routes") or []
    if not routes or "distanceMeters" not in routes[0]:
        return None
    return routes[0]["distanceMeters"]


def count_eateries(lat, lng, radius_m):
    body = {"includedTypes": ["restaurant", "bar", "cafe"], "maxResultCount": 20,
            "locationRestriction": {"circle": {"center": {"latitude": lat, "longitude": lng},
                                               "radius": float(radius_m)}}}
    data = _post(PLACES_NEARBY, body, "places.id")
    return len(data.get("places", []))


def get_geo(lat, lng, rules):
    """Same output shape as geo.get_geo(); see module docstring for the differences."""
    if lat is None or lng is None:
        raise _geo_error()("listing has no coordinates")
    lat, lng = float(lat), float(lng)

    out = {"beach_m": None, "lake_m": None, "canal_m": None, "ski_m": None, "coast_m": None,
           "pois_walkable": 0, "crosses_busy": {}, "crosses_moderate": {},
           "nearest_road_class": None, "fronts_busy_road": False,
           "names": {}, "nearest": {}, "source": "google",
           "crossing_checked": False}

    for rule in rules:
        sig = rule["signal"]
        if sig == "walkable":
            out["pois_walkable"] = count_eateries(lat, lng, rule.get("radius_m", 800))
            continue
        queries = QUERIES.get(sig)
        if not queries or out.get(f"{sig}_m") is not None:
            continue
        reach = rule["max_m"]
        # Look wider than the rule so a near miss is reported rather than invisible.
        found = {}
        for q in queries:
            for p in find_places(q, lat, lng, max(reach * 4, 1500)):
                found[(round(p["lat"], 5), round(p["lng"], 5))] = p
        places = sorted(found.values(), key=lambda x: x["straight_m"])
        if places:
            out["nearest"][sig] = (places[0]["name"], int(places[0]["straight_m"]))
        best = None
        for p in places[:MAX_WALK_CANDIDATES]:
            if p["straight_m"] > reach * 2.5:
                break
            w = walking_m(lat, lng, p["lat"], p["lng"])
            if w is not None and (best is None or w < best[0]):
                best = (w, p["name"])
        if best:
            out[f"{sig}_m"] = int(best[0])
            out["names"][sig] = best[1]
    for sig in ("beach", "lake", "canal", "ski", "coast"):
        out["crosses_busy"][sig] = False
        out["crosses_moderate"][sig] = False
    return out
