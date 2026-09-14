# Petralysis

Supply concentration in critical minerals, measured from open data and published
as a static site on GitHub Pages.

The site takes published production and trade statistics and reduces them to one
number per mineral per year — the Herfindahl–Hirschman Index — at two points in
the chain: where the ore is mined (USGS) and where the material is exported
(UN Comtrade). The front page is a screener: one row per mineral with the mine
index, the largest supplier, a representative export index, the band and the
year, searchable and sortable in the browser and readable as a plain table
without scripts. Each mineral page opens with the same figures as a quote
header before any chart. The first section covers eight battery and
electrification minerals and is laid out for several dozen; a second material
family is a catalog category and a fetch adapter, not a new site.

Formerly Orelysis; renamed in September 2026. See
[docs/task-f-redesign-2026-09.md](docs/task-f-redesign-2026-09.md) for the
rename, the design tokens and the screener rules.

---

## Getting it running

### Lithium automatic updates

Lithium now has a strict weekly update pipeline. Start with
[the lithium operations guide](docs/lithium-pipeline.md) for API authentication,
reviewed USGS updates, raw archives, Excel comparisons and validation gates.
Run **Update lithium data** in Actions. Complete bilateral retrieval requires
`COMTRADE_API_KEY`; it deliberately does not publish truncated preview data.
`python -m pipeline.build --only lithium` also uses this strict path.
The legacy **Refresh data** workflow is now manual-only for other minerals.

### Natural graphite publication

Run `python -m pipeline.publish_graphite` (or `python -m pipeline.build --only natural-graphite`)
to replay the reviewed 2017–2024 mine series from committed Raw. No key is needed.
Trade concentration stays under review. Changed production inputs require a new review;
failed updates retain accepted data. See [Task D publication](docs/natural-graphite-publication-2026-09-14.md)
and [Task E rollout](docs/task-e-mineral-rollout.md).

### 1. Push it

```bash
git init
git add .
git commit -m "petralysis: initial site and pipeline"
git branch -M main
git remote add origin https://github.com/<you>/petralysis.git
git push -u origin main
```

### 2. Set three values in `site.json`

```json
{
  "repo_url": "https://github.com/<you>/petralysis",
  "site_base": "/petralysis/",
  "site_url": "https://<you>.github.io/petralysis/"
}
```

`repo_url` fills the footer links. `site_base` is only used by `404.html`, and it
must match how Pages serves the site: `/petralysis/` for a project page at
`<you>.github.io/petralysis/`, or `/` for a user page or a custom domain.
`site_url` is the absolute origin used for canonical links and the Open Graph
image; leave it empty to omit both.

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

### 5. A UN Comtrade key

For the legacy adapters of other minerals, without a key the pipeline uses Comtrade's free preview endpoint, which caps a
response at 500 rows. That is usually enough for one commodity code in one year,
but not always. A free key from
[comtradedeveloper.un.org](https://comtradedeveloper.un.org/) lifts the cap: add
it as a repository secret named `COMTRADE_API_KEY` and the adapter switches
endpoints on its own.

Lithium instead requires a key and treats row caps as a failed update.
Its strict adapter requests at most 100,000 rows per query; access limits depend
on the subscription. An authenticated endpoint is not an uncapped endpoint.

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
index.html                      the screener (every mineral, every category)
404.html
assets/                         css, js, images — shared by every section
  brand/petralysis-master.png   the one brand image everything else is cut from
  img/                          favicon, icons, header mark, OGP card (generated)
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
  templates/                    Jinja2 (_screener.html is shared by the hub and the section)
  tests/                        unit tests for hhi.py, the stage tabs and the screener
tools/make_brand_assets.py      regenerates assets/img/ from the brand master
site.json                       repo URL, Pages base path, absolute site URL
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
  "category": "battery-metals",
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

Then `python -m pipeline.build --only tin`. The page, the screener row and the
JSON all follow from the catalog entry; nothing else needs editing. `category`
must name a key of the top-level `categories` map, which is what the screener's
category filter reads. A mineral measured at several trade stages may add
`headline_trade_stage` (an HS code from its stage list) to say which stage the
screener's Export HHI column quotes; without it the column links to the page
instead of picking one. A trade block whose `publication_status` is
`under_review` never reaches the screener as a number.

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
and give its minerals a new `category`. The screener on the hub absorbs the new
family as a category rather than a card. The templates, CSS and chart code are
shared.

## Brand assets

Every icon, the header mark and the Open Graph card are derived from
`assets/brand/petralysis-master.png`:

```bash
pip install -r tools/requirements-brand.txt
python tools/make_brand_assets.py
```

Replace the master and re-run; nothing else references the artwork directly.
The committed master is a synthesized stand-in until the final artwork lands.

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

The legacy adapters do not estimate, interpolate or impute a missing figure.
A source that fails produces an empty state on the page and a note in the build
output, which is the intended behaviour.

The strict lithium path instead preserves accepted data and exits nonzero on
failure. Its separate weight-analysis output records the pre-existing Excel
estimates and unverified corrections explicitly; these do not alter the site's
reported-USD headline. See the lithium guide before interpreting them.

---

## Data and credit

The isolated [manganese ore audit](docs/manganese-pipeline.md) covers HS260200,
with strict Raw replay, diagnostic-only production references, and a separate
human-review boundary. It does not publish data. See the
[2026-09-14 validation report](docs/manganese-audit-2026-09-14.md) for the retained
public-API sample, tests, and unresolved evidence requirements.
The [historical-data validation report](docs/manganese-history-2026-09-14.md)
adds 2017–2024 trade observations, BGS production vintages, and revision checks.

Mine production: [USGS Mineral Commodity
Summaries](https://www.usgs.gov/centers/national-minerals-information-center/mineral-commodity-summaries),
National Minerals Information Center.
Trade: [UN Comtrade](https://comtradeplus.un.org/).

Both are public. The calculations, the choices and any errors here are the
author's; neither organisation endorses or is associated with this project.

Code is MIT licensed. See `LICENSE`.
