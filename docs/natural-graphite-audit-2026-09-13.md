# Natural graphite audit, 2026-09-13

Draft PR #5. Baseline is main e65d384, after merged lithium PRs #1-#4.
Acquisition run: https://github.com/Latrans2004/999.9/actions/runs/34775388416
All 32 annual final Comtrade queries succeeded. No key was displayed or saved;
Actions injected the existing secret into the request header.
Raw bytes and provenance are retained under `data/review/natural-graphite/`.

| Year | Comtrade rows | Missing usable weight | Estimated weight |
|---|---:|---:|---:|
| 2017 | 2,901 | 25 | 327 |
| 2018 | 2,935 | 47 | 412 |
| 2019 | 2,935 | 19 | 356 |
| 2020 | 2,812 | 5 | 337 |
| 2021 | 2,994 | 6 | 382 |
| 2022 | 2,978 | 18 | 488 |
| 2023 | 2,986 | 47 | 459 |
| 2024 | 2,917 | 47 | 436 |
| Total | 23,458 | 214 | 3,197 |

Counts include World rows and bilateral rows in both flows; they must not be
summed as world volume. Each response passed the cap, count, dimension and
duplicate gates. This establishes query completion, not universal reporting.
Country/territory, aggregate, special area and unknown rows remain in Raw and
normalized data; entity eligibility is reported separately in `entities.json`.
`measurements.json` identifies missing/estimated measurements, zero/value
inconsistencies, entity exclusions and diagnostic unit values.

## Largest discrepancies

| Country/year/HS | Own exports, t | Observed mirror, t | Outcome |
|---|---:|---:|---|
| USA / 2021 / 250490 | 284.128 | 493,125.179 | Unresolved |
| Mozambique / 2022 / 250410 | 647,761.188 | 159,437.596 | Unresolved |
| USA / 2020 / 250490 | 377.214 | 259,187.000 | Unresolved |
| North Korea / 2017 / 250490 | Missing | 126,553.070 | Unresolved |
| China / 2018 / 250490 | 125,815.737 | 41,256.864 | Unresolved |
| UAE / 2023 / 250410 | 1,753.212 | 54,239.853 | Unresolved |
| Mozambique / 2018 / 250410 | 576.188 | 48,815.752 | Unresolved |
| Mozambique / 2024 / 250410 | 35,304.999 | 74,645.966 | Unresolved |

Dominican Republic accounts for 492,941.001 t of the USA 2021 mirror and
259,016.674 t in 2020. These native rows have isReported=false,
isAggregate=true and isNetWgtEstimated=false. Retain those flags; aggregation
is not by itself proof of an invalid commodity record.

USGS 2021 Minerals Yearbook Table 5 (source: US Census Bureau) gives total
natural-graphite exports of 5,920 t in 2020 and 8,670 t in 2021. Footnote 3
explicitly covers both 250410 and 250490. This does not reconcile current
HS-specific revisions, so it cannot replace either Comtrade observation.
The Yearbook PDF is archived under `data/raw/external` in the review archive.
Source: https://pubs.usgs.gov/myb/vol1/2021/myb1-2021-graphite.pdf

USGS MCS production tables give Mozambique 104,000 t (2018), 166,000 t (2022),
39,000 t (2024); North Korea 5,500 t (2017), 6,000 t (2018). Production provides
scale context but is not a bound or substitute for exports because inventories,
timing and re-exports can differ. The INE Mozambique Industrial Statistics 2022
download URL returned 404; no government export reconciliation was obtained.
China and UAE remain pending HS-specific external investigation.

There are 1,384 observed exporter/year/HS decision records: 28 provisional
reported selections, zero mirror selections, 1,356 unresolved. 637 records flag
a weight gap over 25% of the larger observation; 835 have an explicitly observed
export destination absent from the mirror reporter set. Flags overlap.
All mirror sums remain observed subsets, never certified World totals. The
primary USD comparison remains separate: imports usually CIF, exports FOB,
with national valuation exceptions. No universal CIF-to-FOB factor is applied.

## Mine metrics

166 rows include named producers, explicit zero rows, residuals and world totals.
Eight pinned editions cover all eight requested years. Positive named-producer
counts are below; zero-producing USA remains in source records but not HHI.

| Year | HHI | CR3, % | Positive producers | Named/world coverage |
|---|---:|---:|---:|---:|
| 2017 | 5,031.1 | 84.37 | 17 | 99.77% |
| 2018 | 4,022.0 | 79.46 | 20 | 100%* |
| 2019 | 4,263.0 | 82.08 | 19 | 100%* |
| 2020 | 6,301.3 | 88.43 | 17 | 99.93% |
| 2021 | 5,436.8 | 86.46 | 18 | 99.69% |
| 2022 | 5,393.9 | 89.86 | 18 | 99.76% |
| 2023 | 6,314.3 | 89.66 | 18 | 100%* |
| 2024 | 6,764.9 | 91.12 | 18 | 100%* |

*The site's existing coverage function caps ratios at one. Exact rounding
differences remain in production-metrics.json; 100% does not establish a census
of all production. Other is not treated as a single producing country.
USGS e estimates are explicitly retained. These figures describe natural
graphite mine production, not synthetic graphite or all anode materials.

YoY screens flag 2018, 2020 and 2022. Different historical vintages and changes
in reported producer coverage affect comparisons. Especially China's 2022
number in MCS 2024 differs from the earlier MCS 2023 estimate. Do not interpret
the series as uniformly revised historical growth data.

Trade selected-sample metrics are diagnostics only: each year/HS covers less
than 1% of observed reported export weight, with 0-4 positive exporters.
Every trade profile fails the configured population/coverage screen and is
non-publishable. No combined-HS global trade concentration is asserted.

## Validation and publication boundary

77 tests passed locally, including lithium regressions and committed Raw replay. Initial Actions also
passed tests and reproduced the existing HTML exactly. Pinned production tables
were checked as images; Raw replay revalidates hashes and normalized records.
The isolated preview renders the mine series and withholds the trade headline.
No published data, lithium results, site layout or deployment code was changed.

Before publication: reconcile major trade discrepancies using HS-specific
customs evidence; establish reporter/partner and weight coverage; review flagged
mine vintage/YoY differences; review any adoption decision with its exact source.
No additional API secret configuration is currently required.
