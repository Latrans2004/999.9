# Mineral-specific literals in `pipeline/` (inventory only)

Scope: everything under `pipeline/` except `graphite*.py` / `graphite*.json`, which are
an isolated, non-publishable audit and are inventoried separately when they are promoted.

**This document changes no code.** It is the work plan for extending the strict pipeline
beyond lithium. Nothing here is renamed or parameterised until a second mineral (natural
graphite) has been driven through the publication stage, because naming decisions taken
from a single sample are almost certain to be redone.

Line numbers are as of commit `e0b74bf`.

## Legend

| Column | Meaning |
|---|---|
| Kind | mineral name / country code / HS code / conversion factor / price band / other |
| Impact | what happens if the code is applied to another mineral unchanged |
| Proposal | parameterise / rename / split per mineral / no action / **deferred** |

---

## 1. `pipeline/process_trade.py`

### 1.1 Stage-policy name literals

| File:line | Literal | Kind | Impact | Proposal |
|---|---|---|---|---|
| `process_trade.py:39` | `{'ore','carbonate','hydroxide','reported'}` | mineral name (refining-chain stage) | Hard gate. A graphite stage such as `flake` / `amorphous` / `spherical` raises `ValueError: unknown selection policy` and the run aborts. | parameterise — turn the policy set into a registry keyed by policy implementation, not by lithium's chain |
| `process_trade.py:54` | `policy['policy'] != 'hydroxide'` | mineral name | Guards partner-sum recovery. On another mineral the branch is simply always true, so partner-sum recovery silently applies to a stage where it may be wrong. | parameterise — `allow_partner_sum: bool` |
| `process_trade.py:58` | `policy['policy'] == 'carbonate'` | mineral name | Guards the whole mirror-substitution block. Never fires for a non-lithium stage, so a mineral that needs mirror substitution gets none. | parameterise — `mirror_substitution: {...}` |
| `process_trade.py:63`, `:86` | `policy['policy'] == 'hydroxide'` | mineral name | Guards the price-anchor / price-threshold classification. Never fires elsewhere; `classification` then stays `'unfiltered'` and every row is accepted on `selected_value > 0` alone. | parameterise — `price_classification: {...}` |
| `process_trade.py:105`, `:135` | `policy['policy'] == 'ore'` | mineral name | Guards the mixed-merchandise classifier and the China-import population. Never fires elsewhere. | parameterise — `merchandise_classifier: {...}` |

Note: `'reported'` is accepted at line 39 but is **matched by no branch below**. A stage
configured as `reported` falls through to plain self-report pass-through. It is unclear
whether this is an intentional placeholder or dead code. **Judgement deferred.**

### 1.2 Hard-coded country code `CHN`

| File:line | Literal | Kind | Impact | Proposal |
|---|---|---|---|---|
| `process_trade.py:110` | `r['reporter'] == 'CHN'` (China-import rows for the ratio) | country code | **Breaks the judgement.** For graphite and rare earths China is the *supply* side, not the demand side. The "does China's declared import corroborate this exporter" test inverts in meaning. | parameterise — a `corroborating_importer` (or list) per stage. **Deferred to mineral #2.** |
| `process_trade.py:113` | `r['partner'] == 'CHN'` (share of exports going to China) | country code | Same inversion. `ratio` becomes meaningless and `min_china_ratio` gates on noise. | same, **deferred** |
| `process_trade.py:138` | `row['reporter'] == 'CHN'` (building the China-import population) | country code | Same. | same, **deferred** |

### 1.3 Mineral-name literals in output values

| File:line | Literal | Kind | Impact | Proposal |
|---|---|---|---|---|
| `process_trade.py:124`, `:125` | `'non_lithium'` (returned by `classify()`) | mineral name | A wrong label is emitted into published `trade.json` / `trade.csv` — a graphite row would read `classification: "non_lithium"`. | rename to `off_target` / `target`. **Deferred to mineral #2** (published vocabulary). |
| `process_trade.py:126`, `:132`, `:144` | `'lithium'` (returned by `classify()`, and the inclusion test) | mineral name | Same, plus the inclusion test `== 'lithium'` silently excludes every row for any other mineral. | same, **deferred** |
| `process_trade.py:142` | `'reported_china_import'` (a `selected_source` value) | country code baked into a published enum | The published `selected_source` vocabulary names one specific country. Wrong or meaningless for minerals where the corroborating importer is not China. | rename to `reported_importer_declaration`. **Deferred** (published vocabulary; changing it is a data migration). |

### 1.4 Pseudo HS-code naming convention

