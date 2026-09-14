import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import pytest
from pipeline import archive, countries, hhi, process_trade, strict_comtrade, strict_usgs, update_minerals, validate_data

ROOT=Path(__file__).resolve().parents[2]
CONFIG=json.loads((ROOT/'pipeline/minerals.json').read_text(encoding='utf-8'))['minerals']['lithium']


def test_country_aliases_and_unknown():
    for value,expected in [('China, mainland','CHN'),('USA','USA'),('United States','USA'),('Russian Federation','RUS')]:
        assert countries.normalize(value)==expected
    assert countries.normalize('World') is None
    with pytest.raises(ValueError): countries.normalize('unknown supplier')


def api_row():
    return {'period':'2024','cmdCode':'283691','reporterCode':32,'reporterISO':'ARG',
            'partnerCode':0,'partnerISO':'W00','flowCode':'X','primaryValue':100,
            'netWgt':None,'qty':0,'qtyUnitCode':8,'qtyUnitAbbr':'kg','partner2Code':0,
            'customsCode':'C00','motCode':0,'freqCode':'A','typeCode':'C'}


def query():
    return {'period':'2024','cmdCode':'283691','flowCode':'X','partner2Code':'0',
            'customsCode':'C00','motCode':'0','partnerCode':'0','reporterCode':''}


def test_normalization_keeps_missing_and_zero_distinct():
    row=api_row()
    result=strict_comtrade.normalize({'data':[row]},query(),500)[0]
    assert result['weight_t']==0 and result['net_weight_kg'] is None
    row['qtyUnitCode']=1
    assert strict_comtrade.normalize({'data':[row]},query(),500)[0]['weight_t'] is None


@pytest.mark.parametrize('kind',['empty','error','columns','duplicate','period','flow','count','cap','negative','nan'])
def test_rejects_bad_api_data(kind):
    row=api_row(); payload={'data':[row]}; limit=500
    if kind=='empty': payload['data']=[]
    if kind=='error': payload['errorMessage']='Quota exceeded'
    if kind=='columns': del row['netWgt']
    if kind=='duplicate': payload['data'].append(dict(row))
    if kind=='period': row['period']='2023'
    if kind=='flow': row['flowCode']='M'
    if kind=='count': payload['count']=20
    if kind=='cap': limit=1
    if kind=='negative': row['primaryValue']=-10
    if kind=='nan': row['primaryValue']=float('nan')
    with pytest.raises(ValueError): strict_comtrade.normalize(payload,query(),limit)


def row(country,weight,flow='X',partner='W00',value=None,hs='283691',year=2024):
    return {'year':year,'hs_code':hs,'reporter':country,'partner':partner,'flow':flow,
            'weight_t':weight,'value_usd':value if value is not None else (weight*10000 if weight is not None else None)}


def test_country_specific_mirrors():
    config={'stages':{'283691':CONFIG['stages']['283691']}}
    records=[row('ARG',100),row('JPN',.1),row('CHN',200,'M','ARG'),row('CHN',300,'M','JPN')]
    result={r['country']:r for r in process_trade.build(records,config)}
    assert result['ARG']['selected_value']==200
    assert result['ARG']['selected_source']=='mirror_underreported'
    assert result['JPN']['selected_value']==.1
    assert result['JPN']['mirror_value']==300


def test_incomplete_mirror_is_not_a_complete_sum():
    config={'stages':{'283691':CONFIG['stages']['283691']}}
    result=process_trade.build([row('ARG',100),row('CHN',300,'M','ARG'),row('USA',None,'M','ARG')],config)
    arg=next(r for r in result if r['country']=='ARG')
    assert arg['mirror_value'] is None and arg['selected_value']==100


def test_hydroxide_japan_mirror_disabled():
    config={'stages':{'282520':CONFIG['stages']['282520']}}
    records=[row(c,w,hs='282520') for c,w in [('CHN',100),('CHL',60),('USA',40),('JPN',3.736)]]
    records += [row('CHN',276.5,'M','JPN',hs='282520')]
    jp=next(r for r in process_trade.build(records,config) if r['country']=='JPN')
    assert jp['selected_value']==3.736 and jp['selected_source']=='reported'


