# STR Deal Scout

A tiny automated agent that scans four lake markets every week for
short-term-rental (STR) investment candidates, scores them against a
due-diligence rubric, and posts a ranked digest as a GitHub Issue.

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