| File:line | Literal | Kind | Impact | Proposal |
|---|---|---|---|---|
| `process_trade.py:137` | `hs+'_china_import'` | HS code naming | Produces a synthetic series key such as `253090_china_import`. For a mineral where China is the supplier the key would still read `_china_import` while meaning something else entirely, and the key is already published in `concentration.json`. | generalise to `<hs>@<reporter>_import`. **Deferred to mineral #2.** |

### 1.5 Conversion-factor key names

| File:line | Literal | Kind | Impact | Proposal |
|---|---|---|---|---|
| `process_trade.py:66` | `proxy['lithium_fraction']` | conversion factor (key name) | The **value** (0.1654) is already externalised in `minerals.json`; only the *key name* is mineral-specific. Another mineral would need a differently named key or would reuse a misleading one. | rename the key to `content_fraction`. Low risk, but **deferred** so it lands with the other renames. |
| `process_trade.py:65` | `proxy['values_li_t']` | conversion factor (key name) | Same. | rename to `values_content_t`, **deferred** |

---

## 2. `pipeline/update_minerals.py`

| File:line | Literal | Kind | Impact | Proposal |
|---|---|---|---|---|
| `update_minerals.py:135`, `:241`, `:251` | `'mine_li_t'` (synthetic stage key) | mineral name | The mine-production series key is lithium-specific. It is **already published** in `concentration.json` and `catalog`-derived output. Another mineral would either reuse a wrong key or need a second key, and the two exclusion filters at `:241`/`:251` are written against the literal. | rename to `mine_t` + parameterise the unit. **Deferred** (published vocabulary). |
| `update_minerals.py:139` | `'t Li'` (unit string) | mineral name / unit | Published as `"unit": "t Li"` in `concentration.json`. For graphite the correct unit is plain `t`; for rare earths `t REO`. Emitting `t Li` for them is a factual error on the page. | parameterise — `production_unit` in `minerals.json`. **Deferred**, but this is the highest-severity wrong-label item after §1.3. |
| `update_minerals.py:188`, `:264` | `mineral='lithium'` (default argument / CLI default) | mineral name | Only a default; overridable with `--mineral`. | no action |
| `update_minerals.py:112`, `:193` | `settings['headline_hs_codes']` vs `entry['hs_codes']` | HS code | Not mineral-specific, but the two field names disagree across the two files. | handled in sub-task 2D |

---

## 3. `pipeline/validate_data.py`

**No mineral-specific literal was found.** Every threshold reaches the module through
`limits` (i.e. `minerals.json` → `validation`). The only numeric literals are the
definitional bounds of the metrics themselves:

| File:line | Literal | Kind | Impact | Proposal |
|---|---|---|---|---|
| `validate_data.py:29` | `0 <= hhi <= 10000`, `0 <= cr3 <= 100` | other (metric definition) | None — these are properties of HHI/CR3, not of lithium. | no action |

The reviewed exception key `"253090|2019"` lives in `minerals.json`, not in code, and is
therefore parameter-layer. No action.

---

## 4. `pipeline/audit_entities.py`

| File:line | Literal | Kind | Impact | Proposal |
|---|---|---|---|---|
| `audit_entities.py:13` | `['minerals']['lithium']` | mineral name | The entity audit can only be run for lithium. | parameterise — add a `--mineral` argument |
| `audit_entities.py:76` | `e['slug'] == 'lithium'` | mineral name | Same. | same |
| `audit_entities.py:81` | `'data/processed/lithium/snapshot.json'` | mineral name (path) | Same. | same |

---

## 5. `pipeline/fixtures.py`

| File:line | Literal | Kind | Impact | Proposal |
|---|---|---|---|---|
| `fixtures.py:17-22` | 18 hard-coded country name/ISO pairs | country code | None. Synthetic data for layout work only; never published (`update_minerals.run()` refuses to publish into a fixtures site). | no action |

---

## 6. `pipeline/minerals.json` (parameter layer — no action by design)

Per the three-layer rule, thresholds, anchor countries, mirror baselines and conversion
factors are expected to differ per mineral and are **not** to be unified. Listed here only
so the extension work has the full set in one place.

