"""
dashboard.py
============
Builds a single self-contained, interactive HTML dashboard for the week's
results: a sortable/filterable "Candidates" table and an "Excluded" table
(land/mobile/under-$100k listings), with live links out to each listing and
a days-on-market filter so you can sort by how long something's been sitting.

No external dependencies (no CDN, no build step) - it's plain HTML/CSS/JS so
the file works whether it's opened locally, served from GitHub Pages, or
downloaded as a GitHub Actions artifact.
"""

import json
from datetime import date
from urllib.parse import quote


def _listing_link(row: dict) -> dict:
    """RentCast doesn't return a browsable listing URL - only daysOnMarket /
    an MLS number. Use a real URL when we have one; otherwise fall back to a
    Zillow address search, which lands on the right listing in practice."""
    url = row.get("url") or ""
    direct = bool(url)
    if not direct:
        address = row.get("address") or ""
        url = f"https://www.zillow.com/homes/{quote(address)}_rb/" if address else ""
    return {"url": url, "direct": direct}


def _candidate_row(c: dict) -> dict:
    link = _listing_link(c)
    return {
        "score": c.get("score"),
        "passed": bool(c.get("passed")),
        "address": c.get("address", ""),
        "url": link["url"],
        "direct": link["direct"],
        "market": c.get("market", ""),
        "price": c.get("price"),
        "bedrooms": c.get("bedrooms"),
        "dom": c.get("days_on_market"),
        "gross_revenue": c.get("gross_revenue"),
        "cap_self": c.get("cap_self"),
        "cap_pro": c.get("cap_pro"),
        "flags": "; ".join(c.get("flags") or []),
    }


def _excluded_row(e: dict) -> dict:
    link = _listing_link(e)
    return {
        "address": e.get("address", ""),
        "url": link["url"],
        "direct": link["direct"],
        "market": e.get("market", ""),
        "price": e.get("price"),
        "property_type": e.get("property_type", ""),
        "dom": e.get("days_on_market"),
        "reason": e.get("reason", ""),
    }


def _json_for_script(data) -> str:
    """json.dumps, but safe to embed inside a <script> tag."""
    return json.dumps(data).replace("</", "<\\/")


