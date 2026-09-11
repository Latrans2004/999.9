# 999.9

Supply concentration in critical minerals, measured from open data and published
as a static site on GitHub Pages.

The site takes published production and trade statistics and reduces them to one
number per mineral per year — the Herfindahl–Hirschman Index — at two points in
the chain: where the ore is mined (USGS) and where the material is exported
(UN Comtrade). The first section covers eight battery and electrification
minerals. The structure is built so that a second material family is a catalog
file and a fetch adapter, not a new site.

---

## Getting it running

### 1. Push it

```bash
git init
git add .
git commit -m "999.9: initial site and pipeline"
git branch -M main
git remote add origin https://github.com/<you>/999.9.git
git push -u origin main
```

### 2. Set two values in `site.json`

```json
{
  "repo_url": "https://github.com/<you>/999.9",
  "site_base": "/999.9/"
}
```

`repo_url` fills the footer links. `site_base` is only used by `404.html`, and it
must match how Pages serves the site: `/999.9/` for a project page at
`<you>.github.io/999.9/`, or `/` for a user page or a custom domain.

Then re-render so the change reaches the HTML:

```bash
python -m pipeline.render
```

### 3. Turn on Pages

Repository → Settings → Pages → **Source: GitHub Actions**. The `Test and deploy`
workflow runs on every push to `main` and publishes the site.

### 4. Run the pipeline once

Actions → **Refresh data** → *Run workflow*. This is the run that turns the
"awaiting first build" placeholders into real figures. It commits the JSON and
the regenerated pages, then redeploys.

### 5. Optional: a UN Comtrade key

Without a key the pipeline uses Comtrade's free preview endpoint, which caps a
response at 500 rows. That is usually enough for one commodity code in one year,
but not always. A free key from
[comtradedeveloper.un.org](https://comtradedeveloper.un.org/) lifts the cap: add
it as a repository secret named `COMTRADE_API_KEY` and the adapter switches
endpoints on its own.

---

## Working on it locally

```bash
pip install -r pipeline/requirements.txt

python -m pytest pipeline/tests -q      # the index arithmetic
python -m pipeline.render               # regenerate pages from existing JSON
python -m pipeline.build                # fetch, compute, then render
python -m pipeline.build --only lithium cobalt
python -m pipeline.build --fixtures     # synthetic data, for layout work
python -m http.server -d . 8000         # then open http://localhost:8000
```

`--fixtures` fills every page with deterministic synthetic numbers so you can
work on layout without a network. Pages built that way carry a "Sample data"
banner on every screen, and `critical-minerals/data/index.json` records
`"fixtures": true`. **Never commit a fixtures build** — `git checkout
critical-minerals/data && python -m pipeline.render` puts it back.

Responses are cached under `.cache/` for a day, so re-running the pipeline while
you fix a parser is fast and does not re-hammer the upstream services.

---

## Layout

```
index.html                      the 999.9 hub
404.html
assets/                         css, js, images — shared by every section
critical-minerals/              section 01, self-contained
  index.html                    generated
  methodology.html              generated
  about.html                    generated
  minerals/<slug>.html          generated, one per catalog entry
  data/
    catalog.json                hand-written: the minerals, HS codes, copy
    index.json                  generated: the summary the section page reads
    minerals/<slug>.json        generated: the full record per mineral
    manual/world_production.csv fallback production table, empty by default
pipeline/
  hhi.py                        the index arithmetic, source-agnostic, tested
  sources/usgs.py               ScienceBase discovery + tolerant table parsing
  sources/comtrade.py           annual exports by reporter
  sources/http.py               retries, throttling, on-disk cache
  build.py                      orchestration, writes the JSON
  render.py                     JSON + templates -> static HTML
  fixtures.py                   synthetic data for layout work
  templates/                    Jinja2
  tests/                        unit tests for hhi.py
site.json                       repo URL and Pages base path
```

Every HTML file in the repository is generated. Edit the templates in
`pipeline/templates/`, not the output — CI fails a push whose committed pages
differ from a fresh render.

---

## Adding a mineral

Add an entry to `critical-minerals/data/catalog.json`:

```json
{
  "slug": "tin",
  "name": "Tin",
  "symbol": "Sn",
  "role": "Solder",
  "summary": "…",
  "usgs_commodity": "Tin",
  "usgs_aliases": ["Tin"],
  "hs_codes": ["260900", "800110"],
  "hs_label": "Tin ores (2609.00) and unwrought tin (8001.10)",
  "trade_stage": "ore and unwrought",
  "caveats": ["…"]
}
```

Then `python -m pipeline.build --only tin`. The page, the card and the JSON all
follow from the catalog entry; nothing else needs editing.

For the Japanese side of the page, add `name_ja`, `role_ja`, `summary_ja`,
`hs_label_ja` and a `caveats_ja` list the same length as `caveats`. A missing
`*_ja` field is not an error: that text simply stays in English when the
Japanese toggle is on.

## Language toggle

Every page is rendered once, in English, and carries its Japanese text
alongside it. The EN / 日本語 buttons in the header swap between the two
client-side with `assets/js/i18n.js`; nothing is translated at runtime, and
URLs do not change. The choice is remembered per browser, and a browser whose
preferred language is Japanese opens in Japanese the first time.

Where the Japanese lives:

| Text | Put the Japanese in |
|---|---|
| Repeating UI chrome — nav, footer, table headers, band labels | `pipeline/i18n.py`, `STRINGS_JA`, referenced as `data-i18n="key"` |
| One-off strings, or any string with a number in it | inline on the element, `data-i18n-text="…"` |
| Long prose with links or `<code>` (Methodology, About) | a parallel block, `data-lang-only="en"` / `data-lang-only="ja" hidden` |
| Per-mineral copy | `*_ja` fields in `catalog.json` |
| Sentences built from data (trend, coverage, timestamp) | a `*_ja` function in `pipeline/i18n.py`, next to its English twin in `render.py` |

Country names and organisation names (USGS, UN Comtrade) are deliberately not
translated: they stay as the source reports them in both languages. Pipeline
build notes are also English-only.

The English text in a template is the fallback. If a key or an inline
translation is missing or empty, the element keeps its English rather than
going blank, so a half-translated page degrades instead of breaking. After
editing any of the above, run `python -m pipeline.render` and commit the
regenerated pages, as with any other template change.

## Adding a section

Copy `critical-minerals/` to a new directory with its own `data/catalog.json`,
point `SECTION_DIR` in `build.py` and `render.py` at it (or parameterise them),
and add a card on the hub page. The templates, CSS and chart code are shared.

---

## When something breaks

The upstream schema most likely to drift is the USGS data release. To see what
the discovery step actually found:

```bash
python -m pipeline.sources.usgs --inspect
```

That prints the release it selected, its attached files, and a count of records
per commodity name after parsing. If a commodity shows zero records, either its
alias list in the catalog needs a new spelling or the file layout changed. As a
stopgap, transcribe the figures into
`critical-minerals/data/manual/world_production.csv` — the pipeline reads it
whenever automatic parsing produces nothing for a commodity.

Nothing in this repository estimates, interpolates or imputes a missing figure.
A source that fails produces an empty state on the page and a note in the build
output, which is the intended behaviour.

---

## Data and credit

Mine production: [USGS Mineral Commodity
Summaries](https://www.usgs.gov/centers/national-minerals-information-center/mineral-commodity-summaries),
National Minerals Information Center.
Trade: [UN Comtrade](https://comtradeplus.un.org/).

Both are public. The calculations, the choices and any errors here are the
author's; neither organisation endorses or is associated with this project.

Code is MIT licensed. See `LICENSE`.