def test_excel_production_and_carbonate():
    fixture=json.loads((Path(__file__).parent/'fixtures/excel_reference.json').read_text(encoding='utf-8'))
    for case in fixture['production']:
        result=hhi.concentration(case['year'],case['quantities'])
        assert result.hhi==pytest.approx(case['hhi'],abs=1e-8)
        assert result.cr3==pytest.approx(case['cr3_percent'],abs=1e-8)
    for case in fixture['carbonate']:
        # Preserve the Excel selection-method regression on Excel's original
        # population; its S19 rows were already excluded by the strict fetcher.
        selected=process_trade.select_quantities(case['rows'],{'stages':{'283691':CONFIG['stages']['283691']}})
        amounts={r['country']:r['selected_value'] for r in selected if r['included']}
        result=hhi.concentration(case['year'],amounts)
        assert result.hhi==pytest.approx(case['hhi'],abs=.01)
        assert result.cr3==pytest.approx(case['cr3_percent'],abs=.001)
        for code in ['ARG','CHL','CHN','JPN','USA']:
            expected=case['countries'].get(code)
            if expected and expected['selected_value']:
                actual=next(r['selected_value'] for r in selected if r['country']==code)
                assert actual==pytest.approx(expected['selected_value'],abs=.00001)


def test_report_coverage_measures_filings_not_accepted_suppliers():
    # Three filers in a normal year, one in a late-filing year: the late year reads as a
    # reporting artefact, not as a collapse to a single supplier.
    rows=[row(c,10,hs='283691',year=y) for y in (2022,2023) for c in ('CHN','CHL','ARG')]
    rows+=[row('CHN',10,hs='283691',year=2024)]
    coverage=process_trade.report_coverage(rows)
    assert coverage[('283691',2022)]==coverage[('283691',2023)]==100.0
    assert coverage[('283691',2024)]==pytest.approx(33.3)
    # A country whose figure the policy later rejects still filed, and an unallocated area
    # that files its own returns is a filer even though it is never an accepted supplier.
    assert process_trade.report_coverage(rows+[row('CT:490',0,hs='283691',year=2024)])[('283691',2024)]==pytest.approx(66.7)
    # An entity the registry cannot identify is no evidence that anyone filed.
    assert process_trade.report_coverage(rows+[row('CT:9999',10,hs='283691',year=2024)])[('283691',2024)]==pytest.approx(33.3)
    # Imports are a different question; only the export side is counted.
    assert process_trade.report_coverage(rows+[row('JPN',10,'M','CHN',hs='283691',year=2024)])[('283691',2024)]==pytest.approx(33.3)


def test_a_stage_can_end_before_the_query_range_does():
    """A stage whose method stops working ends; the query range does not shrink."""
    config={'stages':{'283691':{**CONFIG['stages']['283691'],'end_year':2023}}}
    rows=[row(c,10,hs='283691',year=y) for y in (2022,2023,2024) for c in ('CHN','CHL','ARG')]
    selected=process_trade.build(rows,config)
    assert sorted({r['year'] for r in selected})==[2022,2023]
    uncapped={'stages':{'283691':CONFIG['stages']['283691']}}
    assert sorted({r['year'] for r in process_trade.build(rows,uncapped)})==[2022,2023,2024]


def test_a_year_a_stage_does_not_publish_cannot_move_the_years_it_does():
    # Report completeness is relative to the stage's own median, so a late season
    # added to the median would silently restate every year already published.
    published=[row(c,10,hs='283691',year=2022) for c in ('CHN','CHL','ARG','AUS')]
    published+=[row(c,10,hs='283691',year=2023) for c in ('CHN','CHL')]
    late=[row('CHN',10,hs='283691',year=2024)]
    before=process_trade.report_coverage(published)
    after=process_trade.report_coverage(published+late,stage_end_years={'283691':2023})
    assert {k:v for k,v in after.items() if k[1]<=2023}=={k:v for k,v in before.items() if k[1]<=2023}
    assert ('283691',2024) not in after
    # Without the cap the late year is part of the record and does move the median.
    assert process_trade.report_coverage(published+late)[('283691',2022)]!=before[('283691',2022)]


