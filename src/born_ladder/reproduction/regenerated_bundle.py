"""Portable regenerated evidence. Never admitted by the historical trust anchor.

This profile verifies numerical constructions and scores of this run, not the
paper's historical outcomes. Historical-only claims have explicit dispositions.
"""
import json
import gc
from fractions import Fraction
from pathlib import Path
from collections import Counter
from born_ladder.archive import sha, put, canonical, qserial

SCHEMA='born_regenerated_bundle_v1'
GROUPS={
 'worked':('P01','P02','B04','B05','B06','B07'),
 'census':('P03','P10','P13','B08','B09','B10','B13'),
 'attachments':('P11',),'evaluation':('P12',),'test_b':('TB01',)}
HISTORICAL_ONLY={'B01':'historical role records are not new-run evidence',
 'B11':'a fresh run cannot establish the historical executable/source correspondence',
 'B12':'historical selected-case return attachment is not regenerated'}


def safe(root,name):
    p=Path(root)/name
    if Path(name).is_absolute() or '..' in Path(name).parts or not p.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError('bundle member escapes root: '+name)
    return p


def assemble(pipeline,output):
    import os
    source=Path(pipeline).resolve(strict=True);out=Path(output).resolve();out.mkdir(parents=True,exist_ok=True)
    state=json.loads((source/'pipeline.json').read_bytes())
    required={'worked','census','attachments','competitor_evaluation','cross_term_evaluation','test_b','locked','lean','competitor_units','cross_term_units'}
    if set(state['components'])!=required:raise ValueError('pipeline component inventory incomplete')
    roots={};files={}
    for name,relative in state['components'].items():
        root=safe(source,relative).resolve(strict=True)
        roots[name]=os.path.relpath(root,out)
        members={str(p.relative_to(root)):sha(p) for p in sorted(root.rglob('*'))
                 if p.is_file() and '.lake' not in p.parts and '__pycache__' not in p.parts}
        if not members:raise ValueError('empty bundle component: '+name)
        files[name]=members
    doc={'schema':SCHEMA,'profile':'regenerated','reduced':state['profile']=='smoke',
         'roots':roots,'files':files,'claim_groups':{k:list(v) for k,v in GROUPS.items()},'historical_only':HISTORICAL_ONLY,
         'qualification':'new-run numerical checks; no historical outcome or full-cohort claim from reduced runs'}
    path=out/'bundle.json'
    if path.exists():
        previous=json.loads(path.read_bytes())
        if {k:v for k,v in previous.items() if k!='files'}!={k:v for k,v in doc.items() if k!='files'}:
            raise ValueError('completed bundle contract differs')
        for name,members in previous['files'].items():
            if any(doc['files'][name].get(p)!=digest for p,digest in members.items()):
                raise ValueError('completed bundle data differs')
        if previous==doc:return {'profile':'regenerated','reduced':doc['reduced'],'files':sum(map(len,files.values())),'bundle':str(path)}
        # A resumed stage can append a cost record or a build log. Keep the old
        # inventory and publish a new inventory; never permit a changed or
        # removed numerical product to masquerade as such an addition.
        records=out/'inventories';records.mkdir(exist_ok=True)
        if not list(records.glob('bundle_*.json')):put(records/'bundle_0001.json',previous)
        put(records/f'bundle_{len(list(records.glob("bundle_*.json")))+1:04d}.json',doc)
        temp=out/'bundle.next.json';temp.write_text(json.dumps(doc,indent=2,sort_keys=True)+'\n');temp.replace(path)
    else:put(path,doc)
    return {'profile':'regenerated','reduced':doc['reduced'],'files':sum(map(len,files.values())),'bundle':str(path)}


class Bundle:
    def __init__(self,path):
        self.file=Path(path);self.file=self.file/'bundle.json' if self.file.is_dir() else self.file
        self.doc=json.loads(self.file.read_bytes())
        if self.doc.get('schema')!=SCHEMA or self.doc.get('profile')!='regenerated':
            raise ValueError('explicit regenerated bundle required; historical bundles are not accepted')
        self.roots={k:(self.file.parent/v).resolve(strict=True) for k,v in self.doc['roots'].items()}
        if set(self.roots)!=set(self.doc['files']):raise ValueError('bundle root inventory differs')
        for name,members in self.doc['files'].items():
            for path,digest in members.items():
                if sha(safe(self.roots[name],path))!=digest:raise ValueError('regenerated numeric file changed: '+name+'/'+path)