def build_dashboard_html(candidates: list, excluded: list, mode: str) -> str:
    today = date.today().isoformat()
    candidate_rows = [_candidate_row(c) for c in candidates]
    excluded_rows = [_excluded_row(e) for e in excluded]
    passed_count = sum(1 for c in candidate_rows if c["passed"])

    demo_banner = (
        '<p class="banner">DEMO MODE - showing built-in sample listings. '
        'Add a <code>RENTCAST_API_KEY</code> secret for live data.</p>'
        if mode == "demo" else ""
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>STR Deal Scout - {today}</title>
<style>
  :root {{
    color-scheme: light dark;
    --bg: #f7f7f5; --panel: #ffffff; --text: #1a1a1a; --muted: #6b6b6b;
    --border: #e3e3e0; --accent: #2f6f4f; --accent-bg: #eaf3ee;
    --warn: #9a5b00; --warn-bg: #fdf1de; --row-alt: #fafaf8;
    --link: #1a5fb4; --shadow: 0 1px 2px rgba(0,0,0,.06);
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #16181a; --panel: #1e2124; --text: #e8e8e6; --muted: #9a9a97;
      --border: #33373b; --accent: #7fd3a6; --accent-bg: #1c332a;
      --warn: #e0b466; --warn-bg: #332a15; --row-alt: #1a1d1f;
      --link: #7bb2ff; --shadow: 0 1px 2px rgba(0,0,0,.4);
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--bg); color: var(--text);
    font: 14px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    padding: 24px;
  }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }}
  .subtitle {{ color: var(--muted); margin: 0 0 16px; }}
  .banner {{
    background: var(--warn-bg); color: var(--warn); border: 1px solid var(--warn);
    padding: 8px 12px; border-radius: 6px; font-size: 13px; margin: 0 0 16px;
  }}
  .summary {{ display: flex; gap: 24px; margin-bottom: 16px; flex-wrap: wrap; }}
  .stat {{ background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
    padding: 10px 16px; box-shadow: var(--shadow); }}
  .stat .n {{ font-size: 20px; font-weight: 600; }}
  .stat .l {{ color: var(--muted); font-size: 12px; }}
  .tabs {{ display: flex; gap: 4px; margin-bottom: 12px; }}
  .tab {{
    padding: 8px 16px; border: 1px solid var(--border); background: var(--panel);
    color: var(--text); border-radius: 6px 6px 0 0; cursor: pointer; font-size: 13px;
  }}
  .tab.active {{ background: var(--accent-bg); color: var(--accent); font-weight: 600;
    border-bottom-color: var(--accent-bg); }}
  .panel {{ background: var(--panel); border: 1px solid var(--border); border-radius: 0 8px 8px 8px;
    box-shadow: var(--shadow); padding: 16px; }}
  .filters {{ display: flex; gap: 10px; flex-wrap: wrap; align-items: flex-end; margin-bottom: 14px; }}
  .field {{ display: flex; flex-direction: column; gap: 4px; }}
  .field label {{ font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .02em; }}
  input, select {{
    background: var(--bg); color: var(--text); border: 1px solid var(--border);
    border-radius: 6px; padding: 6px 8px; font-size: 13px;
  }}
  input[type="number"] {{ width: 90px; }}
  input[type="search"] {{ width: 220px; }}
  button.reset {{
    border: 1px solid var(--border); background: var(--panel); color: var(--text);
    border-radius: 6px; padding: 6px 12px; font-size: 13px; cursor: pointer;
  }}
  button.reset:hover {{ background: var(--row-alt); }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  thead th {{
    position: sticky; top: 0; background: var(--panel); text-align: left;
    padding: 8px 10px; border-bottom: 2px solid var(--border); cursor: pointer;
    white-space: nowrap; user-select: none;
  }}
  thead th:hover {{ color: var(--accent); }}
  thead th .arrow {{ color: var(--accent); font-size: 11px; }}
  tbody td {{ padding: 7px 10px; border-bottom: 1px solid var(--border); vertical-align: top; }}
  tbody tr:nth-child(even) {{ background: var(--row-alt); }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  a.addr {{ color: var(--link); text-decoration: none; }}
  a.addr:hover {{ text-decoration: underline; }}
  .search-tag {{ color: var(--muted); font-size: 11px; margin-left: 4px; }}
  .badge {{ display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 11px; font-weight: 600; }}
  .badge.pass {{ background: var(--accent-bg); color: var(--accent); }}
  .badge.fail {{ background: var(--warn-bg); color: var(--warn); }}
  .flags {{ color: var(--muted); font-size: 12px; }}
  .empty {{ padding: 24px; text-align: center; color: var(--muted); }}
  footer {{ color: var(--muted); font-size: 12px; margin-top: 16px; }}
  .table-wrap {{ overflow-x: auto; max-height: 70vh; overflow-y: auto; }}
</style>
</head>
<body>

<h1>STR Deal Scout - weekly dashboard</h1>
<p class="subtitle">{today} - scanned 4 lakes.</p>
{demo_banner}

<div class="summary">
  <div class="stat"><div class="n">{len(candidate_rows)}</div><div class="l">Total scored</div></div>
  <div class="stat"><div class="n">{passed_count}</div><div class="l">Passed filters</div></div>
  <div class="stat"><div class="n">{len(candidate_rows) - passed_count}</div><div class="l">Flagged</div></div>
  <div class="stat"><div class="n">{len(excluded_rows)}</div><div class="l">Excluded (land/mobile/under $100k)</div></div>
</div>

<div class="tabs">
  <div class="tab active" data-tab="candidates" onclick="setTab('candidates')">Candidates (<span id="count-candidates">{len(candidate_rows)}</span>)</div>
  <div class="tab" data-tab="excluded" onclick="setTab('excluded')">Excluded (<span id="count-excluded">{len(excluded_rows)}</span>)</div>
</div>

<div class="panel">
  <div class="filters">
    <div class="field">
      <label for="search">Search</label>
      <input type="search" id="search" placeholder="Address, market, flags..." oninput="render()">
    </div>
    <div class="field">
      <label for="market">Market</label>
      <select id="market" onchange="render()"><option value="">All markets</option></select>
    </div>
    <div class="field" id="status-field">
      <label for="status">Status</label>
      <select id="status" onchange="render()">
        <option value="">All</option>
        <option value="passed">Passed only</option>
        <option value="flagged">Flagged only</option>
      </select>
    </div>
    <div class="field">
      <label for="domMin">Min days on market</label>
      <input type="number" id="domMin" min="0" placeholder="0" oninput="render()">
    </div>
    <div class="field">
      <label for="domMax">Max days on market</label>
      <input type="number" id="domMax" min="0" placeholder="any" oninput="render()">
    </div>
    <button class="reset" onclick="resetFilters()">Reset filters</button>
  </div>
  <div class="table-wrap">
    <table>
      <thead><tr id="thead-row"></tr></thead>
      <tbody id="tbody"></tbody>
    </table>
    <div class="empty" id="empty" style="display:none">No listings match these filters.</div>
  </div>
</div>

<footer>Assumptions and thresholds live in <code>src/config.py</code>. The agent reports; it does not decide - verify every flag before an offer. Listing links marked with * are a Zillow address search (RentCast doesn't provide a direct listing URL), not a guaranteed exact match.</footer>

<script>
const CANDIDATES = {_json_for_script(candidate_rows)};
const EXCLUDED = {_json_for_script(excluded_rows)};

const COLUMNS = {{
  candidates: [
    {{ key: "score", label: "Score", type: "num" }},
    {{ key: "passed", label: "Status", type: "status" }},
    {{ key: "address", label: "Address", type: "addr" }},
    {{ key: "market", label: "Market", type: "text" }},
    {{ key: "price", label: "Price", type: "money" }},
    {{ key: "bedrooms", label: "Bd", type: "num" }},
    {{ key: "dom", label: "Days on Market", type: "num" }},
    {{ key: "gross_revenue", label: "Gross Revenue", type: "money" }},
    {{ key: "cap_self", label: "Cap (self)", type: "pct" }},
    {{ key: "cap_pro", label: "Cap (pro)", type: "pct" }},
    {{ key: "flags", label: "Flags", type: "flags" }},
  ],
  excluded: [
    {{ key: "address", label: "Address", type: "addr" }},
    {{ key: "market", label: "Market", type: "text" }},
    {{ key: "price", label: "Price", type: "money" }},
    {{ key: "property_type", label: "Property Type", type: "text" }},
    {{ key: "dom", label: "Days on Market", type: "num" }},
    {{ key: "reason", label: "Reason", type: "flags" }},
  ],
}};

let state = {{
  tab: "candidates",
  sortKey: "score",
  sortDir: "desc",
}};

function money(n) {{
  return (n === null || n === undefined) ? "—" : "$" + Math.round(n).toLocaleString();
}}
function pct(n) {{
  return (n === null || n === undefined) ? "—" : (n * 100).toFixed(1) + "%";
}}
function num(n) {{
  return (n === null || n === undefined) ? "—" : n;
}}

function populateMarkets() {{
  const sel = document.getElementById("market");
  const markets = [...new Set([...CANDIDATES, ...EXCLUDED].map(r => r.market).filter(Boolean))].sort();
  for (const m of markets) {{
    const opt = document.createElement("option");
    opt.value = m; opt.textContent = m;
    sel.appendChild(opt);
  }}
}}

function setTab(tab) {{
  state.tab = tab;
  state.sortKey = tab === "candidates" ? "score" : "price";
  state.sortDir = tab === "candidates" ? "desc" : "asc";
  document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === tab));
  document.getElementById("status-field").style.display = tab === "candidates" ? "" : "none";
  render();
}}

function resetFilters() {{
  document.getElementById("search").value = "";
  document.getElementById("market").value = "";
  document.getElementById("status").value = "";
  document.getElementById("domMin").value = "";
  document.getElementById("domMax").value = "";
  render();
}}

function setSort(key) {{
  if (state.sortKey === key) {{
    state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
  }} else {{
    state.sortKey = key;
    state.sortDir = "asc";
  }}
  render();
}}

function matchesFilters(row) {{
  const search = document.getElementById("search").value.trim().toLowerCase();
  const market = document.getElementById("market").value;
  const status = document.getElementById("status").value;
  const domMin = document.getElementById("domMin").value;
  const domMax = document.getElementById("domMax").value;

  if (search) {{
    const hay = [row.address, row.market, row.flags || row.reason || ""].join(" ").toLowerCase();
    if (!hay.includes(search)) return false;
  }}
  if (market && row.market !== market) return false;
  if (state.tab === "candidates" && status) {{
    if (status === "passed" && !row.passed) return false;
    if (status === "flagged" && row.passed) return false;
  }}
  if (domMin !== "" && (row.dom === null || row.dom === undefined || row.dom < Number(domMin))) return false;
  if (domMax !== "" && (row.dom === null || row.dom === undefined || row.dom > Number(domMax))) return false;
  return true;
}}

function sortRows(rows) {{
  const key = state.sortKey, dir = state.sortDir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {{
    let av = a[key], bv = b[key];
    if (av === null || av === undefined) av = -Infinity;
    if (bv === null || bv === undefined) bv = -Infinity;
    if (typeof av === "string") return av.localeCompare(bv) * dir;
    return (av - bv) * dir;
  }});
}}