def test_a_stage_cannot_end_outside_the_queried_range(tmp_path):
    root=copy_repo(tmp_path)
    config=json.loads((root/'pipeline/minerals.json').read_text(encoding='utf-8'))
    config['minerals']['lithium']['stages']['283691']['end_year']=config['minerals']['lithium']['end_year']+1
    (root/'pipeline/minerals.json').write_bytes(archive.encode(config))
    with pytest.raises(ValueError,match='outside the queried range'):
        update_minerals.run(root,bundle=synthetic_bundle())


def test_evidence_ledger_is_well_formed_and_reaches_real_rows():
    entries=process_trade.load_evidence(ROOT/'pipeline/evidence.json','lithium')
    assert entries
    settings=CONFIG
    snapshot=json.loads((ROOT/'data/processed/lithium/snapshot.json').read_text(encoding='utf-8'))
    rows={(r['hs_code'],r['year'],r['country']) for r in snapshot['selected']}
    for e in entries:
        # An entry naming a stage the pipeline does not query, or a year outside the
        # published range, would silently verify nothing.
        assert e['hs_code'] in settings['hs_codes'], e
        assert settings['start_year']<=e['year_from']<=e['year_to']<=settings['end_year'], e
        for year in range(e['year_from'],e['year_to']+1):
            assert (e['hs_code'],year,e['country']) in rows, (e['hs_code'],year,e['country'])
        # URLs are filled in by hand once confirmed; a fabricated one would defeat the ledger.
        assert e.get('source_url') in (None,'')


@pytest.mark.parametrize('breakage',['outcome','supports','conflicting_supports','years','source','note','overlap'])
def test_evidence_ledger_rejects_untrustworthy_entries(tmp_path,breakage):
    entry={'mineral':'lithium','hs_code':'283691','country':'ARG','year_from':2024,'year_to':2024,
           'outcome':'externally_confirmed','supports':'mirror','source_name':'S','source_url':None,
           'note_en':'e','note_ja':'j'}
    ledger={'entries':[entry]}
    if breakage=='outcome': entry['outcome']='probably_fine'
    if breakage=='supports': entry['supports']='whoever'
    if breakage=='conflicting_supports': entry['outcome']='externally_conflicting'
    if breakage=='years': entry['year_to']=2023
    if breakage=='source': entry['source_name']=''
    if breakage=='note': entry['note_ja']=''
    if breakage=='overlap': ledger['entries'].append(copy.deepcopy(entry))
    path=tmp_path/'evidence.json'
    path.write_bytes(archive.encode(ledger))
    with pytest.raises((ValueError,KeyError)): process_trade.load_evidence(path,'lithium')


def test_verification_status_separates_why_from_whether():
    entries=[{'mineral':'lithium','hs_code':'282520','country':'JPN','year_from':2021,'year_to':2021,
              'outcome':'externally_confirmed','supports':'self_report','source_name':'MOF',
              'source_url':None,'note_en':'e','note_ja':'j'},
             {'mineral':'lithium','hs_code':'253090','country':'ZWE','year_from':2030,'year_to':2030,
              'outcome':'externally_conflicting','supports':'neither','source_name':'MMCZ',
              'source_url':None,'note_en':'e','note_ja':'j'}]
    rows=[{'hs_code':'282520','year':2021,'country':'JPN','selected_value':3.736,'selected_source':'reported'},
          {'hs_code':'282520','year':2021,'country':'KOR','selected_value':1.0,'selected_source':'reported'},
          {'hs_code':'253090','year':2021,'country':'CHN','selected_value':5.0,'selected_source':'reported_china_import'},
          {'hs_code':'283691','year':2021,'country':'BRA','selected_value':9.0,'selected_source':'mirror_missing_report'},
          {'hs_code':'283691','year':2021,'country':'FRA','selected_value':None,'selected_source':'missing'},
          {'hs_code':'headline_usd','year':2021,'country':'CHL','selected_value':7.0}]
    unmatched=process_trade.apply_verification(rows,entries)
    status=[r['verification_status'] for r in rows]
    # An outside source that confirms a self-report outranks 'we changed nothing': folding
    # Japan into no_adjustment would hide the one check that was actually carried out.
    assert status[0]=='externally_confirmed'
    assert status[1]=='no_adjustment'
    # The importer's own declaration is taken as filed, so there is no correction to verify.
    assert status[2]=='no_adjustment'
    # A mirror substitution nobody checked is exactly what 'unverified' is for.
    assert status[3]=='unverified'
    # Nothing was selected, and a stage with no self-report/mirror pair has no such question.
    assert status[4]=='not_applicable' and status[5]=='not_applicable'
    assert [r['unverified'] for r in rows]==[s=='unverified' for s in status]
    assert all(s in process_trade.VERIFICATION_STATUSES for s in status)
    # An entry covering a year that is not published verifies nothing, and says so.
    assert unmatched==[('253090',2030,'ZWE')]


