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
or another durable archive before expiration. Never place credentials in files.

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

USGS target: World Mine Production in metric tonnes of natural graphite,
excluding reserves and synthetic production. Acquisition and historical table
review are pending in this draft; no mine indicator is fabricated.
