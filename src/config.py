"""
config.py
=========
All the knobs you might want to change live here. Edit the numbers,
save the file, commit — the agent picks up the changes on its next run.

Each MARKET describes one place to scan - a lake, a beach peninsula, a ski
town - where to search, what short-term-rental (STR) performance to assume,
and which words in a listing should raise a red flag. The revenue/occupancy
numbers are market-level estimates; if you add an AirDNA API key later they
get replaced with live address-level data automatically. Markets added
without hands-on local research are flagged in their "notes" - verify ADR/
occ against AirDNA/Rabbu comps before underwriting off them.
"""

# ---------------------------------------------------------------------------
# GLOBAL UNDERWRITING ASSUMPTIONS  (used by the cap-rate model in model.py)
# ---------------------------------------------------------------------------
ASSUMPTIONS = {
    "insurance_rate": 0.0055,      # STR + liability, as % of purchase price
    "insurance_floor": 1800,       # minimum annual premium ($)
    "maintenance_pct": 0.08,       # repairs/supplies/hot-tub, as % of gross revenue
    "platform_pct": 0.04,          # Airbnb/Vrbo host fee + software, as % of gross
    "management_pct": 0.22,        # professional management, as % of gross (self-managed = 0)
    "days_per_year": 365,
    # A "dedicated, well-run" listing earns roughly the market RevPAR.
    # Set this below 1.0 to underwrite more conservatively (e.g. 0.85).
    "operation_factor": 1.00,
}

# Only surface deals whose BASE-CASE self-managed cap rate clears this bar.
MIN_CAP_RATE = 0.05           # 5.0%

# ---------------------------------------------------------------------------
# THE MARKETS
# ---------------------------------------------------------------------------
# lat/lng/radius_miles define the RentCast search circle.
# adr / occ are market STR assumptions (fallback when no AirDNA key).
# tax_rate is the effective property-tax rate for that state/county.
# village_names: if a listing's city matches, flag it to VERIFY zoning /
#                village STR caps before assuming it's rentable (also used
#                for Breckenridge's STR-license cap, not just NY/OH villages).
# require_waterfront: defaults to True (see EXCLUSION RULES below). Set False
#                only for a market where waterfront isn't the value driver -
#                currently just Breckenridge, a ski town.
MARKETS = [
    {
        "key": "lake_milton",
        "label": "Lake Milton, OH",
        "state": "OH",
        "lat": 41.0995, "lng": -80.9704, "radius_miles": 3.5,
        "adr": 215, "occ": 0.57, "tax_rate": 0.016,
        "village_names": ["Craig Beach"],
        "notes": "ODNR state-park lake, private deeded lakefront. No-hp watersports lake.",
    },
    {
        "key": "berlin_reservoir",
        "label": "Berlin Reservoir, OH",
        "state": "OH",
        "lat": 41.0030, "lng": -81.0090, "radius_miles": 6.0,
        "adr": 200, "occ": 0.50, "tax_rate": 0.016,
        "village_names": [],
        "notes": "Army Corps lake, private deeded lakefront in spots. Thin STR data - occ is an estimate.",
    },
    {
        "key": "bemus_point",
        "label": "Bemus Point, NY (Chautauqua Lake)",
        "state": "NY",
        "lat": 42.1614, "lng": -79.3928, "radius_miles": 4.0,
        "adr": 250, "occ": 0.45, "tax_rate": 0.024,
        "village_names": ["Bemus Point", "Lakewood", "Celoron", "Mayville"],
        "notes": "Fee-simple. Summer-weighted. Village of Bemus Point requires rental agreement on file.",
    },
    {
        "key": "findley_lake",
        "label": "Findley Lake / Peek'n Peak, NY",
        "state": "NY",
        "lat": 42.1192, "lng": -79.7325, "radius_miles": 6.0,
        "adr": 204, "occ": 0.30, "tax_rate": 0.024,
        "village_names": [],
        "notes": "Fee-simple, two-season (ski + lake). Confirm condo/resort rental-program rules at Peek'n Peak.",
    },
    # -- Added without the hands-on comp research behind the four lakes above.
    # ADR/occ are directional placeholders - pull real AirDNA/Rabbu comps
    # before underwriting anything here.
    {
        "key": "cape_san_blas",
        "label": "Cape San Blas, FL",
        "state": "FL",
        "lat": 29.6636, "lng": -85.3556, "radius_miles": 5.0,
        "adr": 290, "occ": 0.52, "tax_rate": 0.008,
        "village_names": [],
        "notes": "Gulf-front beach market, unincorporated Gulf County. UNVERIFIED ADR/occ estimate. "
                 "Hurricane wind/flood insurance here will likely blow past the global insurance_rate/"
                 "insurance_floor assumptions in model.py - get a real quote before underwriting.",
    },
    {
        "key": "st_joe_peninsula",
        "label": "St. Joseph Peninsula, FL",
        "state": "FL",
        "lat": 29.7553, "lng": -85.3956, "radius_miles": 8.0,
        "adr": 250, "occ": 0.48, "tax_rate": 0.008,
        "village_names": [],
        "notes": "Peninsula north of Cape San Blas (overlapping search area), bay-side + gulf-side mix. "
                 "UNVERIFIED ADR/occ estimate. Same wind/flood insurance caveat as Cape San Blas.",
    },
    {
        "key": "alligator_point",
        "label": "Alligator Point, FL",
        "state": "FL",
        "lat": 29.9050, "lng": -84.4170, "radius_miles": 4.0,
        "adr": 220, "occ": 0.42, "tax_rate": 0.008,
        "village_names": [],
        "notes": "Quieter Franklin County gulf-front community, less premium than Cape San Blas. "
                 "UNVERIFIED ADR/occ estimate. Same wind/flood insurance caveat as Cape San Blas.",
    },
    {
        "key": "breckenridge",
        "label": "Breckenridge, CO",
        "state": "CO",
        "lat": 39.5097, "lng": -106.0400, "radius_miles": 6.0,
        "adr": 380, "occ": 0.55, "tax_rate": 0.005,
        "village_names": ["Breckenridge"],
        "require_waterfront": False,  # ski town, not a waterfront market (see main.py's _exclusion_reason)
        "notes": "Ski-town market, exempted from the waterfront-only filter (see require_waterfront). "
                 "Its real gating factor is STR licensing, not water: Breckenridge caps new STR licenses "
                 "by neighborhood/type (1/2/3); CONFIRM a license is actually obtainable before assuming "
                 "any STR income. UNVERIFIED ADR/occ.",
    },
    {
        "key": "norris_lake",
        "label": "Norris Lake, TN",
        "state": "TN",
        "lat": 36.2927, "lng": -83.9109, "radius_miles": 12.0,
        "adr": 260, "occ": 0.45, "tax_rate": 0.006,
        "village_names": [],
        "notes": "Large TVA reservoir spanning Union/Campbell/Claiborne counties - wide search radius "
                 "to cover multiple marinas/coves. TVA (not Army Corps) shoreline rules apply; docks "
                 "often need a TVA permit. UNVERIFIED ADR/occ estimate.",
    },
]

