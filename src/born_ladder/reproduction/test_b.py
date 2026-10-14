"""Public Test B production through committed predictions; no real test opening.

Science lives in record_tests. This module only coordinates public inputs,
parallel tasks and recoverable attempts. Registered and smoke runs never share
outputs; smoke completion does not certify the registered campaign.
"""
from concurrent.futures import ThreadPoolExecutor
from born_ladder.record_tests.workers import process_pool as ProcessPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from .runs import Manifest, RunSpecifications, exclusive_output, validate_output
from .stage_environment import check_current, profile_path


def science(specifications):
    os.environ['BORN_LADDER_TEST_B_PROFILE']=str(profile_path(specifications,'test_b_fitting'))
    from born_ladder.record_tests import real_v6 as R, cert_v6 as C, estimators as E
    contract=json.loads((Path(specifications)/'test_b.json').read_bytes())
    from born_ladder.record_tests import test_b_census_v6 as census
    from born_ladder.record_tests.test_b_census import THRESHOLD
    expected={'recipes':{'total':census.RECIPE_COUNT,'train':census.TRAIN_COUNT,
                         'validation':census.VALID_COUNT,'test':census.TEST_COUNT},
              'bootstrap_draws':C.V.DRAW_COUNT,'closure_threshold':THRESHOLD,
              'data_design_sha256':R.DATA_DESIGN_HASH,'inference_rng_identity':R.SPEC_HASH,
              'kernel_seed':910000,'scale':32,'calibration_draws':C.G.CALIBRATION_DRAWS,
              'replicates':C.G.REPLICATES,'lags':list(C.LAGS)}
    if any(contract[key]!=value for key,value in expected.items()):
        raise ValueError('Test B public contract differs from registered scientific implementation')
    if (contract['fit']['starts'],contract['fit']['warm_iterations'],contract['fit']['polish_iterations'])!=(E.V5_STARTS,E.V5_WARM_ITER,E.V5_POLISH_ITER):
        raise ValueError('Test B public fit budgets differ from registered implementation')
    if (contract['fit']['floor'],contract['fit']['checkpoints'],contract['fit']['legacy_control_identity'])!=(E.FLOOR,list(E.CHECKPOINTS),E.SPEC_HASH):
        raise ValueError('Test B loss/checkpoint/RNG contract differs from registered implementation')
    if contract['effective_seal_controls']!=R.CONTROL_RULES:
        raise ValueError('Test B control contract differs from registered implementation')
    profile = json.loads(profile_path(specifications, 'test_b_fitting').read_bytes())
    return R, C, E, check_current(profile)


def _publish(path, raw):
    path = Path(path);path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw: raise ValueError('completed input/output differs: '+str(path))
        return
    temporary = path.with_name(path.name+'.tmp')
    with temporary.open('wb') as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())
    temporary.replace(path)


def _json(path, value):
    from .runs import encoded
    _publish(path, encoded(value))


def _attempt(root):
    folder = Path(root)/'attempts';folder.mkdir(parents=True, exist_ok=True)
    count = max([int(p.name.removeprefix('attempt_')) for p in folder.glob('attempt_*')],default=0)+1
    path = folder/f'attempt_{count:04d}';path.mkdir();return path


