"""Corrective paper inputs are explicit, registered and never inferred from ledger values."""
import io
import json
from pathlib import Path

import pytest
from born_ladder.reproduction.comparison_policy import PolicyComparison
from born_ladder.reproduction.full_comparison import compare_paper,automatic_paper_binding
from born_ladder.reproduction import v25_paper as V


def test_lean_declaration_count_uses_fresh_audit():
    entry={'id':'LeanDeclarationsAudited','value':'5058','evidence_type':'audit_metadata'}
    alias={'macro':'LeanDeclarations','id':entry['id'],'format':'int'}
    c=PolicyComparison(io.StringIO())
    result=compare_paper(c,{'entries':[entry]},[alias],[],Path('.'),{}, {'lean_audit':{'declarations':5058}})
    assert result['overall_agreement'] and result['paper_macros_compared']==['LeanDeclarations']


@pytest.mark.parametrize('provided',[False,True])
def test_optional_v25_root_resolves_quantities_or_names_public_command(tmp_path,monkeypatch,provided):
    entry={'id':'CorrCrossRaw','value':'0.125','evidence_type':'recomputed_by_public_command',
           'source':'/retained/v25/cross-term/evaluation/attempts/attempt_0001/population.json#/paper_values/raw/point'}
    alias={'macro':entry['id'],'id':entry['id'],'format':'sig:4'}
    calls=[]
    monkeypatch.setattr(V,'population_view',lambda root,evaluation,**kw:calls.append((root,evaluation)) or {'paper_values':{'raw':{'point':.125}}})
    result=compare_paper(PolicyComparison(io.StringIO()),{'entries':[entry]},[alias],[],tmp_path,{}, {},v25=tmp_path/'v25' if provided else None)
    assert result['overall_agreement']==provided
    assert bool(calls)==provided
    if not provided:assert 'reproduce v25' in result['unavailable_paper_quantities'][0]['reason']
    else:
        monkeypatch.setattr(V,'population_view',lambda *a,**kw:{'paper_values':{'raw':{'point':.25}}})
        result=compare_paper(PolicyComparison(io.StringIO()),{'entries':[entry]},[alias],[],tmp_path,{}, {},v25=tmp_path/'v25')
        assert not result['overall_agreement']


def test_v25_special_counts_and_orientation_bindings():
    names={'CorrCompetitorCases':'/cases','CorrCrossInvocations':'/invocations',
           'CorrCompetitorComparisons':'/comparisons','CorrCompetitorLower':'/minimum_lower',
           'CorrCompetitorConfigs':'/configs','OrientationCount':'/orientation/registered_slots',
           'HistSvdRaw':'/orientation/historical_svd/raw','SelectedDCanonicalPkg':'/pkg'}
    for name,pointer in names.items():
        entry={'id':name,'source':'/retained/v25/cross-term/evaluation/population.json#/ignored'}
        assert automatic_paper_binding(entry,name)['pointer']==pointer


def test_v25_completion_hashes_reject_changed_content(tmp_path):
    from born_ladder.archive import sha
    root=tmp_path/'evaluation';directory=root/'attempts/attempt_0001';directory.mkdir(parents=True)
    path=directory/'population.json';path.write_text('{"point":1}')
    (root/'complete.json').write_text(json.dumps({'attempt':'attempts/attempt_0001',
        'artifacts':[{'path':path.name,'bytes':path.stat().st_size,'sha256':sha(path)}]}))
    assert V.completed(root)==directory
    path.write_text('{"point":2}')
    with pytest.raises(ValueError,match='artifact changed'):V.completed(root)


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))


def reseal(root):
    from born_ladder.archive import sha
    directory=root/'attempts/attempt_0001'
    write(root/'complete.json',{'attempt':'attempts/attempt_0001','artifacts':[
        {'path':p.relative_to(directory).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)}
        for p in sorted(directory.rglob('*')) if p.is_file()]})