def test_accepted_snapshot_carries_only_checked_mirrors_as_verified():
    snapshot=json.loads((ROOT/'data/processed/lithium/snapshot.json').read_text(encoding='utf-8'))
    rows=snapshot['selected']
    assert all(r['verification_status'] in process_trade.VERIFICATION_STATUSES for r in rows)
    assert all(r['unverified']==(r['verification_status']=='unverified') for r in rows)
    # The twelve-country allowlist on the carbonate stage is an argument about which
    # substitutions are plausible, not a check of any country. Only Argentina 2024 has been
    # checked against an outside source; every other mirror substitution reads as unverified.
    mirrors=[r for r in rows if r['hs_code']=='283691' and r['selected_source'].startswith('mirror')]
    assert len(mirrors)==33
    checked=[r for r in mirrors if r['verification_status']=='externally_confirmed']
    assert [(r['country'],r['year']) for r in checked]==[('ARG',2024)]
    assert all(r['verification_status']=='unverified' for r in mirrors if r not in checked)


def test_headline_hs_codes_agree_across_catalog_and_pipeline():
    # The site catalog and the strict pipeline each carry the headline HS codes, and a
    # silent divergence would publish a headline the pipeline did not compute. They are
    # named identically so the mismatch is visible, and checked here so it fails in CI
    # rather than at the next publication attempt.
    catalog=json.loads((ROOT/'critical-minerals/data/catalog.json').read_text(encoding='utf-8'))
    pipeline=json.loads((ROOT/'pipeline/minerals.json').read_text(encoding='utf-8'))['minerals']
    entries={e['slug']:e for e in catalog['minerals']}
    assert all('headline_hs_codes' in e for e in entries.values())
    for slug,settings in pipeline.items():
        assert entries[slug]['headline_hs_codes']==settings['headline_hs_codes'], slug
        # A headline code that is never queried would silently produce an empty headline.
        assert set(settings['headline_hs_codes'])<=set(settings['hs_codes']), slug
    # 253090 is queried and published as its own stage, and its absence from the headline
    # is a recorded decision, not drift. See headline_note in pipeline/minerals.json.
    assert '253090' in pipeline['lithium']['hs_codes']
    assert '253090' not in pipeline['lithium']['headline_hs_codes']
    assert '253090' in pipeline['lithium']['headline_note']


def test_usgs_strict_schema_withheld_and_duplicate():
    body=(ROOT/'data/manual/lithium-production.csv').read_bytes()
    records=strict_usgs.parse_csv(body)
    assert len(records)==20
    assert records[0]['production_t'] is None
    assert sum(r['production_t'] or 0 for r in records if r['year']==2024)==pytest.approx(222970)
    with pytest.raises(ValueError): strict_usgs.parse_csv(body+body.splitlines(keepends=True)[1])
    with pytest.raises(ValueError): strict_usgs.parse_csv(b'year,country\n2024,China\n')


def small_snapshot():
    rows=[{'hs_code':'283691','year':2024,'country':c,'reported_value':v,'mirror_value':None,
           'selected_value':v,'included':True} for c,v in [('CHN',40),('CHL',35),('ARG',25)]]
    return {'selected':rows,'concentration':[{'hs_code':'283691',**hhi.concentration(2024,{'CHN':40,'CHL':35,'ARG':25}).to_dict()}]}


