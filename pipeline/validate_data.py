"""Publication gates; exceptions keep the last accepted snapshot untouched."""
from collections import defaultdict
import math


def validate(current, previous, limits):
    errors = []
    groups = defaultdict(list)
    for r in current['selected']:
        groups[(r['hs_code'], r['year'])].append(r)
        for key in ('reported_value', 'mirror_value', 'selected_value'):
            v = r[key]
            if v is not None and (not math.isfinite(v) or v < 0):
                errors.append(f'Invalid {key}: {r["country"]}')
    missing = {}
    for key, records in groups.items():
        expected = [r for r in records if r.get('reported_usd') is not None or r['selected_value'] is not None]
        missing[key] = sum(r['selected_value'] is None for r in expected) / max(len(expected),1)
        if missing[key] > limits['max_missing_fraction']:
            errors.append(f'{key}: missing fraction {missing[key]:.1%}')
    profiles = {(r['hs_code'], r['year']): r for r in current['concentration']}
    if not profiles:
        errors.append('No concentration profiles')
    for key, r in profiles.items():
        if r['reporters'] < limits['min_countries']:
            errors.append(f'{key}: too few countries ({r["reporters"]})')
        if not 0 <= r['hhi'] <= 10000 or not 0 <= r['cr3'] <= 100 or r['total'] <= 0:
            errors.append(f'{key}: invalid HHI/CR3/total')
    if previous:
        old_quality={(r['hs_code'],r['year'],r['flow']):r for r in previous.get('source_quality',[])}
        for q in current.get('source_quality',[]):
            key=(q['hs_code'],q['year'],q['flow'])
            prior=old_quality.get(key)
            if prior:
                for field in ['rows','reporters']:
                    if q[field] < prior[field]*(1-limits['max_country_drop']):
                        errors.append(f'{key}: upstream {field} count dropped')
                if q['missing_value_fraction']-prior['missing_value_fraction'] > limits['max_missing_increase']:
                    errors.append(f'{key}: upstream missing values increased')
        old_profiles = {(r['hs_code'], r['year']): r for r in previous['concentration']}
        if old_profiles.keys() - profiles.keys():
            errors.append('Previously accepted years/stages disappeared')
        def compare(key, new, old):
            if new['reporters'] < old['reporters'] * (1 - limits['max_country_drop']):
                errors.append(f'{key}: country count dropped')
            if old['total'] and abs(new['total'] / old['total'] - 1) > limits['max_total_relative_change']:
                errors.append(f'{key}: world/reported total changed excessively')
            for metric, limit in [('hhi','max_hhi_change'),('cr3','max_cr3_change')]:
                if abs(new[metric] - old[metric]) > limits[limit]:
                    errors.append(f'{key}: {metric} changed excessively')
        for key, new in profiles.items():
            old = old_profiles.get(key)
            if old is None:
                earlier = [v for (hs,y),v in old_profiles.items() if hs == key[0] and y < key[1]]
                old = max(earlier,key=lambda v:v['year']) if earlier else None
            if old:
                compare(key, new, old)
        old_groups = defaultdict(list)
        for r in previous['selected']:
            old_groups[(r['hs_code'],r['year'])].append(r)
        for key, records in old_groups.items():
            if key in missing:
                expected = [r for r in records if r.get('reported_usd') is not None or r['selected_value'] is not None]
                fraction = sum(r['selected_value'] is None for r in expected) / max(len(expected),1)
                if missing[key] - fraction > limits['max_missing_increase']:
                    errors.append(f'{key}: missing values increased')
        old_rows = {(r['hs_code'],r['year'],r['country']):r for r in previous['selected']}
        new_keys = {(r['hs_code'],r['year'],r['country']) for r in current['selected']}
        for key, old in old_rows.items():
            if old['included'] and key not in new_keys:
                errors.append(f'{key}: accepted country disappeared')
        for r in current['selected']:
            key = (r['hs_code'],r['year'],r['country'])
            old = old_rows.get(key)
            if old and old['selected_value'] and r['selected_value'] is not None:
                if abs(r['selected_value'] / old['selected_value'] - 1) > limits['max_country_relative_change']:
                    errors.append(f'{key}: country quantity changed excessively')
    if errors:
        raise ValueError('Validation failed:\n' + '\n'.join(errors))
    return {'status': 'passed', 'profile_count': len(profiles), 'row_count': len(current['selected'])}