def inventory(*, output, runs=None, headers=None, specifications='specifications', smoke=False):
    """Copy header lines only. Old calibration/path rows cannot reach a fitter."""
    if bool(runs) == bool(headers): raise ValueError('supply exactly one of --runs or --headers')
    source = []
    if runs:
        root = Path(runs).resolve();manifest = Manifest(root)
        completed = manifest.completed()
        expected = RunSpecifications(specifications).grid('test-b')
        if not smoke and [job.id for job in expected] != [r['id'] for r in json.loads((root/'runset.json').read_bytes())['invocations']]:
            raise ValueError('Test B kernel grid membership/order differs')
        if not smoke and set(completed) != {job.id for job in expected}:
            raise ValueError('complete Test B kernel grid required')
        excluded=[]
        for identifier,row in completed.items():
            if identifier not in {job.id for job in expected}:
                excluded.append({'invocation_id':identifier,'reason':'not in the registered Test B kernel grid'})
                continue
            source.extend(root/a['path'] for a in row['artifacts'] if '/headers/' in a['path'] and a['path'].endswith('.audit.jsonl'))
        _json(Path(output)/'capture_dispositions.json',{'excluded_invocations':excluded})
    else: source = sorted(Path(headers).glob('*.audit.jsonl'))
    from born_ladder.record_tests.test_b_census_v6 import source_header
    rows=[];identities=set()
    for path in sorted(source):
        header, digest = source_header(path);key=(header['exp'],header['config'])
        if not smoke and header['n']!=32:raise ValueError('registered Test B requires scale-32 kernel headers')
        if key in identities: raise ValueError('duplicate Test B captured kernel')
        identities.add(key)
        with path.open('rb') as stream:raw=stream.readline()
        _publish(Path(output)/'headers'/path.name, raw)
        rows.append({'exp':key[0],'config':key[1],'header_sha256':digest,'file':path.name})
    if not rows or (not smoke and len(rows)!=140):raise ValueError('expected 140 Test B kernel headers; use --smoke for an explicit reduced run')
    _json(Path(output)/'header_inventory.json',rows)
    return rows


def census_stage(root, *, workers, smoke):
    from born_ladder.record_tests import test_b_census_v6 as census
    final=root/'census'
    if not final.exists():
        attempt=_attempt(root/'census_work')
        census.run(root/'headers',attempt/'census',workers=workers,
                   expected_units=len(list((root/'headers').glob('*.audit.jsonl'))) if smoke else 140)
        (attempt/'census').rename(final)
    release=json.loads((final/'eligibility.json').read_bytes())
    # Numerical checkpoint integrity, not a historical receipt/source gate.
    for field,name in [('training_census_sha256','training_census.jsonl'),
                       ('sealed_recipe_audit_sha256','sealed/recipe_audit.jsonl')]:
        if hashlib.sha256((final/name).read_bytes()).hexdigest()!=release[field]:
            raise ValueError('completed census data changed: '+name)
    return {'stage':'census','unit_count':release['unit_count'],
            'eligible_per_rank':release['eligible_per_rank'],'smoke_nonconfirmatory':smoke}


def _draw_task(item):
    from born_ladder.record_tests import cert_v6 as C
    kind,index=item
    return C.draw_digest(C.plant(kind,index))


def domain(C, root, kind, count, workers):
    folder=root/kind;folder.mkdir(exist_ok=True)
    target=folder/'draw_commitment.json'
    if target.exists():
        rows=C.canonical_document(target)
        if len(rows)!=count or [r['index'] for r in rows]!=list(range(count)):
            raise ValueError('synthetic draw inventory differs')
        return rows
    with ProcessPoolExecutor(max_workers=workers) as pool:
        rows=list(pool.map(_draw_task,[(kind,i) for i in range(count)]))
    _json(target,rows);return rows


def recover_unfinished_checkpoints(target, output_root):
    """Recover only incomplete writes in a phase lacking its completion marker.

    Complete canonical rows remain in order. Numeric products of already
    completed phases are validated, never repaired or silently replaced.
    """
    target=Path(target);output_root=Path(output_root)
    for path in sorted(target.rglob('*.jsonl')):
        raw=path.read_bytes()
        if not raw or raw.endswith(b'\n'):continue
        offset=raw.rfind(b'\n')+1
        saved=output_root/'incomplete'/path.relative_to(output_root)
        saved=saved.with_name(saved.name+'.tail')
        saved.parent.mkdir(parents=True,exist_ok=True)
        counter=0
        while saved.exists():counter+=1;saved=saved.with_name(saved.name+f'.{counter}')
        _publish(saved,raw[offset:])
        with path.open('r+b') as stream:
            stream.truncate(offset);stream.flush();os.fsync(stream.fileno())
    for path in sorted(target.rglob('*.json')):
        try:json.loads(path.read_bytes())
        except (ValueError,UnicodeDecodeError):_preserve_partial(path,output_root)
    for path in sorted(target.rglob('*.npy')):
        import numpy as np
        try:np.load(path,allow_pickle=False)
        except (ValueError,EOFError):_preserve_partial(path,output_root)