def check_locked(bundle):
    from born_ladder.record_tests import scoring, independent, fresh_v6 as F, cert_v6 as C, scorer_v6 as V, real_v6 as R
    from .locked_test import prediction_commit
    p5,p6=bundle.roots['test_b'],bundle.roots['locked']
    _,_,counts=prediction_commit(p5,reduced=bundle.doc['reduced'])
    F.verify_commit(p6,'score')
    archived=C.canonical_document(p6/'verdict.json');rows=[];ind=[];maxerror=0.
    units={};test={}
    with (p6/'census/sealed/test_census.jsonl').open() as f:
        for line in f:
            x=json.loads(line);test.setdefault((F.identity(x),x['h']),[]).append(x['C'])
    setup=C.canonical_document(p5/'setup.json');setup={**setup,'inputs':{**setup['inputs'],'census':str(p5/'census/eligibility.json')}}
    for entry,rank in R.eligible_entries(p5,setup):
        key=(entry['exp'],entry['config'])
        if key not in units:
            audit=next(p for p in (p6/'audit_side').glob('*.audit.jsonl') if tuple(F.read_header(p)[x] for x in ('exp','config'))==key)
            units[key]=F.validate_sidecars(audit,p6/'record_side'/audit.name.replace('.audit.','.record.'))
        head,_,labels=units[key];context=next(c for c in head['contexts'] if (c['k'],c['step_index'])==(entry['k'],entry['step_index']))
        pred=C.canonical_document(p5/'fits/original'/f'{R.fit_identity(entry)}_r{rank}'/'predictions.json')
        lab=labels[(entry['k'],entry['step_index'])];law=scoring.oracle_laws(head,context,entry['h_c'])
        contrasts,report=scoring.evaluate_context(pred,lab,law)
        ident=F.identity(entry);values=test[(ident,entry['h_c'])]
        row={'id':json.dumps(ident,separators=(',',':')),'rank':rank,'laws':law,'contrasts':contrasts,'test_C_values':values};rows.append(row)
        from born_ladder.record_tests.verify import differences
        old=next(r for r in archived['contexts'] if r['context']==entry and r['rank']==rank)
        maxerror=max(maxerror,differences(report,{k:old[k] for k in report}))
        ind.append(independent.reconstruct_case(entry,pred,lab,head,context,values))
    margins={int(k):v for k,v in C.canonical_document(p6/'margins.json')['margins'].items()}
    bs={f:V.bootstrap_indices(f,p6/'bootstrap_cache') for f in ('primary','reversal','order')}
    actual=scoring.campaign(rows,margins,bs)
    from born_ladder.record_tests.verify import differences
    error=differences(actual,{k:archived[k] for k in actual})
    independent_error=None
    if all(counts.get(str(r),0)>0 for r in (2,3,4)):
        other=independent.reconstruct(ind,margins,bs)
        independent_error=differences(other,{k:archived[k] for k in other})
        if other['inference']!=archived['inference']:raise ValueError('independent inference differs')
    if actual['inference']!=archived['inference'] or max(error,maxerror,independent_error or 0)>1e-8:
        raise ValueError('regenerated record scores do not reproduce')
    return {'numerically_verified':True,'category':actual['category'],'inference_exact':True,
            'loss_max_error':maxerror,'independent_max_error':independent_error,'contexts':len(rows),
            'historical_informative_negative_required':False}


def population_json(value):
    """Use put's qserial/JSON representation, permitting only container changes.

    Validate types before qserial can stringify keys or the JSON encoder can
    accept a NumPy float subclass. Unsupported scientific values must fail,
    rather than be converted by a default=str/tolist hook. canonical uses the
    same sorted-key, allow_nan=False encoder as put, with compact whitespace.
    """
    def check(item):
        kind=type(item)
        if kind in (str,int,float,bool,type(None)):
            return
        if kind is dict:
            for key,child in item.items():
                if type(key) is not str:
                    raise TypeError('non-string population key: '+type(key).__name__)
                check(child)
        elif kind in (list,tuple):
            for child in item:check(child)
        else:
            raise TypeError('non-JSON population value: '+kind.__name__)
    check(value)
    return json.loads(canonical(qserial(value)))