function renderCell(row, col) {{
  switch (col.type) {{
    case "money": return `<td class="num">${{money(row[col.key])}}</td>`;
    case "pct": return `<td class="num">${{pct(row[col.key])}}</td>`;
    case "num": return `<td class="num">${{num(row[col.key])}}</td>`;
    case "status": return `<td><span class="badge ${{row.passed ? 'pass' : 'fail'}}">${{row.passed ? 'Passed' : 'Flagged'}}</span></td>`;
    case "addr": {{
      const star = row.direct ? "" : '<span class="search-tag">*</span>';
      const link = row.url
        ? `<a class="addr" href="${{row.url}}" target="_blank" rel="noopener">${{row.address}}</a>${{star}}`
        : row.address;
      return `<td>${{link}}</td>`;
    }}
    case "flags": return `<td class="flags">${{row[col.key] || "-"}}</td>`;
    default: return `<td>${{row[col.key] ?? "-"}}</td>`;
  }}
}}

function render() {{
  const cols = COLUMNS[state.tab];
  const data = state.tab === "candidates" ? CANDIDATES : EXCLUDED;

  const thead = document.getElementById("thead-row");
  thead.innerHTML = cols.map(c => {{
    const arrow = state.sortKey === c.key ? `<span class="arrow">${{state.sortDir === "asc" ? "▲" : "▼"}}</span>` : "";
    return `<th onclick="setSort('${{c.key}}')">${{c.label}} ${{arrow}}</th>`;
  }}).join("");

  const filtered = sortRows(data.filter(matchesFilters));
  const tbody = document.getElementById("tbody");
  tbody.innerHTML = filtered.map(row => `<tr>${{cols.map(c => renderCell(row, c)).join("")}}</tr>`).join("");
  document.getElementById("empty").style.display = filtered.length ? "none" : "block";

  document.getElementById("count-candidates").textContent =
    state.tab === "candidates" ? filtered.length + " / " + CANDIDATES.length : CANDIDATES.length;
  document.getElementById("count-excluded").textContent =
    state.tab === "excluded" ? filtered.length + " / " + EXCLUDED.length : EXCLUDED.length;
}}

populateMarkets();
render();
</script>
</body>
</html>
"""
