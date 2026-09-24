"""Classify FRA ratings by cast pips and write analysis CSVs + a shareable HTML report.

Reads output/fra_j2sjosh_limited_ratings.csv only; does not modify that file.
"""

from __future__ import annotations

import csv
import json
import re
import sys
import urllib.request
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"
CACHE = ROOT / ".cache"
SOURCE = OUT / "fra_j2sjosh_limited_ratings.csv"
PLOTLY_URL = "https://cdn.plot.ly/plotly-2.35.2.min.js"
PLOTLY_CACHE = CACHE / "plotly-2.35.2.min.js"
UA = "fra-limited-sheet/1.0 (personal research script)"

WUBRG = "WUBRG"
COLOR_NAMES = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green"}
PAIRS = ["".join(c) for c in combinations(WUBRG, 2)]

MANA_RE = re.compile(r"\{([^}]+)\}")


def mana_symbols(cost: str) -> list[str]:
    return MANA_RE.findall(cost or "")


def color_code(colors: set[str] | frozenset[str]) -> str:
    return "".join(c for c in WUBRG if c in colors)


def color_name(code: str) -> str:
    if not code:
        return "Colorless"
    return "/".join(COLOR_NAMES[c] for c in code)


def all_archetypes() -> list[str]:
    codes = []
    for n in range(1, 6):
        codes.extend("".join(combo) for combo in combinations(WUBRG, n))
    return codes


ARCHETYPES = all_archetypes()


def pip_constraints(cost: str) -> list[frozenset[str]]:
    """Each colored pip is a set of colors that can pay it. {2/W} is always payable."""
    out: list[frozenset[str]] = []
    for sym in mana_symbols(cost):
        parts = [p for p in sym.split("/") if p]
        colors = [p for p in parts if p in WUBRG]
        if not colors:
            continue
        if any(p.isdigit() for p in parts):
            continue
        out.append(frozenset(colors))
    return out


def identity_colors(code: str) -> set[str]:
    return {c for c in (code or "") if c in WUBRG}


def classify_row(row: dict) -> dict:
    costs = " ".join(
        p for p in (row.get("Mana Cost", ""), row.get("Second Half Cost", "")) if p
    )
    constraints = pip_constraints(costs)
    ident = identity_colors(row.get("Color Identity", ""))

    required: set[str] = set()
    hybrid: set[str] = set()
    for cset in constraints:
        if len(cset) == 1:
            required |= set(cset)
        else:
            hybrid |= set(cset)

    has_cost = bool((row.get("Mana Cost") or "").strip() or (row.get("Second Half Cost") or "").strip())
    if not constraints:
        # Lands with no pips use color identity. {2/W} costs (Karn) are always payable
        # and must not inherit a five-color identity as a requirement.
        required = set() if has_cost else set(ident)

    req_code = color_code(required)
    hyb_code = color_code(hybrid)

    if not required and not hybrid:
        bucket = "Colorless"
    elif len(required) >= 2:
        bucket = f"Gold {color_name(req_code)}"
    elif hybrid and not required:
        bucket = f"Hybrid {color_name(hyb_code)}"
    else:
        bucket = f"Mono {color_name(req_code)}" if req_code else "Colorless"

    if required:
        min_size = len(required)
    elif hybrid:
        min_size = 1
    else:
        min_size = 0

    def playable_in(arch: str) -> bool:
        aset = set(arch)
        if constraints:
            return all(bool(cset & aset) for cset in constraints)
        if has_cost or not ident:
            return True
        return ident <= aset

    playable = [a for a in ARCHETYPES if playable_in(a)]
    archetypes_cell = "".join(f"|{color_name(a)}|" for a in playable)

    return {
        **row,
        "Required Colors": req_code,
        "Hybrid Colors": hyb_code,
        "Cast Bucket": bucket,
        "Archetype Size Min": str(min_size),
        "Archetypes": archetypes_cell,
        "_constraints": ["".join(sorted(c, key=WUBRG.index)) for c in constraints],
        "_playable": playable,
    }