def _verify_population(bundle,name,*,workers=1):
    """One replay scope: no competitor results survive into the rotation pool."""
    root=bundle.roots[name]
    if (root/'smoke_inference.json').exists():
        from .smoke_stages import verify_population
        verify_population(json.loads((root/'smoke_inference.json').read_bytes()))
        return
    from .evaluation import closed_inputs,PopulationSpecification,cross_term_inputs
    from born_ladder.snapshot.universal_shapes import validate_stage_records
    from born_ladder.snapshot.g2a import evaluate_g2a_records
    from born_ladder.snapshot.g2c_evaluate import evaluate_g2c_records
    from born_ladder.snapshot.g2c_controls import gradual_underflow_certificate
    seal=json.loads((root/'complete.json').read_bytes())
    saved=root/seal['summary']['evaluation_path']
    evaluation='competitor' if name.startswith('competitor') else 'cross-term'
    spec=PopulationSpecification('specifications',evaluation)
    inputs=closed_inputs(bundle.roots['competitor_units' if evaluation=='competitor' else 'cross_term_units'],evaluation,'specifications')
    _,_,records,directories,structural,attempts,commitments,info=inputs
    if evaluation=='competitor':
        valid=validate_stage_records(spec,records,stage_profile='g2a',expected_structural_manifest_sha256=structural,expected_attempt_record_sha256=attempts)
        actual=evaluate_g2a_records(spec,valid,
            provenance={'public_input_commitments':commitments},
            completeness={'public_collection_complete':True,'invocations':info['completed_invocations']})
    else:
        controls,rotations,sources,projections=cross_term_inputs(spec,records,directories)
        rotation_options={}
        if workers>1:
            from .rotation_admission import parallel_rotations
            rotation_options['rotation_validator']=parallel_rotations('specifications',sources,controls,rotations,workers)
        with gradual_underflow_certificate():
            actual=evaluate_g2c_records(spec,records,controls,rotation_evidence=rotations,control_sources=sources,control_input_projections=projections,**rotation_options)
    # Recomputation (and any pool) is finished before loading either reference.
    # Saved scientific values and metadata never feed either inference.
    original=json.loads(saved.read_bytes())
    # Only JSON container normalization is allowed; every scientific value,
    # field, membership, sensitivity and verdict must match exactly.
    from .census_comparison import Comparison
    comparison=Comparison(project_bindings=False)
    comparison.compare('population',population_json(actual),original)
    if not comparison.result()['overall_agreement']:
        raise ValueError('full regenerated population inference differs')


def verify_group(bundle,group,*,workers=1):
    if group=='worked':
        from .lean_inputs import checked_worked,R,T,E,F,O
        original,cert,data,ri=checked_worked(bundle.roots['worked'])
        if not bundle.doc['reduced']:
            texts={'RIInputs':R.render_checked(ri),'B04Inputs':T.render_checked(original,data['B04']),
                   'B05Inputs':E.render_checked(cert['ensemble'],data['B05']),
                   'B06Inputs':F.render_checked(data['B06']),'B07Inputs':O.render_checked(data['B07'])}
            for name,text in texts.items():
                if (bundle.roots['lean']/'BornCalculus'/(name+'.lean')).read_bytes()!=text.encode():
                    raise ValueError('worked claim inputs differ from bundle Lean project: '+name)
        return {'exact_certificates_rederived':True,'worked_Lean_input_binding':not bundle.doc['reduced']}
    if group=='census':
        root=bundle.roots[group]
        summary=json.loads((root/'complete.json').read_bytes())['summary']
        if summary.get('selected_count')==2122:
            from .census_extension import verify_census
            return verify_census(root)
        from .lean_inputs import census_records
        coverage_path=bundle.roots['lean']/'formal_coverage.json'
        applicable=coverage_path.exists() and json.loads(coverage_path.read_bytes())['status']=='APPLICABLE'
        rows,pairs=census_records(bundle.roots[group],expected_count=None,registered=applicable)
        bound=all(Fraction(p['gap_exact'])>=Fraction(3,20) for p in pairs) if pairs else None
        return {'exact_cases_rederived':len(rows),'full_120_case_claim':applicable and not bundle.doc['reduced'],
                'full_2122_case_claim':False,'registered_gap_bound_satisfied':bound,'formal_coverage':'registered inputs' if applicable else 'not applicable to this cohort'}
    if group=='test_b':return check_locked(bundle)
    if group=='attachments':
        from born_ladder.independent import verify_summaries
        root=bundle.roots[group];complete=json.loads((root/'complete.json').read_bytes());summary=complete['summary']
        # Attachment stage writes a manifest of each case's immutable unit fields.
        paths=list(root.rglob('descriptive_summaries.json'))
        if not paths:raise ValueError('descriptive summaries missing')
        attached=[]
        for p in root.rglob('*.attachment.json'):attached.append(json.loads(p.read_bytes()))
        if not attached:
            for p in root.rglob('attachments.json'):attached=json.loads(p.read_bytes())
        if not attached:raise ValueError('attachment rows missing')
        verify_summaries(attached,json.loads(paths[0].read_bytes()))
        return {'exact_rational_quantiles_verified':True,'rows':len(attached)}
    if group=='evaluation':
        # Reduced population kernels save all seed vectors/draw membership;
        # full evaluations are rerun by the inference entrypoint in its own stage.
        for name in ('competitor_evaluation','cross_term_evaluation'):
            _verify_population(bundle,name,workers=workers)
            # Release any cycles from this replay before opening the next one.
            gc.collect()
        return {'numerical_artifacts_verified':True,'reduced_kernel_replay':bundle.doc['reduced'],
                'full_population_recomputed_here':not bundle.doc['reduced']}
    raise ValueError('unknown regenerated verification group')


