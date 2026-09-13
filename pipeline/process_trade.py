"""Reported and mirror quantities stay separate from the legacy USD headline."""
from __future__ import annotations
from collections import defaultdict
from statistics import median
from .hhi import concentration


def total(values):
    values = list(values)
    # Do not claim a complete mirror sum when any constituent is missing.
    return sum(values) if values and all(v is not None for v in values) else None


def build(rows, config):
    world = {}
    bilateral = defaultdict(list)
    for r in rows:
        key = (r['hs_code'], r['year'], r['reporter'])
        if r['partner'] == 'W00':
            if r['flow'] == 'X':
                world[key] = r
        else:
            bilateral[(r['hs_code'], r['year'], r['flow'])].append(r)
    result = []
    for hs, policy in config['stages'].items():
        if policy['policy'] not in {'ore','carbonate','hydroxide','reported'}:
            raise ValueError(f'{hs}: unknown selection policy {policy["policy"]}')
        years = sorted({r['year'] for r in rows if r['hs_code'] == hs})
        for year in years:
            exports = bilateral[(hs, year, 'X')]
            imports = bilateral[(hs, year, 'M')]
            suppliers = {k[2] for k in world if k[:2] == (hs, year)} | {r['partner'] for r in imports}
            for code in sorted(suppliers):
                reported = world.get((hs, year, code))
                rep = reported['weight_t'] if reported else None
                own_partners = [r for r in exports if r['reporter'] == code]
                mirror_rows = [r for r in imports if r['partner'] == code]
                mirror = total(r['weight_t'] for r in mirror_rows)
                selected, source = rep, 'reported' if rep is not None else 'missing'
                # Same-reporter partner totals are traceable recovery, never price imputation.
                if policy['policy'] != 'hydroxide' and (rep is None or rep == 0) and own_partners:
                    recovered = total(r['weight_t'] for r in own_partners)
                    if recovered is not None and recovered > 0:
                        selected, source = recovered, 'reported_partner_sum'
                if policy['policy'] == 'carbonate' and code in policy['mirror_allowlist'] and mirror is not None and mirror > 0:
                    if selected is None or selected < policy['minimum_reported_t']:
                        selected, source = mirror, 'mirror_missing_report'
                    elif code == policy['underreported_country'] and mirror > selected * policy['mirror_ratio']:
                        selected, source = mirror, 'mirror_underreported'
                if policy['policy'] == 'hydroxide':
                    proxy = policy.get('legacy_usgs_export_proxy', {})
                    if code == proxy.get('country') and not selected and str(year) in proxy.get('values_li_t', {}):
                        selected = proxy['values_li_t'][str(year)] / proxy['lithium_fraction']
                        source = 'legacy_usgs_export_proxy'
                    limited = total(r['weight_t'] for r in mirror_rows if r['reporter'] in policy['mirror_reporters'])
                    if code in policy['mirror_countries'] and limited is not None and limited > (selected or 0):
                        selected, source = limited, 'mirror_lower_bound'
                    if code in policy['missing_mirror_countries'] and selected is None and mirror is not None:
                        selected, source = mirror, 'mirror_missing_report'
                refs = sorted({r.get('raw_path', '') for r in ([reported] if reported else []) + own_partners + mirror_rows} - {''})
                result.append({'hs_code': hs, 'year': year, 'country': code,
                               'reported_value': rep, 'mirror_value': mirror,
                               'selected_value': selected, 'selected_source': source, 'unit': 't',
                               'reported_usd': reported['value_usd'] if reported else None,
                               'mirror_usd': total(r['value_usd'] for r in mirror_rows),
                               'included': selected is not None and selected > 0,
                               'classification': 'unfiltered', 'raw_paths': refs,
                               'selection_note': policy.get('legacy_usgs_export_proxy', {}).get('caveat') if source == 'legacy_usgs_export_proxy' else None,
                               'supplement_source_url': policy.get('legacy_usgs_export_proxy', {}).get('source_url') if source == 'legacy_usgs_export_proxy' else None,
                               'unverified': source == 'legacy_usgs_export_proxy' or (code in policy.get('unverified_mirror_countries', []) and source.startswith('mirror'))})
    for hs, policy in config['stages'].items():
        subset = [r for r in result if r['hs_code'] == hs]
        if policy['policy'] == 'hydroxide':
            for year in sorted({r['year'] for r in subset}):
                group = [r for r in subset if r['year'] == year]
                anchors = [r for r in group if r['country'] in policy['anchor_countries']]
                prices = [r['reported_usd'] / r['selected_value'] for r in anchors
                          if r['selected_value'] and r['reported_usd'] is not None]
                if len(prices) != len(policy['anchor_countries']):
                    raise ValueError(f'{hs} {year}: missing price anchor; add reviewed source supplement')
                threshold = median(prices) * policy['price_factor']
                for r in group:
                    if not r['selected_value'] and r['reported_usd'] and policy.get('estimate_missing_from_anchor_price'):
                        r['selected_value'] = r['reported_usd'] / median(prices)
                        r['selected_source'] = 'estimated_anchor_price'
                        r['selection_note'] = 'Reported USD divided by median selected-weight unit price of configured anchor countries (Excel 05/17 legacy method)'
                        r['unverified'] = True
                    price = r['reported_usd'] / r['selected_value'] if r['selected_value'] and r['reported_usd'] is not None else None
                    r['classification'] = 'included' if price is not None and price >= threshold else ('missing_price' if price is None else 'excluded_price')
                    r['price_threshold_usd_t'] = threshold
                    r['included'] = r['classification'] == 'included'
        elif policy['policy'] == 'ore':
            # HS253090 is mixed merchandise. Classify exports and China imports separately.
            codes = sorted({r['country'] for r in subset})
            for code in codes:
                own = [r for r in subset if r['country'] == code]
                china = [r for r in rows if r['hs_code'] == hs and r['flow'] == 'M' and r['reporter'] == 'CHN' and r['partner'] == code]
                exp_total = sum(r['selected_value'] or 0 for r in own)
                cn_total = sum(r['weight_t'] or 0 for r in china)
                to_china = sum(r['weight_t'] or 0 for r in rows if r['hs_code'] == hs and r['flow'] == 'X' and r['reporter'] == code and r['partner'] == 'CHN')
                # Excel 30!S uses 1 when cumulative China imports exceed world exports.
                ratio = 1 if cn_total > exp_total else (to_china / exp_total if exp_total else 0)
                def classify(records, weight, value, chinese=False):
                    cumulative = sum(r[weight] or 0 for r in records)
                    def price(y):
                        group = [r for r in records if r['year'] == y]
                        w = sum(r[weight] or 0 for r in group)
                        return sum(r[value] or 0 for r in group) / w if w else 0
                    peak = max(price(y) for y in policy['peak_years'])
                    if cumulative < policy['min_cumulative_t']: return 'insufficient_data'
                    if not policy['min_peak_usd_t'] <= peak <= policy['max_peak_usd_t']: return 'non_lithium'
                    if price(policy['drop_year']) / peak > policy['max_drop_ratio']: return 'non_lithium'
                    return 'lithium' if chinese or ratio >= policy['min_china_ratio'] else 'review'
                export_class = classify(own, 'selected_value', 'reported_usd')
                china_class = classify(china, 'weight_t', 'value_usd', True)
                for r in own:
                    r['classification'] = export_class
                    r['china_import_classification'] = china_class
                    r['included'] = export_class == 'lithium' and bool(r['selected_value'])
    # China-import ore concentration is a separate population, never added to exports.
    for hs, policy in config['stages'].items():
        if policy['policy'] != 'ore': continue
        classifications = {r['country']: r['china_import_classification'] for r in result if r['hs_code'] == hs}
        for row in rows:
            if row['hs_code'] == hs and row['flow'] == 'M' and row['reporter'] == 'CHN' and row['partner'] != 'W00':
                result.append({'hs_code':hs+'_china_import','year':row['year'],'country':row['partner'],
                               'reported_value':row['weight_t'],'mirror_value':None,
                               'selected_value':row['weight_t'],'selected_source':'reported_china_import',
                               'reported_usd':row['value_usd'],'unit':'t',
                               'classification':classifications.get(row['partner'],'insufficient_data'),
                               'included':classifications.get(row['partner']) == 'lithium' and bool(row['weight_t']),
                               'raw_paths':[row['raw_path']] if row.get('raw_path') else [],'unverified':False})
    return result


def metrics(selected):
    groups = defaultdict(dict)
    for r in selected:
        groups.setdefault((r['hs_code'], r['year']), {})
        if r['included']:
            groups[(r['hs_code'], r['year'])][r['country']] = r['selected_value']
    result = []
    for (hs, year), amounts in sorted(groups.items()):
        profile = concentration(year, amounts)
        if profile is None:
            raise ValueError(f'{hs} {year}: no accepted suppliers')
        result.append({'hs_code': hs, 'unit': 't', **profile.to_dict()})
    return result
