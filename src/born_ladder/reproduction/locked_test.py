"""Test B locked opening from committed predictions, and registered scoring.

Only numerical/data commitments are checked. No historical source receipt is
required. A reduced run must opt in explicitly and cannot establish TB01.
"""
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from pathlib import Path
import json
import os
import time

from .test_b import science, _json, _publish, _attempt
from .runs import exclusive_output, validate_output


def prediction_commit(root, *, reduced=False):
    from born_ladder.record_tests import real_v6 as R, cert_v6 as C
    root=Path(root).resolve(strict=True)
    seal=C.canonical_document(root/'prediction_seal_manifest.json')
    setup=R.phase_start(root,'seal');R.verify_phase(root,'seal')
    R.verify_files(root,seal['files'])
    # The training record view commits the census used to select contexts and
    # lags. Bind the sealed test/validation recipes to that same numerical view,
    # before opening any locked path; copying a different census is not allowed.
    view_path='record_side/view_census.json'
    if view_path not in seal['files']:
        raise ValueError('prediction commitment omits the numerical census view')
    view=C.canonical_document(root/view_path)
    if C.canonical_document(root/'census/eligibility.json')!=view:
        raise ValueError('prediction census differs from its committed view')
    for path,key in (
        ('training_census.jsonl','training_census_sha256'),
        ('sealed/full_census.jsonl','full_census_sha256'),
        ('sealed/validation_census.jsonl','sealed_validation_census_sha256'),
        ('sealed/test_census.jsonl','sealed_test_census_sha256'),
        ('sealed/recipe_audit.jsonl','sealed_recipe_audit_sha256'),
    ):
        if R.sha(root/'census'/path)!=view[key]:
            raise ValueError('prediction census numerical file differs: '+path)
    if seal['setup_sha256']!=R.sha(root/'setup.json') or seal['spec_sha256']!=R.SPEC_HASH:
        raise ValueError('prediction setup/specification differs')
    if seal['locked_test_sampled_or_opened']:
        raise ValueError('predictions were not committed before test opening')
    if seal['subset_nonconfirmatory'] and not reduced:
        raise ValueError('reduced prediction commitment requires explicit --smoke')
    # Relocated bundles resolve the numerical census from their current root,
    # rather than following an old absolute I/O annotation.
    setup={**setup,'inputs':{**setup['inputs'],'census':str(root/'census/eligibility.json')}}
    entries=R.eligible_entries(root,setup)
    counts=dict(Counter(str(r) for _,r in entries))
    if not reduced and (counts!={'2':8,'3':6,'4':6} or seal['mandatory_order_completed']!=6):
        raise ValueError('registered Test B requires complete 8/6/6 contexts and controls')
    if counts!={k:v for k,v in seal['rank_context_counts'].items() if v}:
        raise ValueError('prediction context incidence differs')
    margins=R.verify_phase(root,'fit')['summary']['sealed_margin_sha256']
    C.read_sealed_margins(root/'fits/rank_margins.json',margins)
    expected={str(root/'fits/original'/f'{R.fit_identity(e)}_r{r}'/'predictions.json') for e,r in entries}
    if not expected or any(str(Path(p).resolve().relative_to(root)) not in seal['files'] for p in expected):
        raise ValueError('not every eligible prediction is committed')
    return setup,seal,counts


def recover_partial_score(out):
    """Preserve an interrupted, uncommitted score; redo deterministic outputs.

    Completed score commitments are never repaired or overwritten. Valid cached
    bootstrap draws can be reused; truncated NumPy files cannot be mistaken for
    completed draws. No sampler or fitting operation is rerun here.
    """
    import numpy as np
    from born_ladder.record_tests import scorer_v6 as V
    out=Path(out)
    marker=out/'score.commit.json'
    if marker.exists():
        try:json.loads(marker.read_bytes())
        except (ValueError,UnicodeDecodeError):pass
        else:return
    incomplete=[]
    if marker.exists():incomplete.append(marker)
    if (out/'verdict.json').exists():incomplete.append(out/'verdict.json')
    for path in (out/'bootstrap_cache').glob('*.npy'):
        try:
            draws=np.load(path,allow_pickle=False)
            good=draws.shape==(V.DRAW_COUNT,20) and draws.dtype==np.uint8 and draws.max()<20
        except (ValueError,EOFError,OSError):good=False
        if not good:incomplete.append(path)
    if incomplete:
        attempts=out/'incomplete_scores';attempts.mkdir(exist_ok=True)
        target=attempts/f'attempt_{len(list(attempts.iterdir()))+1:04d}';target.mkdir()
        for path in incomplete:
            relative=path.relative_to(out);destination=target/relative
            destination.parent.mkdir(parents=True,exist_ok=True);path.rename(destination)


def prepare(root,out,*,reduced):
    from born_ladder.record_tests import real_v6 as R, fresh_v6 as F
    setup,seal,counts=prediction_commit(root,reduced=reduced)
    value={'schema':'born_regenerated_locked_setup_v1','p5_root':str(root),
           'p5_seal_sha256':R.sha(root/'prediction_seal_manifest.json'),
           'profile':'reduced' if reduced else 'regenerated','rank_counts':counts}
    _json(out/'setup.json',value)
    if (out/'prepare.commit.json').exists():return F.verify_commit(out,'prepare')
    files=[]
    for name in ('training_census.jsonl','eligibility.json','sealed/full_census.jsonl',
                 'sealed/validation_census.jsonl','sealed/test_census.jsonl','sealed/recipe_audit.jsonl'):
        _publish(out/'census'/name,(root/'census'/name).read_bytes());files.append(out/'census'/name)
    F.validate_census(out/'census')
    return F.commit(out,'prepare',files,{'status':'COMPLETE','profile':value['profile']})