@pytest.mark.parametrize('mutation',['countries','total','hhi','cr3','missing','lost_year','country_value'])
def test_anomaly_gates(mutation):
    old=small_snapshot(); new=copy.deepcopy(old)
    profile=new['concentration'][0]
    if mutation=='countries': profile['reporters']=1
    if mutation=='total': profile['total']=1000
    if mutation=='hhi': profile['hhi']=9900
    if mutation=='cr3': profile['cr3']=20
    if mutation=='missing': new['selected'][0]['selected_value']=None; new['selected'][0]['reported_usd']=500
    if mutation=='lost_year': new['concentration']=[]
    if mutation=='country_value': new['selected'][0]['selected_value']=5000
    with pytest.raises(ValueError): validate_data.validate(new,old,CONFIG['validation'])


def two_reporter_snapshot(hs_code,year):
    rows=[{'hs_code':hs_code,'year':year,'country':c,'reported_value':v,'mirror_value':None,
           'selected_value':v,'included':True} for c,v in [('BRA',33643.404),('ZWE',64194.3774)]]
    return {'selected':rows,'concentration':[{'hs_code':hs_code,**hhi.concentration(year,{'BRA':33643.404,'ZWE':64194.3774}).to_dict()}]}


def test_min_countries_exception_is_scoped():
    # 253090/2019 is a documented, reviewed exception (see pipeline/minerals.json
    # and docs/comtrade-entity-audit-2026-09-13.md); it must not excuse any other
    # hs_code/year that also happens to fall below min_countries.
    validate_data.validate(two_reporter_snapshot('253090',2019),None,CONFIG['validation'])
    with pytest.raises(ValueError,match='too few countries'):
        validate_data.validate(two_reporter_snapshot('253090',2020),None,CONFIG['validation'])
    with pytest.raises(ValueError,match='too few countries'):
        validate_data.validate(two_reporter_snapshot('283691',2019),None,CONFIG['validation'])


# The synthetic years follow the configured range rather than a list typed here,
# so extending end_year does not silently stop exercising the newest year.
SYNTHETIC_START_YEAR=2022


def synthetic_bundle():
    records=[]
    for hs in CONFIG['hs_codes']:
        for year in range(SYNTHETIC_START_YEAR,CONFIG['end_year']+1):
            for code,weight in [('AUS',100000),('CHL',80000),('CHN',60000),('USA',40000)]:
                price=(2000 if year<2024 else 800) if hs=='253090' else 20000
                records += [row(code,weight,value=weight*price,hs=hs,year=year),
                            row(code,weight,partner='CHN',value=weight*price,hs=hs,year=year),
                            row('CHN',weight,'M',code,weight*price,hs,year)]
    production=strict_usgs.parse_csv((ROOT/'data/manual/lithium-production.csv').read_bytes())
    return {'trade':records,'production':production,'sources':[{'retrieved_at':'2026-09-13T00:00:00+00:00','source':'synthetic-test-only'}]}


def copy_repo(tmp_path):
    root=tmp_path/'repo'
    shutil.copytree(ROOT,root,ignore=shutil.ignore_patterns('.git','.cache','__pycache__','.pytest_cache','pytest-cache-files-*'))
    config=json.loads((root/'pipeline/minerals.json').read_text(encoding='utf-8'))
    config['minerals']['lithium']['start_year']=SYNTHETIC_START_YEAR
    (root/'pipeline/minerals.json').write_bytes(archive.encode(config))
    # Tests exercise the first-run -> idempotent-second-run cycle against
    # synthetic data; they must not be influenced by whatever real accepted
    # snapshot main happens to carry by the time this runs.
    (root/'data/processed/lithium/snapshot.json').unlink(missing_ok=True)
    return root


def public_bytes(root):
    paths=list(root.glob('*.html'))+list((root/'critical-minerals').rglob('*'))+list((root/'data/processed').rglob('*'))
    return {p.relative_to(root).as_posix():p.read_bytes() for p in paths if p.is_file()}


