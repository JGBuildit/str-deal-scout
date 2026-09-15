# STR Deal Scout

A tiny automated agent that scans a set of waterfront markets every week for
short-term-rental (STR) investment candidates, scores them against a
due-diligence rubric, and posts a ranked digest as a GitHub Issue.

**Markets covered:** Lake Milton (OH), Berlin Reservoir (OH),
Bemus Point / Chautauqua Lake (NY), Findley Lake / Peek'n Peak (NY),
Cape San Blas (FL), St. Joseph Peninsula (FL), Alligator Point (FL),
Breckenridge (CO), Norris Lake (TN).

> The five markets added after the original four lakes don't yet have the
> hands-on ADR/occupancy research the originals do - see the `notes` field
> on each in `src/config.py` before trusting their numbers. Breckenridge in
> particular isn't a waterfront market, so the pipeline's waterfront-only
> filter will exclude nearly everything RentCast returns for it.

## How it works
1. **Source** – pulls active for-sale listings around each market
   (RentCast API, or built-in demo data when no key is set).
2. **Filter** – drops listings that are land/mobile, under $100k, or not
   waterfront, before they're scored (see `src/main.py`).
3. **Enrich** – assigns a nightly rate + occupancy (AirROI when available,
   else AirDNA, otherwise researched market estimates scaled by size/
   waterfront).
4. **Model** – runs the cap-rate model (`src/model.py`).
5. **Score & flag** – applies the rubric in `src/score.py`
   (fee-simple only, flag condo/HOA, flag village limits, reward deeded dock,
   require the base-case self-managed cap rate to clear a threshold).
6. **Deliver** – writes a Markdown digest and an interactive HTML dashboard,
   and opens a weekly GitHub Issue.

## Run it locally
```bash
pip install -r requirements.txt
python -m src.main          # demo mode with no keys
```

## Make it live
Add a repository **Secret** named `RENTCAST_API_KEY`. For address-level ADR/
occupancy (instead of the market-level estimates), also add `AIRROI_API_KEY`
(self-serve, pay-as-you-go - sign up at airroi.com) and/or `AIRDNA_API_KEY`
(enterprise-only, sales-gated; used only if `AIRROI_API_KEY` isn't set). See
**Setup-Guide.docx** for click-by-click instructions.

## Change the settings
Everything tunable lives in `src/config.py` – the markets, the ADR/occupancy
assumptions, and the minimum cap-rate threshold. The schedule is the `cron`
line in `.github/workflows/weekly-scout.yml`.

> The agent **reports, it does not decide.** Always verify each flag –
> leasehold, zoning/village caps, dock ownership, HOA STR rules – before
> making an offer. Market ADR/occupancy are estimates, not guarantees.
