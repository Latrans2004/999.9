# Lithium pipeline integration plan

Baseline: bf8bca9 (remote main, includes EN/JA switch). Desktop checkout is older
at 221e0d9 and clean; implement in an isolated checkout, without changing it.

## Existing flow and compatibility

`catalog.json -> pipeline.build -> sources -> hhi -> data/minerals/*.json +
index.json -> pipeline.render -> Jinja2 -> committed HTML -> deploy.yml`.
Existing HHI is 0–10,000, CR3 is percent; trade is **reported USD export value**
summed over 283691 and 282520. Keep that definition and all existing pages,
styles, scripts, bilingual text, CR1/CR5/effective-supplier/coverage metrics.

Excel (2026-09-12, 36 sheets) is a reference, never a runtime input. It uses
**tonnes**, country-specific corrections and separate ore/chemical stages.
HS253090 is not exclusively lithium and must not enter the existing refined
export-value headline. Port its side-specific classification separately.
Carbonate mirrors are restricted to the producer/refiner allowlist, with ARG
correction at >1.15 and reported tonnes <1 replacement. Hydroxide has anchor
price filtering and country switches (Japan off, Australia on/unverified).
Historical supplementary values must have explicit provenance; never infer
new estimates from incomplete descriptions in workbook prose.

## Implementation sequence

1. Add small configured modules alongside the existing pipeline: immutable raw
   archive, strict Comtrade normalization, country registry, traceable stage
   processing, validation and transactional orchestration.
2. Keep exact upstream response bodies and query/time/hash sidecars. Reject
   API errors, empty/truncated responses, unexpected dimensions and duplicates.
3. Separate USGS source acquisition from reviewed production CSV ingestion;
   never use the legacy tolerant multi-commodity parser for this strict path.
4. Generate processed audit JSON/CSV and existing-compatible lightweight site
   JSON, validate against the previous accepted snapshot, stage rendering in a
   temporary copy, and publish only a fully successful batch.
5. Route lithium through the strict path, leave other minerals' source behavior
   intact. Replace the overlapping refresh schedule with a weekly lithium job.
6. Add arithmetic, normalization, selection, missingness, anomaly, retention,
   idempotency, render and Excel-reference regression checks.
7. Document API limits, secrets, USGS review workflow, extension, and observed
   differences from Excel. Deliver a reviewable patch and implementation.
