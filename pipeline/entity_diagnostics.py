"""Per-query observations, not additive world trade totals (X/M overlap)."""
from . import countries


def summarize(rows):
    entities, groups = {}, {}
    for row in rows:
        query = (row['hs_code'], row['year'], row['flow'])
        group = groups.setdefault(query, {'hs_code': query[0], 'year': query[1], 'flow': query[2],
                                         'rows': 0, 'eligible_rows': 0, 'excluded': {}})
        group['rows'] += 1
        included, reason = countries.trade_eligibility(row)
        if included:
            group['eligible_rows'] += 1
        else:
            excluded = group['excluded'].setdefault(reason, {'rows': 0, 'observed_value_usd': 0,
                                                            'observed_weight_t': 0, 'missing_weight_rows': 0})
            excluded['rows'] += 1
            excluded['observed_value_usd'] += row['value_usd'] or 0
            excluded['observed_weight_t'] += row['weight_t'] or 0
            excluded['missing_weight_rows'] += row['weight_t'] is None
        for dimension in ('reporter', 'partner'):
            entity = countries.row_entity(row, dimension)
            if not entity.key.startswith(('CT:', 'UNKNOWN:')): continue
            eligible, policy = countries.metric_eligibility(entity)
            item = entities.setdefault(entity.key, {'id': entity.key, 'name': entity.name, 'kind': entity.kind,
                                                    'metric_eligible': eligible, 'policy': policy,
                                                    'observations': 0, 'source_labels': [], 'queries': []})
            item['observations'] += 1
            label = [dimension, row.get(dimension + '_iso'), row.get(dimension + '_name')]
            if label not in item['source_labels']: item['source_labels'].append(label)
            if list(query) not in item['queries']: item['queries'].append(list(query))
    return {'policy': 'comtrade-entities-v1',
            'note': 'Excluded amounts are observations by query, not additive world totals. Unknowns are quarantined; existing data-quality gates still apply.',
            'entities': sorted(entities.values(), key=lambda r: r['id']),
            'queries': [groups[k] for k in sorted(groups)]}
