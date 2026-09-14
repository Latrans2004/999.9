# Natural graphite: can mine output adjudicate a disputed export figure?

Follow-up to the 2026-09-13 audit. That run left 1,356 of 1,384 exporter/year/HS
records unresolved and every trade profile non-publishable. This note records why
a universal screening rule cannot close that gap, and what narrows it instead.

Nothing here selects a weight or changes published data. `graphite_anchor.audit`
writes `anchor.json` beside the other review artifacts.

## Two rules that do not work

**Reported divided by mine output, against a threshold.** Germany mines 140-800 t
a year and reports 15,000-21,000 t of exports, a ratio of 20-130. The mirror
agrees with it. Germany is a processing and re-export hub, so the ratio is real
and a threshold set low enough to catch Mozambique 2022 (ratio 3.91) rejects
correct data from every hub.

**Whichever observation sits closer to mine output.** India mines 35,000 t and
reports 450 t of exports because it consumes its own production. Pakistan,
Vietnam and Korea behave the same way. For a domestic consumption producer,
mine output says nothing about which export observation is right, so proximity
to it is not evidence.

Mine output anchors only an export oriented producer: one that ships most of
what it mines. That is a narrow class, and it has to be identified rather than
assumed.

## What the classifier does

For each country and year `classify` compares both trade observations against
mine output and returns a review class. A case is `production_adjudicable` only
when exactly one of the two observations falls in 0.5-1.5x mine output and the
two observations disagree by more than the existing 25% screen. Both sides
outside the band means a hub (both above) or a domestic consumption producer
(both below); both sides inside means mine output does not separate them.

| Review class | Country-years |
|---|---:|
| no_mine_production | 700 |
| no_dispute | 62 |
| incomplete_trade_observation | 25 |
| domestic_consumption_producer | 20 |
| reexport_hub | 15 |
| **production_adjudicable** | **14** |
| production_cannot_adjudicate | 9 |

845 country-years reduce to 14 candidates for external review.

## The two Mozambique cases

| Year | Reported | Mirror | USGS mine output | Favours |
|---|---:|---:|---:|---|
| 2022 | 648,262 t | 159,438 t | 166,000 t | mirror |
| 2024 | 35,305 t | 74,768 t | 39,000 t | reported |

The direction of the disagreement reverses between the two years, which is why
no mirror-only rule can settle either. Balama is effectively all of Mozambique's
output and its nameplate capacity is about 350,000 t/y, so the 2022 reported
figure is not physically attainable.

Syrah Resources disclosed 163,000 t produced and 162,000 t sold at Balama in
2022, and Mozambican output fell sharply in 2024 after the operation stopped and
force majeure was declared. Both agree with the classifier's blind reading of the
committed data. **These figures came from press coverage, not from Syrah's own
filings, so they are not recorded as review evidence.** Every entry in
`graphite_reviews.json` cites a primary document with an exact locator, and these
do not yet meet that standard.

## Deliberately not changed

`attach_reviews` forces `unresolved` for any record carrying an external review,
and `test_external_context_does_not_substitute_mine_output` pins that behaviour
using Mozambique 2022 itself. It is a tested safety property, not an oversight.
Relaxing it without decisive evidence to put through the opening would only
remove a guarantee, so it stands.

The same applies to the unconditional `publishable = False` in
`graphite_usgs.py` and in `status.json`.

## What would actually close the gap

Reported export weight for 2017-2024 concentrates as follows.

| Group | Share of reported export weight |
|---|---:|
| China | 46.3% |
| Mozambique, Madagascar, Tanzania | 35.1% |
| Re-export hubs | 8.1% |
| Everything else | 10.5% |

The top four exporters carry 82.8%, so per-country curation is tractable at the
same scale lithium already runs: `process_trade.py` resolves lithium through
named `mirror_allowlist`, `underreported_country` and `missing_mirror_countries`
rosters, each backed by a cited source, and carries residual doubt into the
output as `unverified`. Lithium ships because its selection is curated and
evidenced, not because its data is cleaner.

## Acquiring the evidence

The audit sandbox cannot reach the operators' sites, but Actions can, and the
pipeline already fetches USGS PDFs that way. `graphite_companies` follows the
same shape: `discover` archives each listed primary document and reports its
hash, a reviewer reads the document and pins that hash in
`graphite_company_sources.json`, and only then may figures be entered in
`data/manual/natural-graphite-company-disclosures.csv`. `load` refuses any row
whose source is unpinned, and `verify_archived` fails closed when a pinned
document's bytes change.

The committed CSV holds a header and no rows. Press coverage put Balama at
163,000 t produced and 162,000 t sold in 2022, which agrees with the classifier,
but no figure is entered until it comes from a filing with an exact locator.

The discovery job is separate from the audit job and is given no Comtrade
secret, because it fetches third-party sites. It runs on manual dispatch only.
Exact report URLs are added to the manifest after discovery rather than guessed;
the seeds are announcement indexes.

Three sources would supply the missing evidence, none of them reachable from the
audit sandbox under the current network policy:

- Syrah Resources and NextSource Materials filings, for the 14 adjudicable cases
- US Census Schedule B detail, for USA 250490 in 2020 and 2021
- China customs at eight digits, which separates flake (25041010) from spherical
  graphite (25041091) and would address both the 250490 discrepancy and the
  battery-grade caveat already stated in the site catalog

China's December 2023 export controls cut flake exports 77.7% year over year in
January-February 2024. That is a policy discontinuity and needs an explicit note
wherever the series is eventually published.