def validate_certification(root):
    from born_ladder.record_tests import cert_v6 as C
    target=Path(root)/'certification'
    C.configure(output=target,census=Path(root)/'census/eligibility.json')
    complete=C.canonical_document(target/'complete.json')
    if complete['status']!='PASS' or complete.get('smoke_nonconfirmatory'):
        raise ValueError('registered synthetic certification must pass before real sampling')
    gates=[C.verify_fidelity_verdict('fidelity',200,180),C.verify_split_verdict(),C.verify_pseudo_verdict()]
    for kind in C.FAMILIES:
        gates.extend([C.verify_fidelity_verdict(kind,100,90),C.verify_pooled_verdict(kind)])
    if any(gate['status'] not in ('PASS','INELIGIBLE') for gate in gates):
        raise ValueError('registered synthetic certification failed')
    return complete


def certify_stage(root, *, specifications, workers):
    R,C,E,runtime=science(specifications)
    target=root/'certification';target.mkdir(exist_ok=True)
    C.configure(output=target,census=root/'census/eligibility.json');C.WORKERS=workers
    if (target/'complete.json').exists():
        try:return validate_certification(root)
        except json.JSONDecodeError:_preserve_partial(target/'complete.json',root)
    recover_unfinished_checkpoints(target,root)
    if (target/'split_state/closure_results.json').exists() and not (target/'split_state/verdict.json').exists():
        _preserve_partial(target/'split_state/closure_results.json',root)
    began=time.monotonic();gates=[]
    def fidelity(kind,count,minimum):
        draws=domain(C,target,kind,count,workers)
        path=target/kind/'verdict.json'
        if path.exists():
            verdict=C.canonical_document(path)
            if verdict['status']=='PASS':C.verify_fidelity_verdict(kind,count,minimum)
        else:verdict=C.fidelity_gate(kind,count,minimum,draws,early_stop=kind=='fidelity',resume=True)
        gates.append(verdict)
        if verdict['status']!='PASS':raise ValueError('Test B synthetic fidelity failed: '+kind)
        return draws
    fidelity('fidelity',200,180)
    draws=domain(C,target,'quadratic',100,workers)
    diagnostics=[{'index':i,'normalization_attempt':C.plant('quadratic',i,paths=False).parameters['attempt'],
                  'normalization_rejections':C.plant('quadratic',i,paths=False).parameters['rejections']} for i in range(100)]
    _json(target/'quadratic/diagnostic.json',{'gate':'quadratic_generator_diagnostic','status':'DESCRIPTIVE',
        'draws':100,'cases':diagnostics,'C95_train':0.,'L':0.})
    for kind in C.FAMILIES:
        draws=fidelity(kind,100,90)
        path=target/kind/'pooled_verdict.json'
        verdict=C.verify_pooled_verdict(kind) if path.exists() else C.pooled_false_square(kind,draws,resume=True)
        gates.append(verdict)
        if verdict['status'] not in ('PASS','INELIGIBLE'):raise ValueError('Test B false-square control failed: '+kind)
    draws=domain(C,target,'split_state',100,workers)
    path=target/'split_state/verdict.json'
    verdict=C.verify_split_verdict() if path.exists() else C.split_control(draws)
    gates.append(verdict)
    if verdict['status']!='PASS':raise ValueError('Test B split-state control failed')
    path=target/'pseudocampaign/verdict.json'
    verdict=C.verify_pseudo_verdict() if path.exists() else C.pseudocampaigns(resume=(target/'pseudocampaign').exists())
    gates.append(verdict)
    if verdict['status']!='PASS':raise ValueError('Test B census-matched pseudo-campaign failed')
    result={'status':'PASS','stage':'certification','gates':gates,'runtime':runtime,
            'wall_seconds':time.monotonic()-began,'smoke_nonconfirmatory':False}
    _json(target/'complete.json',result);return result


