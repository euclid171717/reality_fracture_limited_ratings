# Reality Fracture (FRA) Limited Ratings — J2SJosh

A spreadsheet of every Reality Fracture card J2SJosh rated in his seven-part
[MTG Arena Zone Limited set review](https://mtgazone.com/limited/). It includes his exact
numerical rating (out of 5), his commentary, and card metadata checked against Scryfall.

## Output files (`output/`)

| File | What it is |
| --- | --- |
| `fra_j2sjosh_limited_ratings_simple.csv` | Compact CSV: name, color, mana cost, mana value, rarity, type, P/T, rating, Scryfall link, image link. Sorted by rating. |
| `fra_j2sjosh_limited_ratings.csv` | Full CSV with all columns, including commentary and source article. Sorted by collector number. |
| `fra_j2sjosh_limited_ratings.xlsx` | Same as the full CSV with a card image embedded in each row, plus filters and a frozen header. |
| `verification_report.json` | Counts, duplicates, warnings, and cards in the set that weren't reviewed. |
| `fra_j2sjosh_classified.csv` | Copy of useful rating columns plus cast classification (`Cast Bucket`, `Required Colors`, `Hybrid Colors`) and a pipe-wrapped `Archetypes` list. The original ratings CSV is not modified. |
| `fra_archetype_membership.csv` | Long form: one row per card × playable color combination. Filter `Archetype Code` (for example `WU`) to see a pair’s pool. |
| `fra_color_ratings.html` | Interactive report (rating curves, playable depth, card table). Open the file in a browser; no server needed. |

## How the data is built

- **Ratings and commentary** come from each card's `Rating: X/5` heading and the paragraphs
  under it. Ratings are copied exactly as written and never converted to letter grades.
- **Card identity** comes from the Scryfall image ID embedded in each article's card block.
  If an article shows an older printing, as with some reprints, the card is matched to its
  FRA printing by name.
- **Metadata** comes from Scryfall's FRA printing of each card: name, mana cost, mana value,
  color, color identity, rarity, type, power/toughness/loyalty, and image. Mana value is also
  recomputed from the mana cost using the Comprehensive Rules (X counts as 0, hybrid `{2/W}`
  counts as 2, Phyrexian counts as 1) and checked against Scryfall. Color is checked against
  the colored symbols in the mana cost.
- **"Prepare" cards** (a creature with an attached spell, such as
  `Blossom-Blessed Angel // Seed Suture`) use the creature half for mana cost, mana value,
  color, type, and P/T, matching how the card works outside the stack. The spell half's name,
  cost, and type are in the `Second Half*` columns. `Color Identity` is listed separately
  because it includes the spell half, while `Color` does not.
- **Group ratings.** The review rates "Planeswalker Lands" (10 cards) and "Rare Slow Lands"
  (5 cards) as groups. Every card in a group gets that group's rating, noted in the
  `Rating Note` column.
- **Duplicates** are detected by Scryfall oracle ID, so each card gets exactly one row.

## Regenerate

Requires Python 3.10+.

```bash
pip install -r requirements.txt
python scripts/build_fra_sheet.py            # uses cached pages in .cache/ if present
python scripts/build_fra_sheet.py --refresh  # re-download articles and Scryfall data
python scripts/build_fra_sheet.py --no-images  # skip embedding images in the .xlsx
python scripts/build_color_dashboard.py        # classified CSVs + interactive HTML from the ratings CSV
```

### Color analysis (shareable)

`scripts/build_color_dashboard.py` reads `output/fra_j2sjosh_limited_ratings.csv` and writes the classified CSVs plus `fra_color_ratings.html`. It does not change the source sheet.

Classification uses mana pips on both faces (Prepare cards included):

- A hard pip `{W}` must be paid with White.
- A hybrid pip `{W/U}` can be paid with White or Blue.
- `{2/W}` does not require White.
- Lands with no pips use color identity (a WU dual belongs to White/Blue and its supersets; a colorless land belongs to every archetype).

The HTML is one page: pick **All**, a single color, or a two-color pair. The rating curve (lines), summary numbers, and card list all follow that filter, plus rarity. Recipients should download and open the HTML locally (Drive/Dropbox preview often will not run it). Charts work offline.
