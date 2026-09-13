# Comtrade entity audit — 2026-09-13

## Execution evidence

* Initial inventory: [run 34764911227](https://github.com/Latrans2004/999.9/actions/runs/34764911227), 48/48 queries, 57,107 rows.
* After the entity fix: [run 34765355337](https://github.com/Latrans2004/999.9/actions/runs/34765355337), 48/48 fetched and strictly normalized, 57,107 rows, no unresolved entities.
* The second run's event SHA is the prior audit commit, but its checkout log explicitly records **eec94aa9f505f6db4ceaeea646fb52f6f8788e58** and its test step passes all 60 tests in that revision. The workflow now pins checkout to the event SHA to prevent this discrepancy.
* HTTP 429 responses were retried successfully. Counts below exclude retries. Raw bytes, query metadata and logs are retained in each run's `lithium-observations-<run id>` artifact (90 days).
* The corrected run fetched/verified USGS and computed 42 concentration profiles, then correctly failed the existing publication gate: `('253090', 2019): too few countries (2)`. No data commit or Pages deployment occurred.

| HS | X queries / rows | M queries / rows |
|---|---:|---:|
| 253090 | 8 / 18,346 | 8 / 21,897 |
| 283691 | 8 / 4,077 | 8 / 4,971 |
| 282520 | 8 / 3,246 | 8 / 4,570 |

Period: 2017–2024. All requests use annual goods, partner2=0, customs=C00, mot=0, classic breakdown and a 100,000-row cap. No response reached that cap.

## Inventory

The old ISO adapter cannot resolve these eight ISO/name pairs. Seven were already discarded by the old numeric exclusion set; **ATB is the newly blocking entity**. Counts are dimension occurrences, not unique transactions: S19 can occur as both reporter and partner.

| ISO field (trimmed) | Description | Numeric code | Occurrences | New kind |
|---|---|---:|---:|---|
| ATB | Br. Antarctic Terr. | 80 | 2 | territory |
| A79 | LAIA, nes | 473 | 1 | special_area |
| E19 | Other Europe, nes | 568 | 105 | special_area |
| S19 | Other Asia, nes | 490 | 1,275 | special_area |
| X1 | Bunkers | 837 | 19 | special_area |
| X2 | Free Zones | 838 | 19 | special_area |
| XX | Special Categories | 839 | 8 | special_area |
| _X | Areas, nes | 899 | 218 | special_area |

The original trailing spaces in X1/X2/XX/_X remain in provenance. Source: [Comtrade partner-area registry](https://comtradeapi.un.org/files/v1/app/reference/partnerAreas.json). `isGroup=false` does not imply an ISO country; ATB and special statistical categories both have this flag.

## ATB and metric impact

ATB is retained as `CT:80`, a territory with its own identity, not an aggregate, GBR or ATA. Recognized territories are eligible at the entity layer; commodity selection remains independent.

| Year | Import reporter | HS | Weight (t) | USD | Weight estimated |
|---|---|---|---:|---:|---|
| 2017 | Peru | 253090 | 0.016320 | 184.280 | false |
| 2018 | Japan | 253090 | 15.309174 | 2,896.234 | true |

Total observed weight: 15.325494 t; observed value: USD 3,080.514. These are mixed-HS import observations, not evidence of lithium production. Both remain visible as ATB mirror observations, but lack selected reported export weight and do not pass the existing ore inclusion policy.

There is no successfully accepted strict production snapshot on main to compare with. The explicit counterfactual comparison is therefore **the same raw responses processed by the original main code, after omitting ATB only**. All other old exclusions and selection rules are unchanged in this comparator.

Across 42 profiles (32 stage/China-import, 8 USD headline, 2 USGS production), maximum absolute HHI difference is **0**, maximum absolute CR3 difference is **0 percentage points**. Per-profile results are in [comparison JSON](comtrade-entity-comparison-2026-09-13.json). This does not claim agreement with every historical Excel cell or with a previously published full dataset.

The Excel method regression still checks the original spreadsheet population, including S19. The production population excludes S19 as the old strict fetcher did. Entity-policy tests separately check exclusion before mirrors, partner-sum recovery and headline calculations.

## Implementation and remaining gate

Identity resolution preserves raw identifiers and names, distinguishes country/territory/aggregate/special_area/unknown, and uses numeric Comtrade keys for non-ISO identities. Metric eligibility is a separate policy. Unknowns are retained, warned about and quarantined from metric inputs, with query-level exclusion diagnostics; response/schema/count/duplicate/measurement and publication gates remain strict.

The 2019 ore export profile contains Brazil (33,643.404 t) and Zimbabwe (64,194.3774 t), HHI 5,487.50 and CR3 100%. Australia has no usable selected weight; Thailand has only a mirror observation that the current ore policy does not adopt. The original-code comparator also has two suppliers. The minimum is three, so normal site generation/publication remains blocked. Resolving missing weights or reviewing a justified stage-specific minimum is separate work; this change neither invents data nor relaxes the gate.

The 60-test corrected-run suite included rendering, rollback, idempotency and unknown-entity publication diagnostics on synthetic complete data. A further regression verifies that the audit attempts all 48 queries even if one fetch fails. Real-data HTML staging was not reached because of the minimum-country gate.

Future unrecognized entities remain visible for registry review. Large coverage/metric changes may still stop publication through the existing quality gates. `Other Asia, nes` and other legacy scope exclusions are preserved, not newly reassigned to countries. USGS's pinned edition and the existing unverified quantity supplements are unchanged.
