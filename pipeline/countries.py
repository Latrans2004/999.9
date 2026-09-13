"""Entity identity is independent of the concentration population policy.

``normalize`` remains the strict ISO adapter for reviewed USGS input.
Comtrade uses ``resolve`` and retains non-ISO entities under CT:<numeric code>.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import pycountry

ALIASES = {
    "china, mainland": "CHN", "china": "CHN", "usa": "USA",
    "united states": "USA", "united states of america": "USA",
    "russian federation": "RUS", "russia": "RUS", "republic of korea": "KOR",
    "korea, republic of": "KOR", "rep. of korea": "KOR", "viet nam": "VNM",
    "bolivia (plurinational state of)": "BOL", "iran (islamic republic of)": "IRN",
    "china, hong kong sar": "HKG", "china, macao sar": "MAC",
}
AGGREGATES = {"", "W00", "WLD", "WORLD", "TOTAL", "OTHER", "OTHER COUNTRIES", "AREAS, NES"}

# ISO includes dependent territories and special administrative regions. This
# statistical distinction does not merge them into their administering country.
TERRITORIES = set('ALA ASM AIA ATA ABW BMU BES BVT IOT VGB CYM CXR CCK COK CUW FLK FRO GUF PYF ATF GIB GRL GLP GUM GGY HMD HKG IMN JEY MAC MTQ MYT MSR NCL NIU NFK MNP PCN PRI REU BLM SHN MAF SPM SXM SGS SJM TKL TCA UMI VIR WLF'.split())
REGISTRY = {r['code']: r for r in json.loads(
    Path(__file__).with_name('comtrade_entities.json').read_text(encoding='utf-8'))['entities']}
WORLD = {'W00', 'WLD', 'WORLD', 'TOTAL'}


@dataclass(frozen=True)
class Entity:
    key: str
    name: str
    kind: str
    expired: bool = False


def resolve(value=None, *, code=None, numeric_code=None):
    """Resolve without dropping observations or failing on an unknown entity.

    Numeric Comtrade overrides precede ISO: e.g. 492/MCO is Europe EU, nes,
    not Monaco; 473 and 636 both use A79 but must remain distinct.
    """
    text = str(value or '').strip()
    token = str(code or text).strip().upper()
    if token.startswith('CT:') and numeric_code is None:
        numeric_code = token[3:]
    numeric = int(numeric_code) if numeric_code not in (None, '') else None
    record = REGISTRY.get(numeric)
    if record is None and numeric is None:
        matches = [r for r in REGISTRY.values() if token == r['iso'] or text.casefold() == r['name'].casefold()]
        record = matches[0] if len(matches) == 1 else None
    if record:
        return Entity('W00' if record['code'] == 0 else f"CT:{record['code']}",
                      record['name'], record['kind'], bool(record['expired']))
    if numeric == 0 or token in WORLD:
        return Entity('W00', 'World', 'aggregate')
    if token in {'OTHER', 'OTHER COUNTRIES', 'AREAS, NES'}:
        return Entity('CT:899', 'Areas, nes', 'special_area')
    # A new numeric code with a valid ISO identity can use the established ISO
    # key; original numeric/ISO/name fields are still retained on the row.
    try:
        iso = normalize(text, code=token)
    except ValueError:
        iso = None
    if iso:
        return Entity(iso, pycountry.countries.get(alpha_3=iso).name,
                      'territory' if iso in TERRITORIES else 'country')
    key = f'CT:{numeric}' if numeric is not None else (
        token if token.startswith('UNKNOWN:') else
        'UNKNOWN:' + hashlib.sha256(json.dumps([token, text], ensure_ascii=False).encode()).hexdigest()[:20])
    return Entity(key, text or token or 'Unspecified entity', 'unknown')


def metric_eligibility(entity):
    """Explicit analysis policy; recognized territories are separate suppliers.

    Keep the former exclusion of US Misc. Pacific Isds pending a scope review;
    never infer zero trade from population, sovereignty or ISO membership.
    """
    if entity.expired: return False, 'historical_entity_requires_review'
    if entity.key == 'CT:849': return False, 'legacy_scope_requires_review'
    if entity.kind in {'country', 'territory'}: return True, 'identified_geographic_entity'
    return False, {'aggregate': 'aggregate_would_double_count',
                   'special_area': 'unallocated_special_area',
                   'unknown': 'unknown_requires_review'}[entity.kind]


def row_entity(row, dimension):
    return resolve(row.get(dimension + '_name', row[dimension]),
                   code=row.get(dimension + '_iso', row[dimension]),
                   numeric_code=row.get(dimension + '_code'))


def trade_eligibility(row):
    reporter, partner = (row_entity(row, d) for d in ('reporter', 'partner'))
    included, reason = metric_eligibility(reporter)
    if not included: return False, 'reporter:' + reason
    if partner.key == 'W00': return True, 'reported_world_total'
    included, reason = metric_eligibility(partner)
    return included, 'partner:' + reason


def normalize(value, *, code=None):
    text = str(value or "").strip()
    token = str(code or text).strip().upper()
    if token in AGGREGATES:
        return None
    country = pycountry.countries.get(alpha_3=token)
    if country:
        return country.alpha_3
    if text.lower() in ALIASES:
        return ALIASES[text.lower()]
    try:
        return pycountry.countries.lookup(text).alpha_3
    except LookupError:
        raise ValueError(f"Unmapped country: {text!r} ({code!r}); review registry")


def label(code):
    return {"USA": "United States", "RUS": "Russian Federation", "CHN": "China"}.get(code, resolve(code).name)
