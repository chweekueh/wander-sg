# wander.sg

A Singapore discovery site (side project). Static website + a weekly data pipeline. Free to run.

## How it works

```
Every Monday 03:17 SGT (or when you press "Run workflow"):
  OpenStreetMap  ─┐
  NEA hawkers    ─┼─► scripts/build_data.py ─► site/data/places.json ─► GitHub Pages (your live site)
  NEA closures   ─┤                            site/data/events.json
  your sheet     ─┘   (data/manual_listings.csv — your rows always win)
```

- No server, no database, no paid services.
- If a data source is down or returns too little, the build stops and **the previous version stays live**.
- Google ratings and opening hours are **not** stored. They will load live in the browser once a Google Maps key is added (next phase).

## One-time setup (about 15 minutes)

1. **Create a free GitHub account** at github.com if you don't have one.
2. **Create a new repository** (the "+" menu → New repository). Name it e.g. `wander-sg`. Public is fine and keeps GitHub Pages free.
3. **Upload this folder's contents**: on the empty repo page choose "uploading an existing file", then drag in the `site`, `data`, `scripts` and `tests` folders and `README.md`. Commit.
   Then add the schedule file (hidden folders don't drag well): Add file → **Create new file**, type the name `.github/workflows/update-site.yml`, paste in the contents of `update-site.yml` from this folder, and commit.
4. **Turn on GitHub Pages**: repo → Settings → Pages → under "Build and deployment", set Source to **GitHub Actions**.
5. **Run it the first time**: repo → Actions tab → "Update data and publish site" → **Run workflow**. It takes 2–5 minutes.
6. Your site is at `https://<your-username>.github.io/wander-sg/` (Settings → Pages shows the exact link).

If step 5 fails, open the run, copy the red error text, and send it to Claude.

## Everyday use

**Fix or add a place** — edit the Listings sheet, download it as CSV (in the sheet page), and replace `data/manual_listings.csv` in the repo (Add file → Upload files). The site rebuilds automatically within a few minutes.

Rules for the sheet:
- Keep the column headings as they are.
- `Category` is one of: Eat, See, Shop, Do & Outdoors.
- `Latitude` / `Longitude` are required (right-click a spot in Google Maps to copy them).
- `Attributes` are space-separated words from: `indoor outdoor family dog access business date late veg groups`.
- `Price`: `Free`, `$`, `$$`, `$$$` or `$$$$`.
- If your row is the same place as one from OpenStreetMap or NEA (same name, within 200 m), your values replace theirs.
- Delete the four "Sample listing" rows before launch — they're fictional.

**Add an event** — add a row to `data/events.csv`:

| Column | Example |
|---|---|
| Name | Night market at Tiong Bahru |
| Type | `concert`, `exhibition`, `market` or `workshop` |
| Venue ID | an ID from the sheet, e.g. `tiong-bahru-market` (or leave blank and fill Venue name + Latitude + Longitude) |
| Start date / End date | `2026-12-05` (end date optional) |
| Time | `6pm–11pm` |
| Price | `Free`, `$`, `$$` … |
| Attributes | `outdoor family` |
| Description | One or two sentences in your own words |
| Ticket link / Source link | official page URL |

Events disappear from the site automatically after their end date.

## Running costs

| Item | Cost |
|---|---|
| GitHub repo, Actions, Pages | Free for a public repo |
| OpenStreetMap, data.gov.sg | Free (credit shown on the site) |
| Own domain (optional) | ~S$15–25 / year |
| Google Maps + ratings (next phase) | Free within Google's monthly allowance; set a hard spending cap |

## Files

| Path | What |
|---|---|
| `site/index.html` | The whole website |
| `site/data/` | Built data (generated — don't edit by hand) |
| `data/manual_listings.csv` | Your listings and corrections |
| `data/events.csv` | Your events |
| `scripts/build_data.py` | The pipeline |
| `tests/` | Offline test data (`python tests/make_fixtures.py && python scripts/build_data.py --offline tests/fixtures --out /tmp/out`) |
| `.github/workflows/update-site.yml` | The weekly schedule |

## Attribution

Map data © OpenStreetMap contributors (ODbL). Hawker data: NEA via data.gov.sg (Singapore Open Data Licence). Coastline drawing: OpenStreetMap via geo-maps (MIT code).
