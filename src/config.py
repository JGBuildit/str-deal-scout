"""
config.py
=========
All the knobs you might want to change live here. Edit the numbers,
save the file, commit — the agent picks up the changes on its next run.

Each MARKET describes one lake: where to search, what short-term-rental
(STR) performance to assume, and which words in a listing should raise a
red flag. The revenue/occupancy numbers are the market-level estimates we
researched; if you add an AirDNA API key later they get replaced with live
address-level data automatically.
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
# THE FOUR LAKES
# ---------------------------------------------------------------------------
# lat/lng/radius_miles define the RentCast search circle.
# adr / occ are market STR assumptions (fallback when no AirDNA key).
# tax_rate is the effective property-tax rate for that state/county.
# village_names: if a listing's city matches, flag it to VERIFY zoning /
#                village STR caps before assuming it's rentable.
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
]

# ---------------------------------------------------------------------------
# EXCLUSION RULES  (listings filtered out before scoring - logged to the
# Excel export's "Excluded" sheet instead of showing up as a candidate)
# ---------------------------------------------------------------------------
# Matched against the listing's property type (substring, case-insensitive).
# There's no structure to underwrite an STR on land, and mobile homes are
# rarely financeable/insurable the way this model assumes.
EXCLUDE_PROPERTY_TYPES = ["land", "mobile"]

# Below this price a listing in our markets is almost never a real
# fee-simple home - usually a land parcel, teardown, or data error.
MIN_PRICE = 100_000

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
DOCK_KEYWORDS = [
    "dock", "boat slip", "boat lift", "waterfront", "lakefront",
    "lake front", "water frontage", "private beach", "shoreline",
]
