# STR Deal Scout

A small automated agent that scans markets every week for short-term-rental
(STR) investment candidates, scores them, and posts a ranked digest as a
GitHub Issue. It runs two profiles (set `STR_PROFILES=acq` or `legacy` to run one):

* **acq** (acquisition screen) - Gulf Coast from Gulf Shores AL to Alligator
  Point FL (12 submarkets), Marco Island, McCall ID, Brian Head UT. Screens for
  cash flow after debt service, a modeled year-1 tax deduction near $250k, and a
  desirable location **verified on the map** (see below).
* **legacy** - the original four-lake cap-rate screen (below).

**Lakes covered:** Lake Milton (OH), Berlin Reservoir (OH),
Bemus Point / Chautauqua Lake (NY), Findley Lake / Peek'n Peak (NY).

## How it works
1. **Source** – pulls active for-sale listings around each lake
   (RentCast API, or built-in demo data when no key is set).
2. **Enrich** – assigns a nightly rate + occupancy (AirDNA when available,
   otherwise researched market estimates scaled by size/waterfront).
3. **Model** – runs the cap-rate model (`src/model.py`).
4. **Score & flag** – applies the rubric in `src/score.py`
   (fee-simple only, flag condo/HOA, flag village limits, reward deeded dock,
   require the base-case self-managed cap rate to clear a threshold).
5. **Deliver** – writes a Markdown digest and opens a weekly GitHub Issue.

## Run it locally
```bash
pip install -r requirements.txt
python -m src.main          # demo mode with no keys
```

## Make it live
Add repository **Secrets** named `RENTCAST_API_KEY` (and optionally
`AIRDNA_API_KEY`). See **Setup-Guide.docx** for click-by-click instructions.

## Change the settings
Everything tunable lives in `src/config.py` – the lakes, the ADR/occupancy
assumptions, and the minimum cap-rate threshold. The schedule is the `cron`
line in `.github/workflows/weekly-scout.yml`.

> The agent **reports, it does not decide.** Always verify each flag –
> leasehold, zoning/village caps, dock ownership, HOA STR rules – before
> making an offer. Market ADR/occupancy are estimates, not guarantees.


---
## Acquisition screen (acq profile)

**Gates** (all in `src/acq_config.py`): 3+ bed / 2+ bath, cash flow >= $0 after
debt service (professionally-managed case by default), modeled year-1 deduction
>= 90% of $250k (cost segregation + 100% bonus on furnishings), and a location
signal confirmed on the map.

**Map checks** (`src/geo.py`, OpenStreetMap via Overpass) do not trust listing
text. For each listing that already clears the money gates it measures the
straight-line distance to the beach / named lake / canal / ski lift or run, counts
restaurants and bars within 800 m, and checks whether a busy road (US-98 etc.)
lies between the property and the water. A 1-block walk on a quiet street
passes; a walk across a primary road does not. Default reach is 300 m
(`BEACH_RULE` in `acq_config.py`; use 150 for a strict 1-block rule).

**Revenue** comes from your AirDNA subscription via two CSV files in `data/airdna/`
(headers already there; see `src/airdna.py` for the format):
1. `market_stats.csv` - ADR and occupancy per market and bedroom count (and
   pool / hot tub if you want), from AirDNA's market view.
2. `rentalizer.csv` - address-level results for shortlisted properties.

Status meanings: **PASS** (revenue from AirDNA files), **PROVISIONAL** (all gates
cleared but revenue is still the built-in estimate), **NEEDS_MAP** (map lookup
failed - check location by hand), **FAIL**.

All tax, insurance, rate and revenue defaults are estimates. Replace them before
relying on any result. Short-term-rental legality in each market (and in each
HOA) must be confirmed by you.

Run offline tests: `python -m unittest discover -s tests -t .`