def sample(root,out,*,workers,sampler,reduced):
    import subprocess
    from born_ladder.record_tests import real_v6 as R, cert_v6 as C, fresh_v6 as F
    setup,seal,_=prediction_commit(root,reduced=reduced)
    F.phase_start(root,out,'sample')
    if (out/'sample.commit.json').exists():return F.verify_commit(out,'sample')
    _json(out/'opening.json',{'blocks':list(range(910036,910056)),'recipes':list(range(48,60)),
          'prediction_commitment':R.sha(root/'prediction_seal_manifest.json'),
          'sampling_rule':'deterministic replay of committed kernel header; no dynamics or refitting'})
    headers=C.canonical_document(root/'header_inventory.json');bykey={(x['exp'],x['config']):x for x in headers}
    def task(unit):
        work=out/'jobs'/R.job_name(unit);marker=work/'complete.json'
        if marker.exists():
            result=C.canonical_document(marker);R.verify_files(out,result['files']);return result
        attempt=_attempt(work);sides=attempt/'sidecars';sides.mkdir()
        for name in ('eligibility.json','sealed/recipe_audit.jsonl'):
            _publish(attempt/'census'/name,(root/'census'/name).read_bytes())
        # The historical sampler compares train/validation header bytes before
        # opening test paths. Copy those header lines, never refit or resample.
        for folder in ('audit_side','record_side'):
            matches=[]
            for p in (root/folder).glob('*.jsonl'):
                with p.open('rb') as stream:raw=stream.readline()
                header=json.loads(raw)
                if (header.get('exp'),header.get('config'))==(unit['exp'],unit['config']):matches.append((p,raw))
            if len(matches)!=1:raise ValueError('committed trainval header missing or duplicated')
            _publish(sides/matches[0][0].name,matches[0][1])
        argv=[str(Path(sampler).resolve()),'--header',str(root/'headers'/bykey[(unit['exp'],unit['config'])]['file']),
              '--output',str(sides),'--locked-test','--predictions-root',str(root)]
        _json(attempt/'started.json',{'argv':argv});began=time.monotonic()
        run=subprocess.run(argv,capture_output=True,env={**os.environ,**{p:'1' for p in R.PINS}})
        _publish(attempt/'stdout',run.stdout);_publish(attempt/'stderr',run.stderr)
        if run.returncode:
            _json(attempt/'failed.json',{'exit_code':run.returncode})
            raise ValueError('locked sampler failed: '+run.stderr.decode(errors='replace'))
        audit=next(sides.glob('*.v6.fresh_test.audit.jsonl'));record=next(sides.glob('*.v6.fresh_test.record.jsonl'))
        F.validate_sidecars(audit,record,collect=False)
        files=[]
        for p,folder in ((audit,'audit_side'),(record,'record_side')):
            target=out/folder/p.name;_publish(target,p.read_bytes());files.append(target)
        result={'files':R.tree_hashes(out,files),'wall_seconds':time.monotonic()-began,
                'exp':unit['exp'],'config':unit['config']};_json(marker,result);return result
    # Header replay is deterministic. Incomplete attempts are preserved and redone,
    # never replaced; committed predictions cannot be changed on resume.
    with ThreadPoolExecutor(max_workers=workers) as pool:rows=list(pool.map(task,setup['units']))
    paths=[out/'opening.json']
    for row in rows:paths.extend(out/p for p in row['files'])
    return F.commit(out,'sample',paths,{'status':'COMPLETE','units':len(rows),'blocks':20,
                    'recipes':12,'paths_per_kernel':7680,'states_per_path':65})


def run_locked(*,predictions,output,workers=1,specifications='specifications',
               sampler='vendor/pica/target/release/test-b-sampler',smoke=False):
    start=time.monotonic();R,C,E,runtime=science(specifications)
    root=Path(predictions).resolve(strict=True);out=validate_output(output,Path.cwd())
    if root==out or root.is_relative_to(out) or out.is_relative_to(root):
        raise ValueError('locked outputs must be disjoint from committed predictions')
    if workers<1:raise ValueError('workers must be positive')
    setup,seal,counts=prediction_commit(root,reduced=smoke)
    if setup['runtime']!=runtime:raise ValueError('Test B computing runtime differs from fitting runtime')
    out.mkdir(parents=True,exist_ok=True)
    from born_ladder.record_tests import fresh_v6 as F
    with exclusive_output(out):
        prepare(root,out,reduced=smoke);sample(root,out,workers=workers,sampler=sampler,reduced=smoke)
        previous=F.RANK_COUNTS
        try:
            if smoke:F.RANK_COUNTS=counts  # explicit reduced incidence, isolated child
            recover_partial_score(out)
            result=F.score(root,out)
        finally:F.RANK_COUNTS=previous
        _json(out/'qualification.json',{'profile':'reduced' if smoke else 'regenerated',
              'historical_TB01_asserted':False,'bootstrap_draws':200000,'rank_counts':counts})
    return {'status':'COMPLETE','profile':'reduced' if smoke else 'regenerated',
            'verdict':result['summary']['category'],'wall_seconds':time.monotonic()-start}