@pytest.fixture
def registered(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from born_ladder.reproduction.v25 import specification,fresh
    from born_ladder.reproduction import runs
    from born_ladder.archive import sha
    spec=SimpleNamespace(digest='science',directory=Path('specifications'),
                         science={'inference':{'bootstrap':{'replicates':20000}}})
    monkeypatch.setattr(specification,'Specification',lambda *a:spec)
    monkeypatch.setattr(runs,'RunSpecifications',lambda *a:SimpleNamespace(grid=lambda name:[SimpleNamespace(id=x) for x in ('a','b')]))
    completed={'a':{},'b':{}}
    monkeypatch.setattr(runs,'Manifest',lambda *a:SimpleNamespace(completed=lambda:completed))
    verified=[]
    monkeypatch.setattr(fresh,'verify_collection',lambda path,collection:verified.append(path) or True)
    plan={'schema':'born_v25_stage_plan_v1','scientific_digest':'science','runtime':{'numpy':'registered'},
          'inputs':{'mode':'registered','workflow':'v25'}}
    write(tmp_path/'plan.json',plan)
    for evaluation in ('competitor','cross-term'):
        stage=tmp_path/evaluation
        collection=stage/'units/collection_0001.json'
        write(collection,{'schema':'born_v25_closed_units_v1','mode':'fresh','complete':True,
            'scientific_digest':'science','evaluation':evaluation,
            'dispositions':[{'invocation_id':x,'status':'completed'} for x in ('a','b')],
            'units':[{'unit_id':uid,'kind_cell_id':uid+kind,'eligibility':eligible,'kind':kind}
                     for uid,eligible in [('u',True),('v',False)] for kind in ('raw','package')]})
        write(stage/'runs/runset.json',{'invocations':[{'id':x} for x in ('a','b')]})
        write(stage/'evaluation/plan.json',{**plan,'inputs':{'units_sha256':sha(collection)}})
        directory=stage/'evaluation/attempts/attempt_0001'
        write(directory/'population.json',{'schema':'born_v25_population_v1','evaluation':evaluation,
            'scientific_digest':'science','mode':'registered','bootstrap_replicates':20000,
            'joint':{'status':'PASS'},'statistics':{'package::L_clipped_linear':{'hierarchy_counts':{'configs':2}}},
            'paper_values':{'raw::linear':{'lower':.2},'package::linear':{'lower':.1},
                            'raw::serviceability_factor_two':{'lower':-1.}}})
        write(directory/'orientation_description.json',{'status':'complete','registered_slots':2,'complete_slots':2,
            'summaries':{},'references':{'historical_svd':{'contrasts':{}}}})
        reseal(stage/'evaluation')
    return tmp_path,verified,completed


@pytest.mark.parametrize('evaluation',['competitor','cross-term'])
def test_v25_view_reads_registered_sealed_population(registered,evaluation):
    root,verified,_=registered
    result=V.population_view(root,evaluation)
    assert (result['cases'],result['comparisons'],result['minimum_lower'])==(1,2,.1)
    assert verified==[root/evaluation/'units/collection_0001.json']


def test_identical_committed_collections_are_the_same_evidence(registered):
    root,verified,_=registered
    original=root/'competitor/units/collection_0001.json'
    (original.parent/'collection_0002.json').write_bytes(original.read_bytes())
    result=V.population_view(root,'competitor')
    assert (result['cases'],result['configs'],result['minimum_lower'])==(1,2,.1)
    assert verified==[original]


def test_nonmatching_extra_collection_is_ignored(registered):
    root,verified,_=registered
    original=root/'competitor/units/collection_0001.json'
    original.rename(original.parent/'collection_0002.json')
    original.write_text('uncommitted extra content is not parsed')
    result=V.population_view(root,'competitor')
    assert (result['cases'],result['configs'],result['minimum_lower'])==(1,2,.1)
    assert verified==[original.parent/'collection_0002.json']


def test_no_matching_committed_collection_fails(registered):
    root,_,_=registered
    (root/'competitor/units/collection_0001.json').write_text('{}')
    with pytest.raises(ValueError,match='committed unit collection'):
        V.population_view(root,'competitor')


@pytest.mark.parametrize('field,value',[('schema','wrong'),('evaluation','wrong'),('scientific_digest','wrong'),
                                      ('mode','synthetic-reduced'),('bootstrap_replicates',1),('bootstrap_replicates',True)])
def test_resealed_reduced_or_mismatched_population_fails(registered,field,value):
    root,_,_=registered;stage=root/'competitor/evaluation'
    p=stage/'attempts/attempt_0001/population.json';write(p,{**V.read(p),field:value});reseal(stage)
    with pytest.raises(ValueError,match='population headers'):V.population_view(root,'competitor')


@pytest.mark.parametrize('field,value',[('schema','wrong'),('scientific_digest','wrong'),('runtime',{'numpy':'other'})])
def test_wrong_evaluation_plan_fails(registered,field,value):
    root,_,_=registered;p=root/'competitor/evaluation/plan.json';write(p,{**V.read(p),field:value})
    with pytest.raises(ValueError,match='evaluation plan'):V.population_view(root,'competitor')


@pytest.mark.parametrize('mutation',['unpaired','duplicate-kind','duplicate-unit','incomplete-grid','reordered-grid','failed-disposition'])
def test_unpaired_duplicate_or_incomplete_cohort_fails(registered,mutation):
    from born_ladder.archive import sha
    root,_,_=registered;p=root/'competitor/units/collection_0001.json';c=V.read(p)
    if mutation=='unpaired':c['units'][1]['unit_id']='other'
    elif mutation=='duplicate-kind':c['units'][1]['kind_cell_id']=c['units'][0]['kind_cell_id']
    elif mutation=='duplicate-unit':c['units'].append({**c['units'][0],'kind_cell_id':'different'})
    elif mutation=='incomplete-grid':c['dispositions'].pop()
    elif mutation=='reordered-grid':c['dispositions'].reverse()
    else:c['dispositions'][0]['status']='failed'
    write(p,c);plan=root/'competitor/evaluation/plan.json';write(plan,{**V.read(plan),'inputs':{'units_sha256':sha(p)}})
    with pytest.raises(ValueError,match='membership|duplicate|disposition'):V.population_view(root,'competitor')


@pytest.mark.parametrize('evaluation',['competitor','cross-term'])
def test_run_completion_required_for_both_evaluations(registered,evaluation):
    root,_,completed=registered;completed.pop('b')
    with pytest.raises(ValueError,match='invocation completion'):V.population_view(root,evaluation)


def test_runset_duplicate_or_incomplete_grid_fails(registered):
    root,_,_=registered;p=root/'competitor/runs/runset.json'
    write(p,{'invocations':[{'id':'a'},{'id':'a'}]})
    with pytest.raises(ValueError,match='invocation completion'):V.population_view(root,'competitor')


def test_collection_source_verification_is_required(registered,monkeypatch):
    from born_ladder.reproduction.v25 import fresh
    root,_,_=registered
    def invalid(*a):raise ValueError('fresh flattened scientific/control stream differs from seals')
    monkeypatch.setattr(fresh,'verify_collection',invalid)
    with pytest.raises(ValueError,match='differs from seals'):V.population_view(root,'competitor')


@pytest.mark.parametrize('mutation',['empty','omitted','duplicate','uncommitted-orientation','missing-consumed','extra','escape'])
def test_artifact_bindings_are_exhaustive_and_contained(registered,mutation):
    root,_,_=registered;stage=root/'cross-term/evaluation';seal=V.read(stage/'complete.json')
    if mutation=='empty':seal['artifacts']=[]
    elif mutation=='omitted':seal['artifacts'].pop()
    elif mutation=='duplicate':seal['artifacts'].append(seal['artifacts'][0])
    elif mutation=='uncommitted-orientation':
        seal['artifacts']=[x for x in seal['artifacts'] if x['path']!='orientation_description.json']
    elif mutation=='missing-consumed':
        seal['artifacts']=[x for x in seal['artifacts'] if x['path']!='population.json']
        (stage/seal['attempt']/'population.json').unlink()
    elif mutation=='extra':(stage/seal['attempt']/'unbound.json').write_text('{}')
    else:
        directory=stage/seal['attempt'];target=stage/'outside.json';target.write_text('{}')
        (directory/'population.json').unlink();(directory/'population.json').symlink_to(target)
    write(stage/'complete.json',seal)
    with pytest.raises(ValueError,match='membership|duplicate|escapes attempt'):V.population_view(root,'cross-term')


@pytest.mark.parametrize('field,value',[('schema','wrong'),('scientific_digest','wrong'),('inputs',{'mode':'synthetic','workflow':'v25'})])
def test_root_registration_required(registered,field,value):
    root,_,_=registered;p=root/'plan.json';write(p,{**V.read(p),field:value})
    with pytest.raises(ValueError,match='registered public'):V.population_view(root,'competitor')


def test_preflight_rejects_missing_base_dependency_before_comparison(tmp_path,monkeypatch):
    import importlib
    from born_ladder.reproduction.full_comparison import run_comparison
    original=importlib.import_module
    def missing(name,*a,**kw):
        if name=='sympy':raise ModuleNotFoundError('sympy')
        return original(name,*a,**kw)
    monkeypatch.setattr(importlib,'import_module',missing)
    with pytest.raises(ValueError,match='dependency missing: sympy'):
        run_comparison(run=tmp_path/'absent',archive=tmp_path/'absent',output=tmp_path/'out',v25=tmp_path/'v25')
    assert not (tmp_path/'out').exists()


def test_base_environment_prerequisites():
    assert V.comparison_preflight()=={'numpy':'2.4.4','sympy':'1.14.0','mpmath':'1.3.0'}


def test_real_selected_canonical():
    import os
    root=os.environ.get('BORN_P8_RUN')
    if not root:pytest.skip('BORN_P8_RUN supplies the read-only real P8 output')
    result=V.selected_canonical(Path(root),{'worked':'worked','census':'census','attachments':'attachments'},'specifications')
    assert result['raw'].hex()==float(0.0019104943580650346).hex()
    assert result['pkg'].hex()==float(0.001893557840725521).hex()


def test_compare_cli_forwards_optional_v25_output(tmp_path,monkeypatch):
    import born_ladder.__main__ as M
    from born_ladder.reproduction import full_comparison as F
    calls=[]
    monkeypatch.setattr(F,'run_comparison',lambda **kw:calls.append(kw) or
                        {'protocol_executed_successfully':'PASS','reported_results_reproduced':'PASS'})
    assert M.main(['reproduce','compare','--run',str(tmp_path/'run'),'--archive',str(tmp_path/'ref'),
                   '--output',str(tmp_path/'out'),'--v25-output',str(tmp_path/'v25')])==0
    assert calls[0]['v25']==tmp_path/'v25'


def test_preflight_rejects_wrong_base_version(monkeypatch):
    import importlib
    from types import SimpleNamespace
    monkeypatch.setattr(importlib,'import_module',lambda name:SimpleNamespace(__version__='wrong'))
    with pytest.raises(ValueError,match='dependency mismatch'):V.comparison_preflight()