def test_transaction_render_and_idempotency(tmp_path):
    root=copy_repo(tmp_path); bundle=synthetic_bundle()
    assert update_minerals.run(root,bundle=bundle)
    before=public_bytes(root)
    assert not update_minerals.run(root,bundle=bundle)
    assert public_bytes(root)==before
    assert (root/'critical-minerals/data/lithium/trade.csv').exists()
    profiles=json.loads((root/'critical-minerals/data/lithium/concentration.json').read_text(encoding='utf-8'))['records']
    # Every published stage answers the report-completeness question, and the two
    # single-source stages answer it with null rather than a misleading 100.
    assert all('coverage_pct' in r for r in profiles)
    assert all(r['coverage_pct'] is None for r in profiles if r['hs_code'] in ('headline_usd','mine_li_t'))
    assert any(r['coverage_pct'] is not None for r in profiles)
    text=(root/'critical-minerals/minerals/lithium.html').read_text(encoding='utf-8')
    assert 'Country provenance JSON' in text and 'data-i18n-text=' in text
    broken=copy.deepcopy(bundle)
    broken['trade'][0]['weight_t']*=100
    with pytest.raises(ValueError): update_minerals.run(root,bundle=broken)
    assert public_bytes(root)==before
    changed=copy.deepcopy(bundle)
    changed['trade'][0]['value_usd']*=1.01
    with pytest.raises(subprocess.CalledProcessError):
        update_minerals.run(root,bundle=changed,render_command=[sys.executable,'-c','raise SystemExit(1)'])
    assert public_bytes(root)==before


def test_fetch_failure_retains_site(tmp_path,monkeypatch):
    root=copy_repo(tmp_path); before=public_bytes(root)
    def fail(*args): raise ValueError('API error')
    monkeypatch.setattr(update_minerals,'collect',fail)
    with pytest.raises(ValueError): update_minerals.run(root)
    assert public_bytes(root)==before


def test_raw_archive_no_overwrite(tmp_path):
    first=archive.save(tmp_path,'comtrade',b'{"data":[]}',url='https://example.test',query={'year':2024})
    assert archive.save(tmp_path,'comtrade',b'{"data":[]}',url='https://example.test',query={'year':2024})==first
    second=archive.save(tmp_path,'comtrade',b'{"data":[1]}',url='https://example.test',query={'year':2024})
    assert first['path']!=second['path']
    assert (tmp_path/first['path']).exists()


def test_filesystem_failure_rolls_back(tmp_path,monkeypatch):
    root=tmp_path/'root'; stage=tmp_path/'stage'
    root.mkdir(); stage.mkdir()
    (root/'a.json').write_text('old',encoding='utf-8')
    (stage/'a.json').write_text('new',encoding='utf-8')
    (stage/'b.json').write_text('new-b',encoding='utf-8')
    replace=update_minerals.os.replace
    def fail_second(source,target):
        if Path(target).name=='b.json': raise OSError('Disk write failure')
        return replace(source,target)
    monkeypatch.setattr(update_minerals.os,'replace',fail_second)
    with pytest.raises(OSError): update_minerals.commit_files(root,stage,[Path('a.json'),Path('b.json')])
    assert (root/'a.json').read_text()=='old'
    assert not (root/'b.json').exists()
    assert not list(root.glob('*.updating'))


def test_partial_commodity_cannot_reach_headline():
    bundle=synthetic_bundle()
    bundle['trade']=[r for r in bundle['trade'] if not (r['hs_code']=='283691' and r['partner']=='W00')]
    config=copy.deepcopy(CONFIG); config['start_year']=SYNTHETIC_START_YEAR
    entry=json.loads((ROOT/'critical-minerals/data/catalog.json').read_text(encoding='utf-8'))['minerals'][0]
    with pytest.raises(ValueError,match='missing reported world export totals'):
        update_minerals.assemble(bundle,config,entry)


def test_upstream_importer_loss_detected_even_if_selected_unchanged():
    old=small_snapshot()
    old['source_quality']=[{'hs_code':'283691','year':2024,'flow':'M','rows':100,'reporters':20,'missing_value_fraction':0}]
    new=copy.deepcopy(old); new['source_quality'][0]['reporters']=5
    with pytest.raises(ValueError,match='upstream reporters count dropped'):
        validate_data.validate(new,old,CONFIG['validation'])


def test_no_key_fails_before_fetch(monkeypatch,tmp_path):
    monkeypatch.delenv('COMTRADE_API_KEY',raising=False)
    with pytest.raises(ValueError,match='COMTRADE_API_KEY'):
        update_minerals.collect(tmp_path,CONFIG)
