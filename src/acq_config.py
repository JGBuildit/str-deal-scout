"""
acq_config.py
=============
Settings for the *acquisition* profile: Gulf Coast (Gulf Shores AL ->
Alligator Point FL), Marco Island FL, McCall ID, Brian Head UT.

This profile screens for a different goal than the original lake profile:
a unit that is cash-flow positive AND produces a large year-1 tax deduction
(cost segregation + 100% bonus depreciation), in a desirable location that is
verified on a MAP rather than by keywords in the listing text.

IMPORTANT - every number marked "estimate" below is a starting guess, not data:
  * revenue (ADR / occupancy)  -> replace with AirDNA exports (data/airdna/)
  * tax / insurance rates      -> replace with a quote or county lookup
Listings that clear every gate using only estimated revenue are reported as
PROVISIONAL, never PASS. PASS requires AirDNA-backed revenue.
"""

# ---------------------------------------------------------------------------
# WHAT A LISTING MUST LOOK LIKE
# ---------------------------------------------------------------------------
ACQ = {
    "min_bedrooms": 3,
    "min_bathrooms": 2,
    "preferred_bedrooms": 4,          # bonus in the score, not a gate
    "min_price": 250_000,
    "max_price": None,                # e.g. 1_500_000 - set your ceiling
    # Year-1 deduction target. A listing passes the deduction gate when its
    # modeled deduction >= target * tolerance ("roughly 250k").
    "target_year1_deduction": 250_000,
    "deduction_tolerance": 0.90,
    "min_cash_flow": 0,               # annual $, after debt service
    # Which cash flow gates the pass: "pro" (professionally managed - the
    # conservative case for an out-of-state owner) or "self".
    "cash_flow_basis": "pro",
    # Preferred amenity (pool on the coast, hot tub/sauna in the mountains)
    # raises the score. Set True to make it a hard requirement.
    "require_preferred_amenity": False,
}

# ---------------------------------------------------------------------------
# FINANCING  (edit to your real terms)
# ---------------------------------------------------------------------------
FINANCING = {
    "down_pct": 0.20,
    "rate": 0.0725,                   # estimate - second-home / DSCR rate
    "term_years": 30,
    "closing_pct": 0.03,
}

# ---------------------------------------------------------------------------
# DEPRECIATION / YEAR-1 DEDUCTION MODEL  (estimates - confirm with your CPA
# and a real cost segregation study)
# ---------------------------------------------------------------------------
DEPRECIATION = {
    "cost_seg_pct": 0.25,             # share of building basis reclassed to 5/7/15-yr
    "pool_extra_pct": 0.04,           # added when a private pool is detected
    "spa_extra_pct": 0.02,            # added for hot tub / sauna
    "furnish_base": 15_000,           # furnishings & setup, fixed part
    "furnish_per_bedroom": 9_000,     # furnishings & setup, per bedroom
    "year1_fraction": 0.90,           # share of a year the property is in service
    "bonus_pct": 1.00,                # 100% bonus depreciation
}

# ---------------------------------------------------------------------------
# OPERATING ASSUMPTIONS (shared)
# ---------------------------------------------------------------------------
OPERATING = {
    "maintenance_pct": 0.08,
    "platform_pct": 0.04,
    "management_pct": 0.22,
    "days_per_year": 365,
    "hoa_default": 4800,              # used only when the listing shows no HOA fee
    # Extra annual running cost of each amenity
    "pool_opex": 4800,
    "hot_tub_opex": 1800,
    "sauna_opex": 600,
    # Used only when revenue is an ESTIMATE (AirDNA rows already reflect amenities)
    "pool_adr_premium": 0.08,
    "spa_adr_premium": 0.06,
}

# ---------------------------------------------------------------------------
# MAP-BASED LOCATION RULES
# ---------------------------------------------------------------------------
# A listing is "location OK" if ANY rule in its market passes. Distances are
# straight-line meters from the property to the feature, measured on
# OpenStreetMap data; a crossing of a busy road (US-98 etc.) between the
# property and the feature disqualifies that rule unless allow_busy_crossing.
#   300 m ~ a 2-3 block walk. Tighten to 150 for a strict 1-block rule.
BEACH_RULE = {"signal": "beach", "max_m": 300}