def role_in_archetype(card: dict, arch: str) -> str:
    bucket = card["Cast Bucket"]
    req = card["Required Colors"]
    hyb = card["Hybrid Colors"]
    if bucket == "Colorless":
        return "Colorless"
    if bucket.startswith("Gold"):
        return "Gold"
    if bucket.startswith("Hybrid"):
        if hyb == arch or set(hyb) <= set(arch):
            if len(hyb) >= 2 and hyb != arch and len(arch) == 2:
                return "Off-pair hybrid" if hyb != arch else "Hybrid"
            if hyb == arch:
                return "Hybrid"
            if len(arch) == 2 and hyb != arch:
                return "Off-pair hybrid"
            return "Hybrid"
        return "Off-pair hybrid"
    if bucket.startswith("Mono"):
        if hyb and len(arch) == 2 and hyb != arch and set(hyb) & set(arch):
            return "Mono"
        return "Mono"
    return bucket


def load_rows() -> list[dict]:
    if not SOURCE.exists():
        raise SystemExit(f"Missing source CSV: {SOURCE}")
    with SOURCE.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_classified(cards: list[dict]) -> None:
    path = OUT / "fra_j2sjosh_classified.csv"
    fields = [
        "Card Name",
        "Front Face Name",
        "Color",
        "Color Code",
        "Color Identity",
        "Mana Cost",
        "Mana Value",
        "Rarity",
        "Card Type",
        "Cast Bucket",
        "Required Colors",
        "Hybrid Colors",
        "Archetype Size Min",
        "Archetypes",
        "J2SJosh Rating",
        "Rating Note",
        "Second Half",
        "Second Half Cost",
        "Layout",
        "Scryfall URL",
        "Image URL",
        "Collector Number",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(cards)
    print(f"Wrote {path} ({len(cards)} cards)")


def write_membership(cards: list[dict]) -> None:
    path = OUT / "fra_archetype_membership.csv"
    fields = [
        "Card Name",
        "Mana Cost",
        "Rarity",
        "J2SJosh Rating",
        "Cast Bucket",
        "Required Colors",
        "Hybrid Colors",
        "Archetype",
        "Archetype Code",
        "Archetype Size",
        "Role In Archetype",
        "Rating Note",
        "Scryfall URL",
        "Image URL",
    ]
    n = 0
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for card in cards:
            for arch in card["_playable"]:
                w.writerow(
                    {
                        "Card Name": card["Card Name"],
                        "Mana Cost": card["Mana Cost"],
                        "Rarity": card["Rarity"],
                        "J2SJosh Rating": card["J2SJosh Rating"],
                        "Cast Bucket": card["Cast Bucket"],
                        "Required Colors": card["Required Colors"],
                        "Hybrid Colors": card["Hybrid Colors"],
                        "Archetype": color_name(arch),
                        "Archetype Code": arch,
                        "Archetype Size": len(arch),
                        "Role In Archetype": role_in_archetype(card, arch),
                        "Rating Note": card.get("Rating Note", ""),
                        "Scryfall URL": card.get("Scryfall URL", ""),
                        "Image URL": card.get("Image URL", ""),
                    }
                )
                n += 1
    print(f"Wrote {path} ({n} rows)")


def ensure_plotly() -> str:
    CACHE.mkdir(exist_ok=True)
    if not PLOTLY_CACHE.exists():
        print(f"Downloading Plotly to {PLOTLY_CACHE} …")
        req = urllib.request.Request(PLOTLY_URL, headers={"User-Agent": UA})
        with urllib.request.urlopen(req) as resp:
            PLOTLY_CACHE.write_bytes(resp.read())
    return PLOTLY_CACHE.read_text(encoding="utf-8")


def cards_json(cards: list[dict]) -> list[dict]:
    out = []
    for c in cards:
        try:
            rating = float(c["J2SJosh Rating"])
        except (TypeError, ValueError):
            continue
        out.append(
            {
                "name": c["Card Name"],
                "cost": c.get("Mana Cost") or "",
                "rarity": c["Rarity"],
                "rating": rating,
                "bucket": c["Cast Bucket"],
                "required": c["Required Colors"],
                "hybrid": c["Hybrid Colors"],
                "playable": c["_playable"],
                "group": bool(c.get("Rating Note")),
                "note": c.get("Rating Note") or "",
                "type": c.get("Card Type") or "",
                "image": c.get("Image URL") or "",
                "url": c.get("Scryfall URL") or "",
            }
        )
    return out


def write_html(cards: list[dict]) -> None:
    plotly_js = ensure_plotly()
    payload = json.dumps(cards_json(cards), separators=(",", ":"))
    html = HTML_TEMPLATE.replace("/*__PLOTLY_JS__*/", plotly_js).replace(
        "__CARDS_JSON__", payload
    )
    path = OUT / "fra_color_ratings.html"
    path.write_text(html, encoding="utf-8")
    print(f"Wrote {path} ({path.stat().st_size // 1024} KB)")


def spotcheck(cards: list[dict]) -> None:
    by_name = {c["Card Name"]: c for c in cards}
    checks = [
        ("Blessed Ghoul", "Hybrid White/Black", "WB", True, "W" in "{playable}"),
        ("Fatehold Charm", "Gold White/Blue", "WU", True, None),
        ("Emergency Phytomedic // Seed Suture", "Hybrid White/Green", "WG", True, None),
        ("Karn, Gilded Guardian", "Colorless", "", True, None),
        ("Vraska, Soul of Stone", "Gold White/Blue/Red", "WUR", True, None),
    ]
    ok = True
    for name, bucket, req, want_w, _ in checks:
        c = by_name.get(name)
        if not c:
            print(f"SPOTCHECK missing: {name}")
            ok = False
            continue
        problems = []
        if c["Cast Bucket"] != bucket:
            problems.append(f"bucket {c['Cast Bucket']!r} != {bucket!r}")
        if c["Required Colors"] != req and not (
            bucket.startswith("Hybrid") and c["Required Colors"] == "" and c["Hybrid Colors"] == req
        ):
            if bucket.startswith("Hybrid"):
                if c["Hybrid Colors"] != req:
                    problems.append(f"hybrid {c['Hybrid Colors']!r} != {req!r}")
            else:
                problems.append(f"required {c['Required Colors']!r} != {req!r}")
        if name == "Blessed Ghoul":
            if "W" not in c["_playable"] or "B" not in c["_playable"] or "WU" not in c["_playable"]:
                problems.append(f"playable {c['_playable'][:8]}…")
            if "R" in c["_playable"]:
                problems.append("should not be playable in mono Red")
        if name == "Fatehold Charm":
            if "W" in c["_playable"] or "WU" not in c["_playable"]:
                problems.append("gold WU membership")
        if name == "Karn, Gilded Guardian":
            if len(c["_playable"]) != 31:
                problems.append(f"karn playable {len(c['_playable'])}")
        if name == "Vraska, Soul of Stone":
            if "WU" in c["_playable"] or "WUR" not in c["_playable"]:
                problems.append("3c gold membership")
        angel = by_name.get("Blossom-Blessed Angel // Seed Suture")
        if problems:
            print(f"SPOTCHECK fail {name}: {'; '.join(problems)}")
            ok = False
        else:
            print(f"SPOTCHECK ok {name}: {c['Cast Bucket']} req={c['Required Colors']} hyb={c['Hybrid Colors']}")
    angel = by_name.get("Blossom-Blessed Angel // Seed Suture")
    if angel:
        print(
            f"SPOTCHECK Blossom-Blessed Angel: {angel['Cast Bucket']} "
            f"req={angel['Required Colors']} hyb={angel['Hybrid Colors']} "
            f"playable_1c={[a for a in angel['_playable'] if len(a)==1]}"
        )
        if angel["Required Colors"] != "W" or "G" in [a for a in angel["_playable"] if len(a) == 1]:
            print("SPOTCHECK note: Angel requires White (creature pip); not Green-only")
    if not ok:
        print("Spot checks reported issues.", file=sys.stderr)


def main() -> int:
    rows = load_rows()
    cards = [classify_row(r) for r in rows]
    write_classified(cards)
    write_membership(cards)
    write_html(cards)
    spotcheck(cards)
    return 0


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Reality Fracture — J2SJosh ratings by color</title>
<script>/*__PLOTLY_JS__*/</script>
<style>
:root {
  --bg: #f4f1ea;
  --ink: #1c1916;
  --muted: #5c564e;
  --card: #fffcf6;
  --line: #d8d0c4;
  --accent: #3d4f3a;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: "Segoe UI", system-ui, sans-serif;
  background: var(--bg);
  color: var(--ink);
}
header {
  padding: 1.25rem 1.5rem 0.75rem;
  border-bottom: 1px solid var(--line);
  background: var(--card);
}
header h1 { font-size: 1.35rem; margin: 0 0 0.35rem; font-weight: 650; }
header p { margin: 0; color: var(--muted); font-size: 0.9rem; max-width: 52rem; }
.filters {
  display: flex; flex-wrap: wrap; gap: 0.75rem 1.25rem;
  align-items: center; padding: 0.85rem 1.5rem;
  border-bottom: 1px solid var(--line);
  background: var(--card);
}
.filters label { font-size: 0.85rem; color: var(--muted); display: flex; align-items: center; gap: 0.35rem; }
.filters fieldset {
  border: 1px solid var(--line); border-radius: 6px; padding: 0.35rem 0.6rem;
  display: flex; gap: 0.65rem; margin: 0;
}
.filters legend { font-size: 0.75rem; color: var(--muted); padding: 0 0.25rem; }
main { padding: 1rem 1.5rem 2.5rem; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 0.6rem; margin-bottom: 1rem; }
.kpi { background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 0.65rem 0.75rem; }
.kpi .k { font-size: 0.72rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.03em; }
.kpi .v { font-size: 1.25rem; font-weight: 650; }
.kpi .s { font-size: 0.78rem; color: var(--muted); }
.panel { background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 0.25rem; }
.charts { display: grid; grid-template-columns: 1.2fr 0.8fr; gap: 0.75rem; margin-bottom: 1.25rem; }
.charts .panel > div { min-height: 380px; }
@media (max-width: 900px) { .charts { grid-template-columns: 1fr; } }
.hint { color: var(--muted); font-size: 0.8rem; margin: 0 0 0.75rem; }
h2 { font-size: 1rem; font-weight: 650; margin: 0 0 0.5rem; }
table { width: 100%; border-collapse: collapse; font-size: 0.88rem; background: var(--card); }
th, td { text-align: left; padding: 0.4rem 0.5rem; border-bottom: 1px solid var(--line); }
th { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.03em; color: var(--muted); cursor: pointer; }
tr:hover td { background: #efe8dc; }
input[type="search"] { padding: 0.4rem 0.6rem; border: 1px solid var(--line); border-radius: 6px; min-width: 16rem; }
a { color: var(--accent); }
select { padding: 0.3rem 0.45rem; border: 1px solid var(--line); border-radius: 6px; }
.swatch { display: inline-block; width: 0.7rem; height: 0.7rem; border-radius: 2px; margin-right: 0.3rem; vertical-align: middle; }
#count { color: var(--muted); font-size: 0.8rem; margin-left: 0.5rem; }
</style>
</head>
<body>
<header>
  <h1>Reality Fracture limited ratings by color</h1>
  <p>J2SJosh ratings (out of 5). Hybrid mana counts toward either color; cards that require two colors sit in gold. Pick an archetype to compare curves and see those cards.</p>
</header>
<div class="filters">
  <label>Archetype
    <select id="arch">
      <option value="all">All</option>
      <optgroup label="One color">
        <option value="W">White</option>
        <option value="U">Blue</option>
        <option value="B">Black</option>
        <option value="R">Red</option>
        <option value="G">Green</option>
      </optgroup>
      <optgroup label="Two colors">
        <option value="WU">White/Blue</option>
        <option value="UB">Blue/Black</option>
        <option value="BR">Black/Red</option>
        <option value="RG">Red/Green</option>
        <option value="WG">White/Green</option>
        <option value="WB">White/Black</option>
        <option value="UR">Blue/Red</option>
        <option value="BG">Black/Green</option>
        <option value="WR">White/Red</option>
        <option value="UG">Blue/Green</option>
      </optgroup>
    </select>
  </label>
  <fieldset>
    <legend>Rarity</legend>
    <label><input type="checkbox" class="rar" value="Common" checked> Common</label>
    <label><input type="checkbox" class="rar" value="Uncommon" checked> Uncommon</label>
    <label><input type="checkbox" class="rar" value="Rare" checked> Rare</label>
    <label><input type="checkbox" class="rar" value="Mythic" checked> Mythic</label>
  </fieldset>
  <label><input type="checkbox" id="excludeGroup" checked> Exclude group-rated lands</label>
</div>
<main>
  <p class="hint" id="hint"></p>
  <div class="kpis" id="kpis"></div>
  <div class="charts">
    <div class="panel"><div id="chart"></div></div>
    <div class="panel"><div id="box"></div></div>
  </div>
  <h2>Cards <span id="count"></span></h2>
  <p><input type="search" id="q" placeholder="Filter by name, cost, or bucket"></p>
  <div style="overflow:auto">
    <table>
      <thead>
        <tr>
          <th data-k="name">Card</th>
          <th data-k="cost">Cost</th>
          <th data-k="rarity">Rarity</th>
          <th data-k="bucket">Bucket</th>
          <th data-k="rating">Rating</th>
        </tr>
      </thead>
      <tbody id="tbody"></tbody>
    </table>
  </div>
</main>
<script>
const CARDS = __CARDS_JSON__;
const NAMES = {W:"White",U:"Blue",B:"Black",R:"Red",G:"Green"};
const COLORS = {W:"#c9b37a",U:"#4a7ea8",B:"#4a4450",R:"#b5523a",G:"#4d6b45",C:"#8a8378",Gold:"#7a5c2e",Hyb:"#6b5b95"};
const BINS = [0.5,1,1.5,2,2.5,3,3.5,4,4.5,5];
const layoutBase = {
  paper_bgcolor: "#fffcf6",
  plot_bgcolor: "#fffcf6",
  font: { color: "#1c1916", size: 12 },
  margin: { t: 56, r: 20, b: 100, l: 52 },
  legend: {
    orientation: "h",
    y: -0.34,
    yanchor: "top",
    x: 0.5,
    xanchor: "center",
    font: { size: 11 }
  },
  hovermode: "x unified"
};

function rarities() {
  return [...document.querySelectorAll(".rar:checked")].map(x => x.value);
}
function baseFiltered() {
  const rar = new Set(rarities());
  const ex = document.getElementById("excludeGroup").checked;
  return CARDS.filter(c => rar.has(c.rarity) && (!ex || !c.group));
}
function inArch(c, arch) {
  return c.playable.indexOf(arch) >= 0;
}
function mean(xs) {
  if (!xs.length) return null;
  return xs.reduce((a,b)=>a+b,0)/xs.length;
}
function median(xs) {
  if (!xs.length) return null;
  const s = [...xs].sort((a,b)=>a-b);
  const m = Math.floor(s.length/2);
  return s.length%2 ? s[m] : (s[m-1]+s[m])/2;
}
function fmt(n) { return n==null ? "—" : n.toFixed(2); }
function pct(xs, t) {
  if (!xs.length) return "—";
  return (100 * xs.filter(x => x >= t).length / xs.length).toFixed(0) + "%";
}
function counts(ratings) {
  const m = {};
  BINS.forEach(b => m[b] = 0);
  ratings.forEach(r => { if (m[r] != null) m[r]++; });
  return BINS.map(b => m[b]);
}
function uniqueCards(series) {
  const seen = new Set();
  const out = [];
  series.forEach(s => s.cards.forEach(c => {
    if (!seen.has(c.name)) { seen.add(c.name); out.push(c); }
  }));
  return out;
}
function colorPool(list, color) {
  if (color === "C") return list.filter(c => c.bucket === "Colorless");
  if (color === "Gold") return list.filter(c => c.bucket.startsWith("Gold"));
  return list.filter(c => inArch(c, color) && !c.bucket.startsWith("Gold") && c.bucket !== "Colorless");
}
function pairSeries(list, pair) {
  const a = pair[0], b = pair[1];
  const pool = list.filter(c => inArch(c, pair));
  const hybridName = "Hybrid " + NAMES[a] + "/" + NAMES[b];
  const goldName = "Gold " + NAMES[a] + "/" + NAMES[b];
  return [
    { key: NAMES[a], color: COLORS[a], cards: pool.filter(c => c.bucket === "Mono " + NAMES[a] || (c.bucket.startsWith("Hybrid") && c.bucket !== hybridName && c.hybrid.indexOf(a) >= 0 && c.required === "")) },
    { key: NAMES[b], color: COLORS[b], cards: pool.filter(c => c.bucket === "Mono " + NAMES[b] || (c.bucket.startsWith("Hybrid") && c.bucket !== hybridName && c.hybrid.indexOf(b) >= 0 && c.hybrid.indexOf(a) < 0 && c.required === "")) },
    { key: "Hybrid " + NAMES[a] + "/" + NAMES[b], color: COLORS.Hyb, cards: pool.filter(c => c.bucket === hybridName) },
    { key: "Gold " + NAMES[a] + "/" + NAMES[b], color: COLORS.Gold, cards: pool.filter(c => c.bucket === goldName) },
  ];
}

function view() {
  const arch = document.getElementById("arch").value;
  const list = baseFiltered();
  if (arch === "all") {
    return {
      title: "Rating curve — all colors",
      hint: "Each color is mono plus hybrids you can pay with that color. Gold is separate. Click a legend item to hide a line.",
      series: [
        { key: "White", color: COLORS.W, cards: colorPool(list, "W") },
        { key: "Blue", color: COLORS.U, cards: colorPool(list, "U") },
        { key: "Black", color: COLORS.B, cards: colorPool(list, "B") },
        { key: "Red", color: COLORS.R, cards: colorPool(list, "R") },
        { key: "Green", color: COLORS.G, cards: colorPool(list, "G") },
        { key: "Colorless", color: COLORS.C, cards: colorPool(list, "C") },
        { key: "Gold", color: COLORS.Gold, cards: colorPool(list, "Gold") },
      ],
      table: list
    };
  }
  if (arch.length === 1) {
    const cards = colorPool(list, arch);
    const mono = cards.filter(c => c.bucket.startsWith("Mono"));
    const hybrid = cards.filter(c => c.bucket.startsWith("Hybrid"));
    const series = [
      { key: "Mono " + NAMES[arch], color: COLORS[arch], cards: mono },
    ];
    if (hybrid.length) {
      series.push({ key: "Hybrid", color: COLORS.Hyb, cards: hybrid });
    }
    return {
      title: "Rating curve — " + NAMES[arch],
      hint: NAMES[arch] + " splits into mono cards and hybrids payable with " + NAMES[arch] + ". Gold that requires another color is omitted.",
      series: series,
      table: cards
    };
  }
  const series = pairSeries(list, arch);
  return {
    title: "Rating curve — " + NAMES[arch[0]] + "/" + NAMES[arch[1]],
    hint: NAMES[arch[0]] + "/" + NAMES[arch[1]] + " splits into each mono color, that pair’s hybrid, and cards that require both. Other-pair hybrids you can still pay stay with the matching mono line.",
    series: series,
    table: uniqueCards(series)
  };
}

function lineTraces(series) {
  return series.map(s => ({
    type: "scatter",
    mode: "lines+markers",
    name: s.key,
    x: BINS,
    y: counts(s.cards.map(c => c.rating)),
    line: { color: s.color, width: 2 },
    marker: { color: s.color, size: 7 }
  }));
}
function boxTraces(series) {
  return series.filter(s => s.cards.length).map(s => ({
    type: "box",
    name: s.key,
    y: s.cards.map(c => c.rating),
    text: s.cards.map(c => c.name),
    hovertemplate: "%{text}<br>Rating: %{y}<extra>%{fullData.name}</extra>",
    boxpoints: "all",
    jitter: 0.4,
    pointpos: 0,
    marker: { color: s.color, size: 5, opacity: 0.7 },
    line: { color: s.color },
    fillcolor: s.color
  }));
}

function renderKpis(series) {
  document.getElementById("kpis").innerHTML = series.map(s => {
    const xs = s.cards.map(c => c.rating);
    const ge3 = xs.filter(x => x >= 3).length;
    return `<div class="kpi"><div class="k"><span class="swatch" style="background:${s.color}"></span>${s.key}</div>
      <div class="v">${fmt(mean(xs))}</div>
      <div class="s">n=${xs.length} · median ${fmt(median(xs))} · ≥3.0 ${ge3} (${pct(xs, 3)})</div></div>`;
  }).join("");
}

let sortKey = "rating";
let sortDir = -1;
let tableRows = [];

function drawTable() {
  const q = (document.getElementById("q").value || "").toLowerCase();
  let rows = tableRows;
  if (q) rows = rows.filter(c => (c.name + " " + c.bucket + " " + c.cost).toLowerCase().indexOf(q) >= 0);
  rows = [...rows].sort((a,b) => {
    const av = a[sortKey], bv = b[sortKey];
    if (av < bv) return -1 * sortDir;
    if (av > bv) return 1 * sortDir;
    return 0;
  });
  document.getElementById("count").textContent = "(" + rows.length + ")";
  document.getElementById("tbody").innerHTML = rows.map(c =>
    `<tr>
      <td>${c.url ? `<a href="${c.url}" target="_blank" rel="noopener">${c.name}</a>` : c.name}</td>
      <td>${c.cost}</td>
      <td>${c.rarity}</td>
      <td>${c.bucket}</td>
      <td>${c.rating.toFixed(1)}</td>
    </tr>`
  ).join("");
}

function redraw() {
  const v = view();
  tableRows = v.table;
  document.getElementById("hint").textContent = v.hint;
  renderKpis(v.series);
  Plotly.react("chart", lineTraces(v.series), {
    ...layoutBase,
    title: { text: v.title, x: 0, xanchor: "left", pad: { t: 4, b: 8 } },
    xaxis: { title: { text: "J2SJosh rating", standoff: 10 }, dtick: 0.5, range: [0.3, 5.2] },
    yaxis: { title: { text: "Number of cards", standoff: 8 }, rangemode: "tozero" }
  }, { responsive: true, displayModeBar: false });
  Plotly.react("box", boxTraces(v.series), {
    ...layoutBase,
    showlegend: false,
    hovermode: "closest",
    margin: { t: 56, r: 16, b: 72, l: 52 },
    title: { text: "Rating spread", x: 0, xanchor: "left", pad: { t: 4, b: 8 } },
    xaxis: { automargin: true },
    yaxis: { title: { text: "J2SJosh rating", standoff: 8 }, range: [0, 5.3] }
  }, { responsive: true, displayModeBar: false });
  drawTable();
}

document.querySelectorAll(".rar, #excludeGroup, #arch").forEach(el => el.addEventListener("change", redraw));
document.getElementById("q").addEventListener("input", drawTable);
document.querySelectorAll("th[data-k]").forEach(th => {
  th.addEventListener("click", () => {
    const k = th.dataset.k;
    if (sortKey === k) sortDir *= -1;
    else { sortKey = k; sortDir = k === "rating" ? -1 : 1; }
    drawTable();
  });
});
redraw();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