def sample_stage(root, *, specifications, workers, sampler, smoke, only):
    R,C,E,runtime=science(specifications)
    census=json.loads((root/'census/eligibility.json').read_bytes())
    if not smoke:
        validate_certification(root)
    names=set(only or [])
    units=[u for u in census['units'] if not names or u['exp']+':'+u['config'] in names]
    if names != {u['exp']+':'+u['config'] for u in units} and names:raise ValueError('unknown Test B kernel subset')
    setup={'schema':'test_b_real_v6_1_p5_setup_v1','spec_sha256':R.SPEC_HASH,
        'data_design_sha256':R.DATA_DESIGN_HASH,'subset':smoke or bool(names),
        'inputs':{'census':str((root/'census/eligibility.json').resolve())},'units':units,
        'runtime':runtime}
    if (root/'setup.json').exists():
        stored=C.canonical_document(root/'setup.json')
        if {key:stored.get(key) for key in setup}!=setup:raise ValueError('Test B numerical setup differs on resume')
    else:_json(root/'setup.json',setup)
    if not (root/'gates.commit.json').exists():
        _json(root/'gates/qualification.json',{'synthetic_certified':not smoke,'smoke_nonconfirmatory':smoke})
        R.commit_phase(root,'gates',[root/'gates/qualification.json'],{'status':'PASS' if not smoke else 'SMOKE_NONCONFIRMATORY'})
    if (root/'sample.commit.json').exists():return R.verify_phase(root,'sample')['summary']
    if not Path(sampler).is_file():
        subprocess.run(['cargo','build','--offline','--release','-p','test_b_sampler','--manifest-path',str(Path('vendor/pica/Cargo.toml').resolve())],check=True)
    inventory=C.canonical_document(root/'header_inventory.json')
    by_identity={(r['exp'],r['config']):r for r in inventory}
    def task(unit):
        key=(unit['exp'],unit['config']);work=root/'sampling'/R.job_name(unit)
        marker=work/'result.json'
        if marker.exists():
            result=C.canonical_document(marker);R.verify_files(root,result['files']);return result
        attempt=_attempt(work);(attempt/'sidecars').mkdir()
        for relative in ('eligibility.json','sealed/recipe_audit.jsonl'):
            _publish(attempt/'census'/relative,(root/'census'/relative).read_bytes())
        command=[str(Path(sampler).resolve()),'--header',str((root/'headers'/by_identity[key]['file']).resolve()),
                 '--output',str((attempt/'sidecars').resolve())]
        _json(attempt/'started.json',{'exp':key[0],'config':key[1],'status':'started','argv':command})
        started=time.monotonic();run=subprocess.run(command,capture_output=True)
        _publish(attempt/'stdout',run.stdout);_publish(attempt/'stderr',run.stderr)
        if run.returncode:
            _json(attempt/'failed.json',{'exp':key[0],'config':key[1],'status':'failed',
                'exit_code':run.returncode,'wall_seconds':time.monotonic()-started})
            raise ValueError('Rust trainval sampler failed: '+run.stderr.decode(errors='replace'))
        record=next((attempt/'sidecars').glob('*.record.jsonl'));audit=next((attempt/'sidecars').glob('*.audit.jsonl'))
        checked=R.validate_sample(record,audit,unit)
        for file,target in [(record,'record_side'),(audit,'audit_side')]:_publish(root/target/file.name,file.read_bytes())
        paths=[root/'record_side'/record.name,root/'audit_side'/audit.name]
        result={'exp':key[0],'config':key[1],'wall_seconds':time.monotonic()-started,
                'checked':checked,'files':R.tree_hashes(root,paths)}
        _json(marker,result);return result
    with ThreadPoolExecutor(max_workers=workers) as pool:results=list(pool.map(task,units))
    selected={(u['exp'],u['config']) for u in units}
    view={**census,'unit_count':len(units),'units':units,
          'training_contexts':[c for c in census['training_contexts'] if (c['exp'],c['config']) in selected]}
    _json(root/'record_side/view_census.json',view)
    if not (root/'record_view').exists():
        attempt=_attempt(root/'filter_work')
        R.RV.build(root/'record_side',root/'record_side/view_census.json',attempt/'record_view')
        (attempt/'record_view').rename(root/'record_view')
    loader=E.RecordAllowlist(root/'record_view/manifest.json')
    for path in loader.allowed:loader.load(Path(path))
    summary=R.calibration_census(root/'record_side',root/'record_side')
    paths=[p for folder in ('record_side','audit_side','record_view') for p in (root/folder).iterdir() if p.is_file()]
    return R.commit_phase(root,'sample',paths,{'status':'PASS','kernels':len(units),
              'eligible_contexts':len(loader.allowed),**summary})['summary']


