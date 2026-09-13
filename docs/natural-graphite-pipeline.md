# Natural graphite audit (draft)

Baseline: main e65d384, after merged PRs #1 (lithium), #2 (entities),
#3 (lithium 253090/2019 exception), #4 (hermetic regression fixture).
No unmerged dependency. Lithium selection policies and public data are unchanged.

Scope is natural graphite, 2017-2024. It is not total battery anode supply.
UNSD definitions: [250410 powder/flakes](https://unstats.un.org/unsd/classifications/Econ/Detail/EN/32/250410)
and [250490 other forms](https://unstats.un.org/unsd/classifications/Econ/Detail/EN/32/250490).
Artificial graphite 380110 is excluded. These codes do not identify battery grade
or uniquely distinguish all geological graphite types.

[Net weight is kg; supplementary unit 8 is kg](https://uncomtrade.org/docs/supplementary-quantity-units/).
Convert kg to metric tonnes by dividing by 1000, retaining native quantities and
estimation flags. Missing is null, never zero. No price-derived weight estimates.
[Import values usually CIF, exports FOB](https://uncomtrade.org/docs/trade-valuation/);
country exceptions exist, and primaryValue is retained with native CIF/FOB fields.
No universal freight adjustment is applied. Value discrepancies are diagnostic.

Run `python -m pipeline.graphite`. The authenticated final annual API supplies
32 independent queries (year / HS / X or M), with all reporters and partners.
The existing strict normalizer rejects caps, duplicate keys, wrong dimensions,
count mismatches, and invalid numbers; raw responses have SHA256 and provenance.
Failed queries remain listed. Entity identity and metric eligibility use the
existing country/territory/aggregate/special-area registry without lithium lists.

Output defaults to `.cache/graphite-audit/`. Nothing writes public JSON or HTML.
The dedicated Actions job has read-only permissions, no commit or deploy step,
and retains artifacts for 90 days. Raw artifacts must be retained in the draft PR
or another durable archive before expiration. This PR retains the observations
in `data/review/natural-graphite/`, outside the public site. Never place credentials in files.

Compare each exporter World row with imports naming it as partner. Mirrors are
observed reporter sums, never certified world totals. Explicit destinations
absent from mirrors, missing or estimated weights, and a weight gap greater
than 25% of the larger observation trigger unresolved review. This is a
transparent screening rule, not an accuracy tolerance or correction formula.
It is independent of lithium thresholds. No larger-value substitution exists.
Reported weights passing screening are provisional observed-sample choices,
not externally verified world supply estimates. Mirror selection requires
specific external evidence and is not automatic.

HHI/CR3 are per HS and year on accepted observed net weights. Coverage is against
available reported export weight only, not global trade. Missing global coverage
stays null. YoY totals, HHI, and country counts are review diagnostics; every
result is marked non-publishable until USGS, external decisions, completeness,
and year-over-year quality review are complete.

USGS: World Mine Production in metric tonnes of natural graphite, excluding
reserves and synthetic production. Eight PDFs (MCS 2019-2026) were acquired;
each first production column supplies edition minus two (2017-2024). All eight
tables, year headers, numeric columns, and zero/estimate footnotes were visually
reviewed. The pinned `graphite_usgs_sources.json` records URL, edition, SHA256,
and review date. Changed PDF bytes fail closed after archiving the new response.
`graphite_usgs.py` rejects unrecognized rows, duplicate countries, wrong years,
or a missing world total. USGS explicitly defines the dash as zero in these
tables; W/NA remain null. An `e` flag is retained, not silently stripped.
Other is excluded from HHI but included in the reconciliation of country totals.
The 1% country-plus-residual/world tolerance covers published rounding and is
not a license to fill unreported countries. The unclipped rounding residual is
recorded alongside the site's conventional capped coverage ratio.

These are fixed historical source vintages, not a claim to incorporate every
later retrospective revision. Especially 2019-2021 country changes and the large
China revision need care when interpreting trends. Numerical YoY screens flag
total changes outside 0.7-1.3 and HHI changes over 1,000 for review; no threshold
is borrowed from the lithium configuration and no exception is auto-approved.
No production or trade output from this audit is automatically publishable.

External reviews in `graphite_reviews.json` supply contextual USGS evidence for
the USA, Mozambique, and North Korea discrepancies. Contextual mine output or
two-HS export totals do not justify an HS-specific replacement. These cases
remain unresolved. China and UAE discrepancies still lack a reconciled annual
HS-specific customs source. All records include a decision, reason, Raw paths,
and any external review. No mirror value was adopted in this run.

Reproduce the entire audit from committed Raw without credentials:

```sh
python -m pipeline.graphite --replay data/review/natural-graphite/bundle.json --output .cache/graphite-replay --replay-usgs
```

Replay automatically copies the archived Raw into its isolated output directory.
Trade replay checks each response
hash, re-normalizes it and compares all records against the bundle. USGS replay
checks pinned hashes and parses the reviewed production columns again.
To refresh live, run the dedicated Actions audit. It is never a deployment.

`python -m pipeline.graphite_preview --audit data/review/natural-graphite` creates
an isolated static preview under `.cache/graphite-preview`. The mine series is
rendered with the existing site templates; the trade headline is unavailable.
It does not write the published site's files or change lithium computations.

See [the acquisition report](natural-graphite-audit-2026-09-13.md) for counts,
discrepancies, metrics and outstanding publication issues.
