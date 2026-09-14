"""Diagnostic only: never select trade or infer industry structure from ratios."""
from __future__ import annotations

from .manganese_evidence import PRODUCT


def diagnose(observation, disclosures, context=None):
    context = context or {}
    result = {k: observation[k] for k in ('country', 'year', 'hs_code')}
    result.update(diagnostic_only=True, publishable=False, reported_production_ratio=None,
                  mirror_production_ratio=None, threshold_status='deferred_no_manganese_evidence',
                  industry_role=context.get('role', 'unknown'),
                  industry_sources=context.get('source_urls', []))
    candidates = [r for r in disclosures if r['country'] == observation['country']
                  and r['year'] == observation['year'] and r['measure'] == 'production']
    result['anchor_candidates'] = len(candidates)
    mismatches = set()
    for r in candidates:
        if r['weight_basis'] != observation['weight_basis']:
            mismatches.add('weight_basis_mismatch')
        if r['product_scope'] != PRODUCT:
            mismatches.add('product_scope_mismatch')
        if r['coverage_scope'] != 'national':
            mismatches.add('operation_is_not_national_production')
        if r['period_start'] != f"{r['year']}-01-01" or r['period_end'] != f"{r['year']}-12-31":
            mismatches.add('fiscal_calendar_mismatch')
    result['comparability_issues'] = sorted(mismatches)
    reported, mirror = observation['reported_weight_t'], observation['mirror_observed_weight_t']
    if reported is None:
        status, reason = 'missing', 'missing_reported_trade'
    elif context.get('role') == 'hub':
        status, reason = 'hub', 'reexports_processing_inventories_preclude_mine_anchor'
    elif context.get('role') == 'domestic_consumption':
        status, reason = 'domestic_consumption', 'domestic_use_precludes_export_production_identity'
    elif observation['comparison_status'] == 'no_dispute':
        status, reason = 'no_dispute', 'no_observed_weight_disagreement_not_accuracy_certification'
    elif not candidates:
        status, reason = 'missing', 'no_human_reviewed_annual_production'
    elif mismatches:
        status, reason = 'incomparable', ';'.join(sorted(mismatches))
    elif len(candidates) != 1 or candidates[0]['value_t'] in (None, 0):
        status, reason = 'indeterminate', 'ambiguous_or_zero_production_anchor'
    else:
        status, reason = 'indeterminate', 'industry_comparability_and_manganese_thresholds_require_review'
        # Matching labels and numeric ratio bands do not prove economic
        # comparability or that one operation represents national exports.
        # No ratio is calculated until a future reviewed design establishes it.
    result.update(classification=status, reason=reason)
    return result