def _preserve_partial(path, root):
    destination=root/'incomplete'/path.relative_to(root)
    destination.parent.mkdir(parents=True,exist_ok=True)
    suffix=0
    while destination.exists():suffix+=1;destination=destination.with_name(destination.name+f'.{suffix}')
    path.rename(destination)


def fit_stage(root, *, specifications, workers):
    R,C,E,runtime=science(specifications)
    setup=C.canonical_document(root/'setup.json')
    if setup['runtime']!=runtime:raise ValueError('incompatible Test B numerical resume')
    for directory in (root/'fits/original').glob('*'):
        if not directory.is_dir():continue
        marker=directory/'result.json'
        if not marker.exists():_preserve_partial(directory,root)
        else:
            try:C.canonical_document(marker)
            except (ValueError,json.JSONDecodeError):_preserve_partial(directory,root)
    if (root/'fit.commit.json').exists():
        try:C.canonical_document(root/'fit.commit.json')
        except json.JSONDecodeError:_preserve_partial(root/'fit.commit.json',root)
    for name in ('timing.json','rank_margins.json'):
        path=root/'fits'/name
        if path.exists():
            try:C.canonical_document(path)
            except json.JSONDecodeError:_preserve_partial(path,root)
    return R.fit(root,workers)['summary']


def allowlist_control(root,loader,rejected):
    """Report the admitted run's cells and its own committed record manifest."""
    from born_ladder.archive import sha
    recipes=set();blocks=set();calibration=set()
    for path in loader.loader.allowed:
        record=loader.load(Path(path))
        recipes.update(map(int,record.recipes));blocks.update(map(int,record.blocks))
        calibration.update(map(int,record.calibration))
    return {'status':'PASS','rejected':rejected,'sampled_test_paths':0,
            'allowed_path_recipes':sorted(recipes),'allowed_seed_blocks':sorted(blocks),
            'calibration_only_recipes':sorted(calibration-recipes),
            'manifest_sha256':sha(Path(root)/'record_view/manifest.json')}