# ---------------------------------------------------------------------------
# MARKETS
# ---------------------------------------------------------------------------
# rev: {bedrooms: (ADR $, occupancy)}  -  ESTIMATES until AirDNA files exist.
# Bedrooms of 6+ use the 6 row; fewer than 3 are filtered out before this.
# tenure_note: shown as a flag on every candidate in that market.
# str_note: rules to confirm before an offer (I have not verified these).

_FL_PANHANDLE_COASTAL = dict(
    profile="acq", kind="coastal", state="FL",
    tax_rate=0.011, insurance_rate=0.012, insurance_floor=4500, land_pct=0.35,
    location_rules=[BEACH_RULE],
    amenity_preference="pool",
)

ACQ_MARKETS = [
    {**_FL_PANHANDLE_COASTAL, "key": "gulf_shores_orange_beach",
     "label": "Gulf Shores / Orange Beach, AL", "state": "AL",
     "lat": 30.268, "lng": -87.640, "radius_miles": 8,
     "tax_rate": 0.007, "insurance_rate": 0.010,
     "rev": {3: (330, .50), 4: (420, .50), 5: (520, .48), 6: (620, .46)},
     "str_note": "Confirm city STR licensing and lodging tax registration (Gulf Shores, Orange Beach, unincorporated Baldwin Co. differ)."},

    {**_FL_PANHANDLE_COASTAL, "key": "perdido_key",
     "label": "Perdido Key, FL", "lat": 30.290, "lng": -87.450, "radius_miles": 4,
     "rev": {3: (320, .50), 4: (410, .49), 5: (500, .47), 6: (590, .45)},
     "str_note": "Escambia County: confirm registration / any condo-association STR limits."},

    {**_FL_PANHANDLE_COASTAL, "key": "pensacola_beach",
     "label": "Pensacola Beach, FL", "lat": 30.335, "lng": -87.140, "radius_miles": 5,
     "rev": {3: (330, .50), 4: (430, .49), 5: (520, .47), 6: (610, .45)},
     "tenure_note": "Pensacola Beach lots are commonly LEASEHOLD (Santa Rosa Island Authority) - confirm the land is fee simple.",
     "str_note": "Confirm lease terms and STR rules with the Santa Rosa Island Authority."},

    {**_FL_PANHANDLE_COASTAL, "key": "navarre_beach",
     "label": "Navarre Beach, FL", "lat": 30.380, "lng": -86.865, "radius_miles": 5,
     "rev": {3: (320, .50), 4: (420, .49), 5: (510, .47), 6: (600, .45)},
     "tenure_note": "Navarre Beach lots are commonly LEASEHOLD (county-owned land) - confirm the land is fee simple.",
     "str_note": "Confirm Santa Rosa County registration and lease terms."},

    {**_FL_PANHANDLE_COASTAL, "key": "destin_okaloosa",
     "label": "Destin / Fort Walton / Okaloosa Island, FL", "lat": 30.388, "lng": -86.530, "radius_miles": 6,
     "rev": {3: (380, .52), 4: (500, .50), 5: (620, .48), 6: (740, .46)},
     "str_note": "Confirm city/county registration; many condo associations restrict rentals."},

    {**_FL_PANHANDLE_COASTAL, "key": "miramar_sandestin",
     "label": "Miramar Beach / Sandestin, FL", "lat": 30.376, "lng": -86.350, "radius_miles": 5,
     "rev": {3: (400, .52), 4: (540, .50), 5: (680, .48), 6: (800, .46)},
     "str_note": "Walton County: confirm registration; Sandestin has association rules."},

    {**_FL_PANHANDLE_COASTAL, "key": "scenic_30a",
     "label": "30A (Dune Allen to Inlet Beach), FL", "lat": 30.322, "lng": -86.100, "radius_miles": 7,
     "land_pct": 0.45, "insurance_rate": 0.013,
     "location_rules": [BEACH_RULE,
                        {"signal": "walkable", "min_pois": 8, "radius_m": 800}],
     "rev": {3: (450, .52), 4: (620, .50), 5: (780, .48), 6: (930, .46)},
     "str_note": "Walton County: confirm registration; many 30A communities (HOAs, Seaside/Alys-style) restrict or regulate rentals."},

    {**_FL_PANHANDLE_COASTAL, "key": "panama_city_beach",
     "label": "Panama City Beach, FL", "lat": 30.178, "lng": -85.800, "radius_miles": 9,
     "rev": {3: (300, .50), 4: (390, .48), 5: (480, .46), 6: (570, .44)},
     "str_note": "Bay County / city: confirm registration and any zoning limits."},

    {**_FL_PANHANDLE_COASTAL, "key": "mexico_beach",
     "label": "Mexico Beach, FL", "lat": 29.940, "lng": -85.410, "radius_miles": 5,
     "rev": {3: (280, .45), 4: (360, .44), 5: (440, .42), 6: (520, .40)},
     "str_note": "Confirm city rental rules (post-hurricane rebuild: also check flood elevation and insurability)."},

    {**_FL_PANHANDLE_COASTAL, "key": "cape_san_blas_port_st_joe",
     "label": "Cape San Blas / Port St. Joe, FL", "lat": 29.740, "lng": -85.330, "radius_miles": 8,
     "rev": {3: (290, .42), 4: (380, .41), 5: (470, .40), 6: (550, .38)},
     "str_note": "Gulf County: confirm registration and flood-zone insurance cost."},

    {**_FL_PANHANDLE_COASTAL, "key": "st_george_island",
     "label": "St. George Island / Apalachicola, FL", "lat": 29.660, "lng": -84.880, "radius_miles": 10,
     "rev": {3: (300, .42), 4: (400, .41), 5: (490, .40), 6: (580, .38)},
     "str_note": "Franklin County: confirm registration; barrier-island flood/wind insurance is the main risk."},

    {**_FL_PANHANDLE_COASTAL, "key": "carrabelle_alligator_point",
     "label": "Carrabelle / Alligator Point, FL", "lat": 29.870, "lng": -84.520, "radius_miles": 10,
     "rev": {3: (240, .38), 4: (320, .37), 5: (400, .36), 6: (470, .34)},
     "str_note": "Franklin/Wakulla Co.: confirm registration; Alligator Point erosion and road-access risk."},

    {"key": "marco_island", "label": "Marco Island, FL", "profile": "acq", "kind": "coastal",
     "state": "FL", "lat": 25.940, "lng": -81.720, "radius_miles": 4,
     "tax_rate": 0.0095, "insurance_rate": 0.014, "insurance_floor": 5500, "land_pct": 0.45,
     "location_rules": [BEACH_RULE,
                        {"signal": "canal", "max_m": 40}],
     "amenity_preference": "pool",
     "rev": {3: (400, .46), 4: (540, .45), 5: (680, .43), 6: (800, .41)},
     "str_note": "VERIFY Marco Island's rental rules (minimum stay / zoning) and association rules before anything else - they decide whether nightly STR is allowed here."},

    {"key": "mccall_id", "label": "McCall, ID", "profile": "acq", "kind": "mountain",
     "state": "ID", "lat": 44.910, "lng": -116.100, "radius_miles": 7,
     "tax_rate": 0.0075, "insurance_rate": 0.0045, "insurance_floor": 2500, "land_pct": 0.35,
     "location_rules": [{"signal": "lake", "max_m": 300},
                        {"signal": "ski", "max_m": 1500},
                        {"signal": "walkable", "min_pois": 8, "radius_m": 800}],
     "amenity_preference": "hot_tub_or_sauna",
     "rev": {3: (320, .40), 4: (430, .40), 5: (540, .38), 6: (650, .36)},
     "str_note": "VERIFY City of McCall STR permit rules and any zone caps before an offer."},

    {"key": "brian_head_ut", "label": "Brian Head, UT", "profile": "acq", "kind": "mountain",
     "state": "UT", "lat": 37.700, "lng": -112.840, "radius_miles": 5,
     "tax_rate": 0.0085, "insurance_rate": 0.0050, "insurance_floor": 2500, "land_pct": 0.25,
     "location_rules": [{"signal": "ski", "max_m": 600},
                        {"signal": "walkable", "min_pois": 5, "radius_m": 800}],
     "amenity_preference": "hot_tub_or_sauna",
     "rev": {3: (260, .42), 4: (360, .42), 5: (450, .40), 6: (540, .38)},
     "str_note": "VERIFY Brian Head town business-license / STR rules and HOA rules before an offer."},
]

# Keywords (listing text) that suggest the land is not owned outright.
LEASEHOLD_KEYWORDS = [
    "leasehold", "land lease", "leased land", "ground lease", "lease land",
    "land is leased", "lease hold",
]
CONDO_KEYWORDS = ["condo", "condominium", "hoa", "association fee", "gated", "poa",
                  "homeowners association", "townhome", "townhouse"]

# Property types that are filtered out before scoring.
EXCLUDE_PROPERTY_TYPES = ["land", "manufactured", "mobile"]