# ---------------------------------------------------------------------------
# EXCLUSION RULES  (listings filtered out before scoring - logged to the
# dashboard's "Excluded" tab instead of showing up as a candidate)
# ---------------------------------------------------------------------------
# Matched against the listing's property type (substring, case-insensitive).
# There's no structure to underwrite an STR on land, and mobile homes are
# rarely financeable/insurable the way this model assumes.
EXCLUDE_PROPERTY_TYPES = ["land", "mobile"]

# Below this price a listing in our markets is almost never a real
# fee-simple home - usually a land parcel, teardown, or data error.
MIN_PRICE = 100_000

# Only lakefront/waterfront listings move forward - it's the single biggest
# driver of nightly rate, and the whole point of these markets. Matched
# against DOCK_KEYWORDS below (property type + description).

# ---------------------------------------------------------------------------
# RED-FLAG KEYWORDS  (scanned in the listing type + description)
# ---------------------------------------------------------------------------
# Leasehold = you don't own the land (deal-killer for STR income). Includes
# the Muskingum Watershed (MWCD) cottage-lease pattern we ruled out earlier.
LEASEHOLD_KEYWORDS = [
    "leasehold", "land lease", "leased land", "cottage site", "mwcd",
    "muskingum", "ground lease", "lease land", "land is leased",
]
# Condo / HOA / gated communities frequently BAN short-term rentals.
CONDO_KEYWORDS = [
    "condo", "condominium", "hoa", "association fee", "gated", "poa",
    "homeowners association",
]
# A deeded dock/waterfront is the single biggest driver of nightly rate.
# Includes gulf/ocean-front phrasing for the FL beach markets, not just lake
# terms - otherwise genuine beachfront listings get wrongly excluded by the
# waterfront-only filter in main.py for not saying "waterfront" specifically.
DOCK_KEYWORDS = [
    "dock", "boat slip", "boat lift", "waterfront", "lakefront",
    "lake front", "water frontage", "private beach", "shoreline",
    "beachfront", "beach front", "gulf front", "gulffront",
    "oceanfront", "ocean front", "bayfront", "bay front", "river front",
    "riverfront",
]