def verify(identifier,data,*,lean_root='lean_born',certificate_output=None,workers=1):
    from born_ladder.full_cohort_claims import IDS,verify as verify_full
    file=Path(data);file=file/'bundle.json' if file.is_dir() else file
    document=json.loads(file.read_bytes()) if file.is_file() else {}
    reduced=document.get('reduced') is True
    if reduced and certificate_output is not None:
        raise ValueError('an exact full-cohort P13 receipt is unavailable for a reduced run')
    if identifier in IDS and not reduced:
        return {'profile':'regenerated','status':'VERIFIED','id':identifier,
                'historical_claim_asserted':False,
                'checks':verify_full(identifier,data,lean_root,certificate_output=certificate_output)}
    b=Bundle(data)
    if identifier in HISTORICAL_ONLY:return {'profile':'regenerated','status':'NOT_APPLICABLE','reason':HISTORICAL_ONLY[identifier]}
    group=next((k for k,v in GROUPS.items() if identifier in v),None)
    if group is None:
        from born_ladder.__main__ import REGISTRY,verify_claim
        if REGISTRY[identifier][1]=='data':raise ValueError('unknown regenerated data endpoint')
        coverage=b.roots['lean']/'formal_coverage.json'
        if coverage.exists():
            formal=json.loads(coverage.read_bytes())
            if formal.get('census_cases')==2122 and formal['status']!='APPLICABLE':
                raise ValueError('full-cohort formal certification is required; NOT_APPLICABLE cannot satisfy the census amendment')
        if b.doc['reduced'] or (coverage.exists() and json.loads(coverage.read_bytes())['status']!='APPLICABLE'):
            return {'profile':'regenerated','status':'NOT_APPLICABLE','reason':'not applicable to this cohort: full Lean endpoints require complete registered inputs; reduced/off-cohort data cannot certify them'}
        return {'profile':'regenerated','status':'VERIFIED','id':identifier,'formal_or_control_check':verify_claim(identifier,lean_root=b.roots['lean'])}
    result=verify_group(b,group,workers=workers)
    if identifier in ('P01','P02') and not b.doc['reduced']:
        from born_ladder.__main__ import verify_claim
        result['formal_or_control_check']=verify_claim(identifier,lean_root=b.roots['lean'])
    if group=='worked' and identifier not in ('P01','P02') and not b.doc['reduced']:
        from born_ladder.__main__ import REGISTRY,audit_endpoints
        result['axiom_audit']=audit_endpoints(b.roots['lean'],REGISTRY[identifier][2])
    return {'profile':'regenerated','status':'REDUCED_NONCONFIRMATORY' if b.doc['reduced'] else 'VERIFIED',
            'id':identifier,'reduced':b.doc['reduced'],'full_cohort_claim_asserted':False,
            'historical_claim_asserted':False,'checks':result}


def group_receipt(ids,receipts,*,reduced=False):
    """A successful exit cannot stand in for missing claim-specific evidence."""
    expected='REDUCED_NONCONFIRMATORY' if reduced else 'VERIFIED'
    if set(receipts)!=set(ids):raise ValueError('group receipt lacks claim-specific checks')
    for identifier in ids:
        receipt=receipts[identifier]
        if (receipt.get('id')!=identifier or receipt.get('status')!=expected
                or not receipt.get('checks')):
            raise ValueError('group receipt lacks claim-specific checks: '+identifier)
        if not reduced:
            required={'P01':('exact_certificates_rederived','worked_Lean_input_binding','formal_or_control_check'),
                      'P02':('exact_certificates_rederived','worked_Lean_input_binding','formal_or_control_check'),
                      **{i:('exact_certificates_rederived','worked_Lean_input_binding','axiom_audit') for i in ('B04','B05','B06','B07')},
                      'P12':('numerical_artifacts_verified','full_population_recomputed_here'),
                      'TB01':('numerically_verified','inference_exact','contexts'),
                      'P03':('numerical_cases','public_K_map_replay'),
                      'P10':('axiom_audit','validation_coverage'),
                      'B08':('axiom_audit','validation_coverage'),
                      'P11':('records','type_7_summaries'),
                      'P13':('per_case_witnesses','axiom_audit','registered_3_over_20'),
                      'B09':('overall','coordinate','symbolic','bit_equality'),
                      'B10':('active','positive','singular','axiom_audit'),
                      'B13':('collection','rank_two','rank_counts')}.get(identifier,())
            if any(field not in receipt['checks'] for field in required):
                raise ValueError('group receipt lacks claim-specific obligations: '+identifier)
    return {'status':expected,'claim_ids':[] if reduced else list(ids),
            'reduced_check_ids':list(ids) if reduced else [],'claim_receipts':receipts,
            'full_cohort_claim_asserted':False if reduced else any(i in ('P03','P10','P13','B08','B09','B10','B13','P11') for i in ids)}