def commit_stage(root, *, specifications, workers):
    R,C,E,runtime=science(specifications)
    setup=R.phase_start(root,'seal')
    if setup['runtime']!=runtime:raise ValueError('incompatible Test B numerical resume')
    if (root/'prediction_seal_manifest.json').exists():
        R.verify_phase(root,'seal')
        saved=C.canonical_document(root/'prediction_seal_manifest.json');R.verify_files(root,saved['files'])
        # Supplement old completed commitments without changing any prediction,
        # fit, margin or already committed file.
        _json(root/'controls/erasure_diagnostics.json',R.erasure_diagnostics(root,R.eligible_entries(root,setup)))
        return saved
    recover_unfinished_checkpoints(root/'controls',root)
    if (root/'seal.commit.json').exists():
        R.verify_phase(root,'seal')
    entries=R.eligible_entries(root,setup)
    equivariance=R.literal_relabel_refits(root,entries,workers)
    loader=R.P5RecordLoader(root);rejected=[]
    for name in ('audit.audit.jsonl','old_v5.json','locked_910036.record.jsonl'):
        target=root/'controls/allowlist_probes'/name;_json(target,{'forbidden':True})
        try:loader.load(target)
        except PermissionError:rejected.append(name)
        else:raise ValueError('record loader admitted forbidden inputs')
    _json(root/'controls/allowlist.json',allowlist_control(root,loader,rejected))
    # Same scientific omission as the effective amendment; no approval receipt.
    _json(root/'controls/erasure.json',R.erasure_diagnostics(root,entries))
    audit_marker=root/'controls/training_audit.complete.json'
    audit_file=root/'controls/training_audit_1000.json'
    if audit_marker.exists():
        checkpoint=C.canonical_document(audit_marker)
        if R.sha(audit_file)!=checkpoint['data_sha256']:raise ValueError('completed training-audit numeric data changed')
        audit=checkpoint['summary']
    else:
        audit=R.training_audit(root,entries,workers)
        _json(audit_marker,{'data_sha256':R.sha(audit_file),'summary':audit})
    paths=[p for p in (root/'controls').rglob('*') if p.is_file()]
    R.commit_phase(root,'seal',paths,{'status':'PASS','equivariance':'PASS',
        'literal_full_refits':equivariance['actual_full_refits'],
        'allowlist':'PASS','structural_erasure':'NOT_COMPUTED','structural_erasure_refits':0,
        'training_block_audit':audit,'locked_test_sampled_or_opened':False})
    files={}
    for phase in R.PHASES:
        part=R.verify_phase(root,phase);files.update(part['files']);files[f'{phase}.commit.json']=R.sha(root/f'{phase}.commit.json')
    result={'schema':'test_b_v6_1_p6_required_seal_v1','spec_sha256':R.SPEC_HASH,
        'setup_sha256':R.sha(root/'setup.json'),'subset_nonconfirmatory':setup['subset'],'files':files,
        'rank_context_counts':{str(r):sum(rank==r for _,rank in entries) for r in (2,3,4)},
        'locked_test_sampled_or_opened':False,'mandatory_order_completed':None if setup['subset'] else 6,
        'structural_erasure':'NOT_COMPUTED','control_rules':R.CONTROL_RULES}
    _json(root/'prediction_seal_manifest.json',result);return result


def run_test_b(*, output, stage='all', runs=None, headers=None, specifications='specifications',
               workers=1, smoke=False, only=None, sampler='vendor/pica/target/release/test-b-sampler'):
    if workers<1:raise ValueError('--workers must be positive')
    root=validate_output(output,Path(specifications).resolve().parent)
    root.mkdir(parents=True,exist_ok=True)
    stages=('census','certify','sample','fit','commit')
    if stage not in (*stages,'all'):raise ValueError('unknown Test B production stage')
    science(specifications)
    with exclusive_output(root):
        inventory(output=root,runs=runs,headers=headers,specifications=specifications,smoke=smoke)
        _json(root/'production_plan.json',{'schema':'test_b_production_v1','smoke_nonconfirmatory':smoke,
                                         'only':list(only or []),'runtime':science(specifications)[3]})
        results={}
        if stage not in ('all','census') and not (root/'census').exists():
            census_stage(root,workers=workers,smoke=smoke)
        for name in stages if stage=='all' else (stage,):
            if name=='census':results[name]=census_stage(root,workers=workers,smoke=smoke)
            elif name=='certify':
                if smoke:
                    from .test_b_smoke import smoke_certification
                    results[name]=smoke_certification(census=root/'census/eligibility.json',output=root/'certification',specifications=specifications,workers=workers)
                else:results[name]=certify_stage(root,specifications=specifications,workers=workers)
            elif name=='sample':results[name]=sample_stage(root,specifications=specifications,workers=workers,
                sampler=sampler,smoke=smoke,only=only)
            elif name=='fit':results[name]=fit_stage(root,specifications=specifications,workers=workers)
            elif name=='commit':results[name]=commit_stage(root,specifications=specifications,workers=workers)
        return {'stage':stage,'results':results,'locked_test_sampled_or_opened':False,
                'smoke_nonconfirmatory':smoke or bool(only)}