| Key | Value | Kind |
|---|---|---|
| `stages.253090.policy` / `.283691.policy` / `.282520.policy` | `ore` / `carbonate` / `hydroxide` | mineral name |
| `stages.253090.min_cumulative_t` | `50000` | other |
| `stages.253090.peak_years` / `drop_year` | `[2022, 2023]` / `2024` | other |
| `stages.253090.min_peak_usd_t` / `max_peak_usd_t` | `800` / `5000` | price band |
| `stages.253090.max_drop_ratio` | `0.6` | price band |
| `stages.253090.min_china_ratio` | `0.4` | country code (**in the key name**) |
| `stages.283691.mirror_allowlist` | 12 countries | country code |
| `stages.283691.underreported_country` | `ARG` | country code |
| `stages.283691.mirror_ratio` / `minimum_reported_t` | `1.15` / `1` | other |
| `stages.282520.anchor_countries` | `["CHN","CHL","USA"]` | country code |
| `stages.282520.price_factor` | `0.4` | price band |
| `stages.282520.mirror_countries` / `mirror_reporters` / `missing_mirror_countries` / `unverified_mirror_countries` | `["AUS"]` / `["CHN","JPN","KOR","USA"]` / `["CHN"]` / `["AUS"]` | country code |
| `stages.282520.legacy_usgs_export_proxy.lithium_fraction` | `0.1654` | conversion factor |
| `stages.282520.legacy_usgs_export_proxy.country` | `USA` | country code |
| `validation.min_countries_exceptions` | `"253090|2019"` | HS code |

Only one item here warrants a later change: **`min_china_ratio` carries a country name in
its key**, and should become `min_corroborating_importer_ratio` (or similar) alongside the
§1.2 parameterisation. **Deferred.**

---

## 7. Conversion factors named in the task brief that do **not** exist in the repository

The brief listed four categories of known literals. The fourth ("unit conversion factors:
LCE 5.323, hydroxide Li content 0.1654, 6% Li2O concentrate 2.788%") is only one-third
present:

| Factor | Present? | Where |
|---|---|---|
| LCE conversion `5.323` | **No** — no occurrence anywhere in the repository | — |
| 6% Li₂O concentrate `2.788` | **No** — no occurrence anywhere in the repository | — |
| Hydroxide Li content `0.1654` | Yes | `pipeline/minerals.json`, already externalised as `legacy_usgs_export_proxy.lithium_fraction`. Only the key name is mineral-specific (§1.5). |

So there is no hard-coded unit-conversion arithmetic to extract. The strict pipeline works
in gross tonnes throughout; the single content-fraction division at `process_trade.py:66`
is the only conversion, and it is already configuration-driven.

---

## 8. Clean — no mineral-specific literal found

| File | Note |
|---|---|
| `pipeline/hhi.py` | Deliberately source-agnostic; operates on `{producer: quantity}`. The DOJ/FTC band thresholds (1000 / 1800) are a published convention, not mineral-specific. |
| `pipeline/templates/*.html` | No occurrence of `lithium`, `リチウム`, `china_import`, `carbonate`, `hydroxide`, or `LCE`. |
| `pipeline/i18n.py` | No mineral-specific string. |
| `pipeline/render.py` | Iterates the catalog; no mineral named. |
| `pipeline/strict_comtrade.py`, `pipeline/strict_usgs.py`, `pipeline/archive.py`, `pipeline/sources/*` | Transport and normalisation only. |

---

## 9. Judgement deferred

Recorded for completeness; each needs a decision that a single mineral cannot supply.

1. **`'reported'` policy at `process_trade.py:39`** — accepted but unimplemented. Placeholder
   or dead code?
2. **`hhi.py` `universe_total` / `coverage`** — not mineral-specific, but it only functions
   where USGS publishes a world total alongside withheld country figures. Whether that holds
   for graphite, and how `coverage` should behave when it does not, is open.
3. **`countries.py:82` `entity.key == 'CT:849'`** (US Misc. Pacific Isds excluded pending
   scope review) — a specific entity hard-coded in code rather than configuration. Mineral-
   independent, but it is a hard-coded geography and belongs on this list.
4. **`countries.py:121` `label()`** overrides display names for `USA` / `RUS` / `CHN` only.
   Mineral-independent presentation choice; no action expected, recorded for completeness.
5. **Whether `classification` should stay a single field.** Lithium's ore policy emits both
   `classification` and `china_import_classification` on the same row. If mineral #2 needs a
   third axis the field set, not just the values, has to change.

---

## 10. Severity ordering for the seven-mineral rollout

1. §2 `'t Li'` unit string and §1.3 `'lithium'` / `'non_lithium'` — these put a **factually
   wrong label on a published page**, not merely an awkward name.
2. §1.2 hard-coded `CHN` — the only item that makes a **judgement produce a wrong answer**
   rather than a wrong label.
3. §1.1 policy-name gating — blocks the run outright (`ValueError`), so it fails loudly and
   is the least dangerous.
4. §1.4 `_china_import` and §1.5 key names — naming only.
5. §4 `audit_entities.py` — tooling convenience.
