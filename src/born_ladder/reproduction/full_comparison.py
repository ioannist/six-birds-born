"""Complete post-run P8 comparison; never an input to production.

Accept a relocated historical claim bundle or explicit comparison reference
manifest. Missing evidence is UNRESOLVED, never a match. Reduced cohorts are
NOT_COMPARABLE. Output is always separate from the run and the archive.
"""
from contextlib import contextmanager
from dataclasses import asdict
import csv
import hashlib
import json
from pathlib import Path
import re
import resource
import time

from .comparison_policy import PolicyComparison, PROCESS_FIELDS, render
from .runs import RunSpecifications, Manifest


def read(path):
    with Path(path).open() as stream:return json.load(stream)


def bytes_equal(a,b):
    with Path(a).open('rb') as x,Path(b).open('rb') as y:
        while True:
            left,right=x.read(2**20),y.read(2**20)
            if left!=right:return False
            if not left:return True


class Reference:
    """Only caller-supplied roots; no archive discovery or private Git reads."""
    def __init__(self,path):
        self.file=Path(path).resolve();self.doc=read(self.file)
        if 'historical_bundle' in self.doc:
            custom=self.doc;bundle_file=(self.file.parent/custom['historical_bundle']).resolve();self.doc=read(bundle_file)
            self.doc['roots']={k:str((bundle_file.parent/v).resolve()) for k,v in self.doc['roots'].items()}
            self.doc.update({k:v for k,v in custom.items() if k not in ('schema','historical_bundle')})
        self.roots={k:(self.file.parent/v).resolve() for k,v in self.doc.get('roots',{}).items()}
        self.bundle=self.doc.get('schema')=='born_claim_bundle_v1'
        if not self.bundle and self.doc.get('schema')!='born_reproduction_reference_v1':
            raise ValueError('archive must be a claim bundle or born_reproduction_reference_v1')

    def path(self,name):
        root,relative=name.split('/',1)
        p=Path(relative)
        if p.is_absolute() or '..' in p.parts:raise ValueError('reference path escapes root')
        result=self.roots[root]/p
        if not result.resolve().is_relative_to(self.roots[root]):raise ValueError('reference symlink escapes root')
        return result

    def read(self,name):return read(self.path(name))

    def location(self,name):
        if name in self.doc.get('components',{}):return self.path(self.doc['components'][name])
        if not self.bundle:raise FileNotFoundError('reference component not supplied: '+name)
        c=self.doc['claims']
        if name=='census':return self.path(c['P10']['contexts']).parent
        if name=='worked':return self.path(c['B04']['context']).parent.parent
        if name=='lean':return self.roots['repo']/'lean_born'
        if name=='test_b':return self.roots['p5']
        if name=='locked':return self.roots['p6']
        if name=='certification':return self.roots['cert']
        if name=='test_b_census':return self.roots['cert'].parent/'census'
        if name=='ledger':raise FileNotFoundError('supply --ledger explicitly for paper macro comparison')
        raise FileNotFoundError('reference component not supplied: '+name)

    @contextmanager
    def artifact(self,evaluation,name):
        if self.bundle:
            from born_ladder.claims import artifact
            item=self.doc['claims']['P12']['g2a' if evaluation=='competitor' else 'g2c'][name]
            with artifact(self,item) as (stream,_,__):yield stream
        else:
            path=self.path(self.doc['predictive'][evaluation][name])
            with path.open('rb') as stream:yield stream


def scientific_lines(path):
    """All emitted scientific rows, in order; exclude timing/log chatter only."""
    with Path(path).open('rb') as stream:
        for line in stream:
            if line.startswith(b'KEY_') and b'JSON ' in line:
                tag,body=line.rstrip(b'\n').split(b' ',1)
                # Structural end records contain bytes/hash/process bookkeeping;
                # scientific rows themselves are compared independently below.
                if b'STRUCTURAL_END' in tag:continue
                yield [tag.decode(),json.loads(body)]


def compare_file(c,group,a,b,*,binary=False):
    a,b=Path(a),Path(b)
    if a.name.endswith('.seal.json'):
        # Prediction payloads are separate numerical files in the same tree.
        # Their sealing path, serialization size and digest are storage fields,
        # not another estimator. Never drop an actual prediction file.
        for path in (a,b):
            if not Path(str(path).removesuffix('.seal.json')).is_file():
                raise FileNotFoundError('prediction seal has no numerical payload: '+str(path))
        x,y=read(a),read(b)
        for key in sorted(set(x)|set(y)):
            if key in ('path','bytes','sha256'):
                if x.get(key)!=y.get(key):c.record('prediction_seal_storage',str(a)+'/'+key,x.get(key),y.get(key),'named storage projection; numerical payload independently compared',True)
            else:c.compare(group,x.get(key),y.get(key),str(a)+'/'+key)
        return
    if binary or a.suffix not in ('.json','.jsonl'):
        equal=bytes_equal(a,b)
        c.compare(group,{'bytes':a.stat().st_size,'byte_equal':equal},
                        {'bytes':b.stat().st_size,'byte_equal':True},str(a))
    elif a.suffix=='.jsonl':
        with a.open() as x,b.open() as y:
            from itertools import zip_longest
            for i,(left,right) in enumerate(zip_longest(x,y)):
                if left is None or right is None:
                    c.compare(group,left,right,str(a)+'/'+str(i))
                else:c.compare(group,json.loads(left),json.loads(right),str(a)+'/'+str(i))
    elif a.name=='erasure.json' and group=='literal_refits_order_and_controls':
        def completed(path):
            value=read(path);supplement=path.with_name('erasure_diagnostics.json')
            if supplement.is_file():
                extra=read(supplement)
                for key in set(value)&set(extra):
                    c.compare('erasure_supplement_consistency',value[key],extra[key],str(path)+'/'+key)
                value={**value,**extra}
            return value
        compare_erasure(c,completed(a),completed(b),str(a))
    else:
        from .comparison_bindings import file_bindings, documentary
        x,y=file_bindings(c,a,b,read(a),read(b))
        if a.name=='verdict.json' and group=='locked_scoring_and_verdict':
            x,y=dict(x),dict(y)
            if 'erasure' in x.get('descriptive_controls',{}) and 'erasure' in y.get('descriptive_controls',{}):
                ex,ey=documentary(c,x['descriptive_controls']['erasure'],y['descriptive_controls']['erasure'],
                                  ERASURE_DOCUMENTARY_FIELDS,str(a)+'/descriptive_controls/erasure')
                x['descriptive_controls']={**x['descriptive_controls'],'erasure':ex}
                y['descriptive_controls']={**y['descriptive_controls'],'erasure':ey}
        c.compare(group,x,y,str(a))


ERASURE_DOCUMENTARY_FIELDS=frozenset(('manager_approval','manager_ruling','spec_quote','spec_reference'))
ERASURE_DIAGNOSTIC_FIELDS=frozenset(('campaign_context_figures','subset_infeasibility_reference'))


def compare_erasure(c,actual,reference,path='erasure.json'):
    """The registered omission is scientific; approvals are documentary.

    Diagnostic counts/memberships are never called documentary: absent ones
    are unresolved, and present ones are compared recursively in full.
    Unknown fields stay scientific, so an invented field cannot disappear.
    """
    omitted=ERASURE_DOCUMENTARY_FIELDS|ERASURE_DIAGNOSTIC_FIELDS
    c.compare('erasure_scientific_disposition',
        {k:v for k,v in actual.items() if k not in omitted},
        {k:v for k,v in reference.items() if k not in omitted},path)
    for key in sorted(ERASURE_DOCUMENTARY_FIELDS & (set(actual)|set(reference))):
        row={'field':path+'/'+key,'generated':actual.get(key),'reference':reference.get(key),
             'historical_matches':0,
             'disposition':'HISTORICAL_DOCUMENTARY_ONLY','reason':'approval or explanatory reference; does not enter a gate, estimator or verdict'}
        c.documentary_fields.append(row)
        c.record('historical_documentary_fields',row['field'],row['generated'],row['reference'],row['disposition'],True)
    for key in sorted(ERASURE_DIAGNOSTIC_FIELDS):
        if key in actual and key in reference:
            c.compare('erasure_quantitative_diagnostics',actual[key],reference[key],path+'/'+key)
        else:
            row={'field':path+'/'+key,'generated':actual.get(key),'reference':reference.get(key),
                 'disposition':'UNRESOLVED_QUANTITATIVE_DIAGNOSTIC',
                 'reason':'quantitative diagnostic/membership has no corresponding product; not counted as matched'}
            c.unresolved_diagnostics.append(row)
            c.record('unresolved_quantitative_diagnostics',row['field'],row['generated'],row['reference'],row['disposition'],False)


def compare_tree(c,group,a,b,*,exclude=()):
    a,b=Path(a),Path(b)
    if not a.is_dir() or not b.is_dir():raise FileNotFoundError('required tree: '+str(a)+' / '+str(b))
    def files(root):
        return {str(p.relative_to(root)):p for p in root.rglob('*') if p.is_file()
                and p.suffix in ('.json','.jsonl','.npy','.npz','.csv','.bin')
                and not any(token in p.relative_to(root).parts for token in ('attempts','incomplete','incomplete_checkpoints'))
                and not p.name.endswith(('.commit.json','.complete.json'))
                and not p.name.startswith('resume_manifest')
                and p.name not in exclude}
    x,y=files(a),files(b)
    if not x or not y:raise ValueError('empty scientific tree: '+group)
    c.compare(group+'_file_membership',sorted(x),sorted(y))
    for name in sorted(set(x)&set(y)):compare_file(c,group,x[name],y[name])


def last_attempt(root):
    doc=read(Path(root)/'complete.json')
    summary=doc['summary']
    return Path(root)/summary['directory'] if 'directory' in summary else (Path(root)/summary['evaluation_path']).parent


def predictive_draw_counts(doc,evaluation):
    """Check the saved full-contract primary draws; never generate draws."""
    statistics=doc['statistics']
    if not statistics:raise ValueError('no population endpoints')
    counts={}
    for name,stat in statistics.items():
        primary=stat if evaluation=='competitor' else stat['bootstrap']
        counts[name]=len(primary['replicate_estimates'])
        if counts[name]!=20000:raise ValueError('reduced primary bootstrap: '+name)
        if 'rng_audit' in primary and len(primary['rng_audit'])!=20000:
            raise ValueError('incomplete primary RNG audit: '+name)
    return counts


def package_evidence_counts(units, reconstruction):
    """Decode raw/package kind from the registered immutable cell identity.

    Cross-term unit schema v23 has no `kind` field. The reconstruction JSONL
    identifies raw-only source units whose package evidence was constructed.
    Every unit must have exactly one raw and one package output cell.
    """
    from born_ladder.snapshot.identities import kind_cell_id
    paired={}
    with Path(units).open() as stream:
        for line in stream:
            row=json.loads(line)
            if not isinstance(row,dict) or not isinstance(row.get('unit_id'),str):
                raise ValueError('cross-term unit row has no valid unit_id')
            uid=row['unit_id']
            kinds=[kind for kind in ('raw','pkg') if kind_cell_id(uid,kind)==row.get('kind_cell_id')]
            if len(kinds)!=1:raise ValueError('cannot decode cross-term kind_cell_id for '+uid)
            kind=kinds[0]
            if 'kind' in row and row['kind']!=kind:raise ValueError('cross-term kind disagrees with immutable cell identity: '+uid)
            existing=paired.setdefault(uid,set())
            if kind in existing:raise ValueError('duplicate cross-term '+kind+' cell: '+uid)
            existing.add(kind)
    if not paired or any(kinds!={'raw','pkg'} for kinds in paired.values()):
        raise ValueError('cross-term raw/package join incomplete')
    reconstructed=set()
    with Path(reconstruction).open() as stream:
        for line in stream:
            row=json.loads(line)
            if not isinstance(row,dict) or not isinstance(row.get('unit_id'),str):
                raise ValueError('package reconstruction row has no valid unit_id')
            uid=row['unit_id']
            if uid not in paired:raise ValueError('package reconstruction has no joined unit: '+uid)
            if uid in reconstructed:raise ValueError('duplicate package reconstruction: '+uid)
            reconstructed.add(uid)
    return {'dual_kind_parity_units':len(paired)-len(reconstructed),'reconstructed_units':len(reconstructed)}


def locked_draw_counts(root):
    """Validate persisted full-contract index arrays, without inference."""
    import numpy as np
    files=sorted((Path(root)/'bootstrap_cache').glob('*.npy'))
    families={}
    for p in files:
        family=next((name for name in ('primary','reversal','order') if '_'+name+'_' in p.name),None)
        if family is None or family in families:raise ValueError('unknown or duplicate locked bootstrap family')
        array=np.load(p,mmap_mode='r',allow_pickle=False)
        if array.shape!=(200000,20) or array.dtype!=np.uint8 or array.max()>=20:
            raise ValueError('reduced or invalid locked bootstrap indices: '+p.name)
        families[family]=array.shape[0]
    if set(families)!={'primary','reversal','order'}:raise ValueError('locked bootstrap family missing')
    return families


def protocol(root,specifications,profile):
    """Numerical completion/accounting, independent of the optional archive."""
    result={}
    grids=(('g2a','competitor'),('g2c','cross-term'),('worked-cases','worked'),('test-b','test-b')) if profile=='full' else ((read(Path(specifications)/'reproduction_smoke.json')['runner_grid'],'smoke'),)
    specs=RunSpecifications(specifications)
    for grid,label in grids:
        name='runs/'+label;directory=root/name
        try:
            plan=read(directory/'runset.json');expected=[{'id':j.id,**asdict(j)} for j in specs.grid(grid)]
            if plan['invocations']!=expected or len({r['id'] for r in expected})!=len(expected):
                raise ValueError('registered grid membership/order differs')
            completed=Manifest(directory).completed();last={r['invocation_id']:r for r in Manifest(directory).rows if r['event']=='finished'}
            unknown=set(last)-{r['id'] for r in expected}
            if unknown:raise ValueError('unexpected invocations: '+str(sorted(unknown)))
            # latest failed/interrupted attempt may not be replaced by an earlier
            # success. Successful resume attempts remain separately accounted.
            missing=[r['id'] for r in expected if r['id'] not in completed or last.get(r['id'],{}).get('status')!='completed']
            result[name]={'status':'UNRESOLVED' if missing else 'PASS','expected':len(expected),'completed':len(completed),
                          'unfinished':missing,'manifest_attempts':len(Manifest(directory).rows)}
        except FileNotFoundError as e:result[name]={'status':'UNRESOLVED','reason':str(e)}
        except (ValueError,KeyError) as e:result[name]={'status':'FAIL','reason':str(e)}
    requirements={'census':'complete.json','worked':'selected/certificates.json','attachments':'complete.json',
                  'test-b':'prediction_seal_manifest.json','locked':'score.commit.json','lean':'formal_coverage.json',
                  'bundle':'bundle.json'}
    if profile=='full':requirements.update({'units/competitor':'collections','units/cross-term':'collections',
                   'evaluation/competitor':'complete.json','evaluation/cross-term':'complete.json'})
    else:requirements.update({'units/smoke':'collections','evaluation/competitor':'smoke_inference.json',
                              'evaluation/cross-term':'smoke_inference.json'})
    if profile=='smoke' and not (root/'lean/formal_coverage.json').exists():requirements['lean']='input_build.json'
    for name,marker in requirements.items():
        path=root/name/marker
        try:
            if name.startswith('units/'):
                paths=sorted(path.glob('collection_*/collection.json'))
                if not paths:raise FileNotFoundError('no closed unit collection: '+str(path))
                doc=read(paths[-1]);entries=doc.get('evaluations',{})
                if not entries or any(not r['complete'] or r['completed_invocations']!=r['expected_invocations'] for r in entries.values()):
                    raise ValueError('incomplete unit collection')
                if profile=='full':
                    evaluation=name.split('/')[-1]
                    count=len(specs.grid('g2a' if evaluation=='competitor' else 'g2c'))
                    if set(entries)!={evaluation} or entries[evaluation]['expected_invocations']!=count:
                        raise ValueError('unit collection denominator differs from registered run grid')
            else:doc=read(path)
            if name=='worked' and not (root/'worked/original/certificates.json').exists():raise FileNotFoundError('original worked certificate missing')
            if name=='test-b' and (doc.get('locked_test_sampled_or_opened') or profile=='full' and doc.get('subset_nonconfirmatory')):
                raise ValueError('prediction commitment is late or reduced')
            result[name]={'status':'PASS','marker':str(path.relative_to(root))}
        except FileNotFoundError as e:result[name]={'status':'UNRESOLVED','reason':str(e)}
        except (KeyError,ValueError) as e:result[name]={'status':'FAIL','reason':str(e)}
    try:
        report=read(root/'verification_report.json')
        expected_status='REDUCED_NONCONFIRMATORY' if profile=='smoke' else 'VERIFIED'
        if report['status']!='COMPLETE' or report['profile']!=profile or set(report['checks'])!={'worked','census','attachments','evaluation','test_b'} or any(r['status']!=expected_status for r in report['checks'].values()):
            raise ValueError('regenerated verification report incomplete')
        if profile=='smoke' and any(row.get('claim_ids')!=[] or row.get('full_cohort_claim_asserted') is not False
                                   for row in report['checks'].values()):
            raise ValueError('reduced verification report asserts confirmatory claims')
        from .regenerated_bundle import Bundle
        Bundle(root/'bundle') # checks every recorded numerical output, read-only
        result['verification']={'status':'PASS','formal_coverage':report['formal_endpoints']}
    except FileNotFoundError as e:result['verification']={'status':'UNRESOLVED','reason':str(e)}
    except (ValueError,KeyError) as e:result['verification']={'status':'FAIL','reason':str(e)}
    verdict='FAIL' if any(r['status']=='FAIL' for r in result.values()) else 'UNRESOLVED' if any(r['status']!='PASS' for r in result.values()) else 'PASS'
    return {'verdict':verdict,'stages':result,'scientific_negative_result_is_execution_failure':False}


def run_comparison(*,run,archive,output,specifications='specifications',ledger=None,aliases=None,paper=None,v25=None):
    if v25 is not None:
        from .v25_paper import comparison_preflight
        comparison_preflight()
    start=time.monotonic();cpu=time.process_time()
    root=Path(run).resolve(strict=True);output=Path(output).resolve()
    ref=Reference(archive)
    protected=[root]
    if v25 is not None:protected.append(Path(v25).resolve(strict=True))
    for component in ('census','worked','lean','test_b','test_b_census','locked','certification'):
        try:protected.append(ref.location(component))
        except (FileNotFoundError,KeyError):pass
    for source in protected:
        if output==source or output.is_relative_to(source):raise ValueError('comparison output must be separate from run/archive inputs')
    output.mkdir(parents=True,exist_ok=True)
    attempts=output/'attempts';attempts.mkdir(exist_ok=True)
    dest=attempts/f'attempt_{len(list(attempts.glob("attempt_*")))+1:04d}';dest.mkdir()
    state=read(root/'pipeline.json');profile=state['profile']
    execution=protocol(root,Path(specifications),profile)
    stages={};components=state['components'];populations={}
    def stage(name,callback,required):
        began=time.monotonic()
        if profile!='full':
            stages[name]={'status':'NOT_COMPARABLE','reason':'reduced profile: not comparable with registered archive'};return
        if any(not (root/p).exists() for p in required):
            stages[name]={'status':'UNRESOLVED','evidence_disposition':'MISSING_GENERATED_OUTPUT',
                          'missing_generated_outputs':[p for p in required if not (root/p).exists()],
                          'reason':'production stage not complete; missing '+', '.join(p for p in required if not (root/p).exists())};return
        try:
            with (dest/(name.replace('/','_')+'_differences.jsonl')).open('w') as stream:
                c=PolicyComparison(stream)
                extra=callback(c) or {}
                result={**c.result(),**extra,'historical_documentary_fields':c.documentary_fields,
                        'unresolved_quantitative_diagnostics':c.unresolved_diagnostics,
                        'unresolved_reference_fields':c.unresolved_reference_fields}
            status='PASS' if result['overall_agreement'] else 'FAIL'
            if result.get('new_case_validation_agreement') is False:status='FAIL'
            if (result.get('unavailable_stored_reference_files') or result.get('unavailable_paper_quantities') or c.unresolved_diagnostics or c.unresolved_reference_fields) and result.get('new_case_validation_agreement',True) and not any(g['failed'] for g in c.result()['field_groups'].values()):status='UNRESOLVED'
            if status=='PASS' and result.get('resolved_with_declared_limits'):status='PASS_WITH_DECLARED_LIMITS'
            result.update(status=status,wall_seconds=time.monotonic()-began)
            result['comparison_coverage']=coverage_summary(result)
            stages[name]=result
        except (FileNotFoundError,KeyError) as e:
            assessment=c.result() if 'c' in locals() else {}
            stages[name]={**assessment,'status':'FAIL' if any(r.get('failed',0) for r in assessment.get('field_groups',{}).values()) else 'UNRESOLVED',
                          'evidence_disposition':'MISSING_REQUIRED_INPUT_OR_REFERENCE','reason':str(e)}
        except (ValueError,RuntimeError,TypeError,AssertionError) as e:
            assessment=c.result() if 'c' in locals() else {}
            stages[name]={**assessment,'status':'FAIL','reason':str(e)}
        (dest/(name.replace('/','_')+'.json')).write_text(json.dumps(stages[name],indent=2)+'\n')

    for grid,label in (('g2a','competitor'),('g2c','cross-term'),('worked-cases','worked'),('test-b','test-b')):
        def runs(c,label=label):
            from .units import source_inputs
            captures=ref.doc.get('captures',{}).get(label)
            if captures is None:raise FileNotFoundError('supply archive captures.'+label+' (complete retained capture-index or P2a root)')
            old,_=source_inputs([ref.path(captures)]);plan=read(root/'runs'/label/'runset.json');completed=Manifest(root/'runs'/label).completed()
            keys=[(j['experiment'],j['configuration'],j['seed'],j['scale']) for j in plan['invocations']]
            c.compare('invocation_membership',sorted(keys,key=str),sorted(old,key=str),label)
            if keys!=list(old):
                c.record('capture_index_storage_order',label,keys,list(old),
                    'capture index serialization/dispatch order; registered grid order checked against public plan, all downstream scientific row orders exact',True)
            unfinished=[];count=0
            for j,key in zip(plan['invocations'],keys):
                if j['id'] not in completed:unfinished.append(j['id']);continue
                if key not in old:continue  # membership comparison already fails
                actual=root/'runs'/label/completed[j['id']]['directory']/'stdout.bin'
                expected=Path(old[key]['root'])/old[key]['stdout_path']
                c.compare('source_scientific_inputs',list(scientific_lines(actual)),list(scientific_lines(expected)),j['id'])
                count+=1
            if unfinished:raise FileNotFoundError('unfinished invocations ('+str(len(unfinished))+'); completed scientific captures compared: '+str(count))
            return {'completed_captures_compared':count,'coverage':'all stdout scientific payloads in acquisition order'}
        stage('runs/'+label,runs,['runs/'+label+'/runset.json'])

    for evaluation,key in (('competitor','competitor_units'),('cross-term','cross_term_units')):
        def units(c,evaluation=evaluation,key=key):
            from .census import collection_inputs
            from .unit_comparison import compare_records
            _,_,_,unit_name,files,_,info=collection_inputs(root/components[key],evaluation)
            with ref.artifact(evaluation,'units') as stream:
                exact=compare_records(files[unit_name],stream,comparison=c)
            accepted=c.result()['overall_agreement'] and not exact['missing_rows'] and not exact['extra_rows'] and exact['row_order_exact']
            return {'overall_agreement':accepted,'exact_comparator':exact,'unit_rows':info['unit_rows']}
        stage('units/'+evaluation,units,[components[key]+'/collections'])

    def census(c):
        from .census_comparison import compare_census
        return compare_census(root/components['census'],ref.location('census'),lean_root=ref.location('lean'),comparison=c)
    stage('census',census,[components['census']+'/complete.json'])
    def worked(c):
        from .worked_comparison import compare_worked_cases
        return compare_worked_cases(root/components['worked'],ref.location('worked'),comparison=c,
            non_trace=ref.path(ref.doc['non_trace_reference']) if ref.doc.get('non_trace_reference') else None,
            source_runs=[root/'runs/worked'],specifications=specifications,lean_root=root/components['lean'])
    stage('worked',worked,[components['worked']+'/selected/certificates.json',components['worked']+'/original/certificates.json'])
    def lean(c):
        from .lean_comparison import compare_lean, log_receipt
        target=root/components['lean']
        oldaudit=ref.doc.get('lean_audit')
        if oldaudit is None:raise FileNotFoundError('supply reference lean_audit with the complete endpoint audit')
        retained=ref.doc.get('lean_historical_sources')
        if retained is None:
            raise FileNotFoundError('supply reference lean_historical_sources naming the retained historical source tree')
        coverage=read(target/'formal_coverage.json')
        for key,expected in (('audit_receipt','audit_receipt.json'),('build_receipt','build_receipt.json')):
            c.compare('fresh_Lean_receipt_locations',coverage.get(key),expected,key)
        audit=read(target/'audit_receipt.json');build=read(target/'build_receipt.json')
        c.compare('fresh_Lean_audit_log_binding',audit,log_receipt(root/'logs/lean-audit.log','allowed_axioms'))
        c.compare('fresh_Lean_build_log_binding',build,log_receipt(root/'logs/lean.log','modules'))
        populations['lean_audit']=audit
        return compare_lean(c,target=target,historical_sources=ref.path(retained),audit=audit,
            historical_audit=read(ref.path(oldaudit)),coverage=coverage,build=build,workspace=dest)
    stage('lean',lean,[components['lean']+'/formal_coverage.json'])
    for evaluation,key in (('competitor','competitor_evaluation'),('cross-term','cross_term_evaluation')):
        def inference(c,evaluation=evaluation,key=key):
            from .evaluation_comparison import WRAPPER_FIELDS,compare_values
            new=read(last_attempt(root/components[key])/'evaluation.json')
            with ref.artifact(evaluation,'evaluation') as stream:old=json.load(stream)
            draws=predictive_draw_counts(new,evaluation)
            predictive_draw_counts(old,evaluation)
            a={k:v for k,v in new.items() if k not in WRAPPER_FIELDS};b={k:v for k,v in old.items() if k not in WRAPPER_FIELDS}
            exact=compare_values(a,b);c.compare('population',a,b)
            for field in sorted(WRAPPER_FIELDS):
                if new.get(field)!=old.get(field):c.record('wrapper_provenance',field,new.get(field),old.get(field),'named archive wrapper projection',True)
            if 'package_evidence_census' in old:
                from .census import collection_inputs
                _,_,_,unit_name,files,_,info=collection_inputs(root/components['cross_term_units'],'cross-term')
                reconstruction_name=read(Path(specifications)/'units.json')['evaluations']['cross-term']['package_reconstruction_file']
                if Path(reconstruction_name).name!=reconstruction_name:
                    raise ValueError('package reconstruction specification must name a collection file')
                reconstruction=Path(files[unit_name]).parent/reconstruction_name
                c.compare('package_evidence_denominators',package_evidence_counts(files[unit_name],reconstruction),old['package_evidence_census'])
            populations[evaluation]=paper_projection(new)
            return {'exact_comparator':exact,'excluded_wrapper_fields':sorted(WRAPPER_FIELDS),'primary_draw_counts':draws}
        stage('evaluation/'+evaluation,inference,[components[key]+'/complete.json'])
    def attachments(c):
        from .attachment_comparison import compare_attachments
        new=last_attempt(root/components['attachments']);old=ref.location('census')
        return compare_attachments(new,old,root/components['census'],root/components['cross_term_units'],c)
    stage('attachments',attachments,[components['attachments']+'/complete.json'])

    def test_b_census(c):
        old=ref.location('test_b_census');new=root/components['test_b']/'census'
        for name in ('eligibility.json','training_census.jsonl','sealed/full_census.jsonl','sealed/validation_census.jsonl','sealed/test_census.jsonl','sealed/recipe_audit.jsonl'):
            compare_file(c,'recipes_eligibility_and_lags',new/name,old/name)
    stage('test-b/census',test_b_census,[components['test_b']+'/census/eligibility.json'])
    def certification(c):
        compare_tree(c,'synthetic_certification',root/components['test_b']/'certification',ref.location('certification'),
                     exclude=('code_freeze.json','estimator_ast_comparison.json','resume_manifest.json','complete.json'))
    stage('test-b/certification',certification,[components['test_b']+'/certification/complete.json'])
    def training(c):
        old=ref.location('test_b');new=root/components['test_b']
        for name in ('audit_side','record_side','record_view'):
            compare_tree(c,'sampled_sequences',new/name,old/name)
    stage('test-b/sampling',training,[components['test_b']+'/sample.commit.json'])
    def fitting(c):
        old=ref.location('test_b');new=root/components['test_b']
        compare_tree(c,'fits_selectors_predictions_margins',new/'fits',old/'fits',exclude=('timing.json',))
        compare_tree(c,'literal_refits_order_and_controls',new/'controls',old/'controls',
                     exclude=('clarifications.json','erasure_diagnostics.json'))
        a,b=read(new/'prediction_seal_manifest.json'),read(old/'prediction_seal_manifest.json')
        from .comparison_bindings import documentary
        if 'control_rules' in a and 'control_rules' in b:
            rules_a,rules_b=documentary(c,a['control_rules'],b['control_rules'],{'manager_approval'},'prediction_seal_manifest/control_rules')
            a={**a,'control_rules':rules_a};b={**b,'control_rules':rules_b}
        # Files/seals contain storage hashes; all numerical files above are
        # compared independently. Scientific incidence and commitment timing stay.
        c.compare('prediction_commitment',{k:v for k,v in a.items() if k!='files'}, {k:v for k,v in b.items() if k!='files'})
    stage('test-b/fits',fitting,[components['test_b']+'/prediction_seal_manifest.json'])
    def locked(c):
        new=root/components['locked'];old=ref.location('locked')
        counts=locked_draw_counts(new);locked_draw_counts(old)
        compare_file(c,'locked_scoring_and_verdict',new/'verdict.json',old/'verdict.json')
        compare_file(c,'rank_margins',new/'margins.json',old/'margins.json')
        for directory in ('bootstrap_cache','audit_side','record_side'):
            # No parsing/recasting of persisted draw arrays: .npy bytes exact.
            compare_tree(c,'rng_and_draws' if directory=='bootstrap_cache' else 'sampled_sequences',new/directory,old/directory)
        return {'locked_draw_counts':counts}
    stage('locked',locked,[components['locked']+'/score.commit.json'])

    def paper_stage(c):
        if ledger is None or aliases is None or paper is None:
            raise FileNotFoundError('paper comparison requires --ledger, --aliases and --paper (actual manuscript definitions)')
        return compare_paper(c,read(ledger),read(aliases),ref.doc.get('paper_quantities',[]),root,components,populations,paper=paper,specifications=specifications,v25=v25)
    stage('paper',paper_stage,['verification_report.json'])
    statuses=[r['status'] for r in stages.values()]
    reproduction='NOT_COMPARABLE' if profile!='full' else 'FAIL' if 'FAIL' in statuses else 'UNRESOLVED' if any(s not in ('PASS','PASS_WITH_DECLARED_LIMITS') for s in statuses) else 'PASS'
    coverage={name:coverage_summary(result) for name,result in stages.items()}
    wording=reproduction_wording(reproduction,coverage)
    dependencies=paper_counterpart_dependencies(stages,ledger,aliases,paper,ref.doc.get('paper_quantities',[]))
    report={'schema':'born_full_reproduction_comparison_v1','profile':profile,'run':str(root),'archive':str(ref.file),
            'v25_output':str(Path(v25).resolve()) if v25 is not None else None,
            'protocol_executed_successfully':execution,'reported_results_reproduced':{'verdict':reproduction,'stages':stages},
            'reproduction_verdict_wording':wording,'comparison_coverage':coverage,
            'paper_dependencies_on_uncomparable_items':dependencies,
            'criteria':'fixed P8: exact cohorts/decisions/rationals/source bytes/draws; computed float absolute+relative 1e-12 and unchanged manuscript displays',
            'wall_seconds':time.monotonic()-start,'cpu_seconds':time.process_time()-cpu,
            'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'output':str(dest)}
    (dest/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    with (dest/'stages.csv').open('w') as f:
        w=csv.writer(f);w.writerow(['stage','status','compared','exact','accepted','failed','max_absolute_difference','reason',
                                   'no_archived_counterpart','unresolved_quantitative_diagnostics','unresolved_reference_fields','missing_generated_outputs','new_results_no_archived_counterpart','new_results_historical_matches','coverage_wording'])
        for name,result in stages.items():
            groups=list(result.get('field_groups',{}).values())
            w.writerow([name,result['status'],*[sum(g.get(k,0) for g in groups) for k in ('compared','exact','accepted','failed')],
                        max((float(g.get('maximum_absolute_difference',0)) for g in groups),default=0),result.get('reason',''),
                        *[coverage[name][k] for k in ('no_archived_counterpart','unresolved_quantitative_diagnostics','unresolved_reference_fields','missing_generated_outputs','new_results_no_archived_counterpart','new_results_historical_matches','wording')]])
    with (dest/'fields.csv').open('w') as f:
        w=csv.writer(f);w.writerow(['stage','field_group','compared','exact','accepted','failed',
            'floats','floats_binary64_exact','maximum_absolute_difference','minimum_signed_difference',
            'maximum_signed_difference','process_differences'])
        for name,result in stages.items():
            for group,counts in result.get('field_groups',{}).items():
                w.writerow([name,group,*[counts.get(k,0) for k in ('compared','exact','accepted','failed',
                    'floats','floats_binary64_exact','maximum_absolute_difference','minimum_signed_difference',
                    'maximum_signed_difference','process_differences')]])
    text=['# P8 comparison','',f"Protocol executed successfully: **{execution['verdict']}**.",
          f'Reported results reproduced: **{reproduction}**. {wording}','',
          '| Stage | Result | Compared | Exact | Accepted | Failed | Max absolute difference |',
          '|---|---|---:|---:|---:|---:|---:|']
    with (dest/'stages.csv').open() as f:
        for row in csv.DictReader(f):text.append('| '+' | '.join(row[k] for k in ('stage','status','compared','exact','accepted','failed','max_absolute_difference'))+' |')
    text+=['','Every nonexact scientific scalar and projected process difference is in the stage JSONL files. Missing evidence and unavailable archive references are explicitly UNRESOLVED. No inference, fitting or acquisition was run by this command.']
    for name,result in stages.items():
        text+=['',name+': '+coverage[name]['wording']]
        if result.get('new_results_without_archived_counterpart'):
            if name=='census':
                scope=str(result['new_contexts'])+' census cases; historical projection: '+str(result['historical_contexts_compared'])+' of '+str(result['historical_required_contexts'])+' cases in archive order'
            else:
                scope=str(len(result['new_results_without_archived_counterpart']))+' attachment records; historical comparison: '+str(result['historical_records_compared'])+' of '+str(result['archived_records'])+' records by unit identity and view'
            text.append('- New results: '+scope+'. No archived counterparts; zero historical matches. Independent validation: '+('PASS' if result['new_case_validation_agreement'] else 'FAIL')+'.')
        for row in result.get('unavailable_stored_reference_files',[]):
            text.append('- No archived counterpart: '+row['unit_id']+'/'+row['file']+'. '+row['paper_value_dependency']['reason'])
        for row in result.get('historical_outputs_without_archived_counterpart',[]):
            text.append('- Independently validated without an archived counterpart: '+row['unit_id']+'/'+row['file']+'. Historical matches: 0. '+row['scope'])
        for row in result.get('unresolved_quantitative_diagnostics',[]):text.append('- Unresolved diagnostic: '+row['field'])
        for row in result.get('unresolved_reference_fields',[]):text.append('- Unresolved retained qualification/diagnostic: '+row['field'])
        for row in result.get('historical_documentary_fields',[]):text.append('- Documentary only: '+row['field'])
        for row in result.get('worked_qualifications',[]):
            text.append('- Worked qualification '+str(row['row'])+': '+row['field']+' — '+row['disposition']+'. Historical matches: 0.')
        if 'generated_H_boundary' in result:text.append('- Generated-H mathematical boundary: '+result['generated_H_boundary'])
    text+=['','Paper dependencies on absent archived endpoint files: '+dependencies['wording']]
    (dest/'report.md').write_text('\n'.join(text)+'\n')
    return {'protocol_executed_successfully':execution['verdict'],'reported_results_reproduced':reproduction,
            'report':str(dest/'report.json'),'table':str(dest/'stages.csv')}


def coverage_summary(result):
    groups=list(result.get('field_groups',{}).values())
    missing=len(result.get('missing_generated_outputs',[]))
    unpaired=len(result.get('unavailable_stored_reference_files',[]))
    validated_unpaired=result.get('historical_outputs_without_archived_counterpart',[])
    unpaired_failed=sum(not r['independent_validation']['overall_agreement'] for r in validated_unpaired)
    diagnostics=len(result.get('unresolved_quantitative_diagnostics',[]))
    reference_fields=len(result.get('unresolved_reference_fields',[]))
    failed=sum(g.get('failed',0) for g in groups)
    new_failed=sum(not r['independent_validation']['overall_agreement'] for r in result.get('new_results_without_archived_counterpart',[]))
    audit_failed=sum(not r['independent_validation']['overall_agreement'] for r in result.get('all_record_independent_validations',[]))
    summary_failed=result.get('summary_independent_validation',{}).get('overall_agreement') is False
    wording=('Scientific differences found.' if failed else
             'Independent validation of historical-case outputs without archived counterparts failed.' if unpaired_failed else
             'Independent validation of new results failed; historical comparison is reported separately.' if new_failed else
             'Independent validation of retained attachment records or population summaries failed.' if audit_failed or summary_failed else
             'Missing regenerated outputs; comparison incomplete.' if missing else
             'All compared scientific values satisfy the fixed criteria; historical reproduction not established for the separately listed items without archived counterparts.' if unpaired else
             'All compared scientific values satisfy the fixed criteria; separately listed quantitative diagnostics remain unresolved.' if diagnostics else
             'All compared scientific values satisfy the fixed criteria; separately listed retained qualifications/diagnostics have no literal regenerated counterpart.' if reference_fields else
             'Comparison incomplete: '+result.get('reason','unavailable paper quantities') if result.get('status')=='UNRESOLVED' else
             'Reduced profile: not comparable.' if result.get('status')=='NOT_COMPARABLE' else
             'All compared scientific values satisfy the fixed criteria.')
    if validated_unpaired:
        wording+=' '+str(len(validated_unpaired))+' historical-case outputs without archived counterparts were independently checked, with zero historical matches.'
    if result.get('new_results_without_archived_counterpart'):
        wording+=' Additional results are independently validated and have zero historical matches.'
    if 'added_declarations' in result:
        wording+=' '+str(result['historical_declarations'])+' historical declarations retain their source statements and transitive axiom sets; '+str(result['added_declarations'])+' added declarations are independently validated with zero historical matches.'
    if result.get('resolved_with_declared_limits'):
        wording+=' Worked scientific qualifications are semantically checked; retained method/boundary declarations have named dispositions and zero historical matches. Generated-H boundary: '+result['generated_H_boundary']+'.'
    exact=sum(g.get('exact',0) for g in groups)
    accepted=sum(g.get('accepted',g.get('exact',0)) for g in groups)
    return {'matched':exact,'differed':sum(g.get('compared',0)-g.get('exact',0) for g in groups),
            'satisfy_criteria':accepted,'accepted_nonexact':accepted-exact,'outside_criteria':failed,
            'no_archived_counterpart':unpaired,'unresolved_quantitative_diagnostics':diagnostics,
            'independently_validated_historical_outputs_without_counterpart':len(validated_unpaired),
            'independent_historical_output_validation_failed':unpaired_failed,
            'unresolved_reference_fields':reference_fields,
            'new_results_no_archived_counterpart':result.get('added_declarations',len(result.get('new_results_without_archived_counterpart',[]))),
            'new_results_historical_matches':0,'new_results_validation_failed':new_failed,
            'independent_attachment_records_failed':audit_failed,'independent_summary_validation_failed':summary_failed,
            'worked_validation_coverage':result.get('worked_validation_coverage'),
            'missing_generated_outputs':missing,'wording':wording}


def reproduction_wording(verdict,coverage):
    if verdict=='PASS':
        if any(r.get('worked_validation_coverage') for r in coverage.values()):
            return 'Reported results reproduced under the fixed criteria, with the listed worked method and mathematical boundary qualifications; those qualifications are not literal historical matches.'
        return 'Reported results reproduced under the fixed criteria.'
    if verdict=='FAIL':return 'Reported results not reproduced: scientific differences or invalid comparison products are listed by stage.'
    if verdict=='NOT_COMPARABLE':return 'Reduced profile: not comparable with the registered archive.'
    if any(r['missing_generated_outputs'] for r in coverage.values()):
        return 'Comparison incomplete: regenerated outputs are missing. Completed comparisons and absent archived counterparts are reported separately.'
    return 'All completed comparisons without differences satisfy the fixed criteria; complete reported-result reproduction remains unresolved for the separately listed unavailable evidence. No item without a counterpart is counted as matched.'


def paper_counterpart_dependencies(stages,ledger,aliases,paper,bindings):
    gaps=[row for result in stages.values()
          for field in ('unavailable_stored_reference_files','historical_outputs_without_archived_counterpart')
          for row in result.get(field,[])]
    if not gaps:return {'status':'NO_IDENTIFIED_REFERENCE_GAPS','items':[],
                        'wording':'No absent archived endpoint file was identified in the completed stages; this does not certify unfinished stages.'}
    if ledger is None or aliases is None:return {'status':'UNRESOLVED','items':gaps,
        'wording':'Ledger/aliases missing; paper-value dependencies on absent references cannot be established.'}
    entries={e['id']:e for e in read(ledger)['entries']};names={a['macro']:a for a in read(aliases)}
    if paper is not None:
        used,_=manuscript_macros(paper,names);names={k:v for k,v in names.items() if k in used}
    by={r['macro']:r for r in bindings};items=[]
    for gap in gaps:
        name=gap['file'];dependent=[]
        for macro,a in names.items():
            if name in entries[a['id']].get('source','') or name in json.dumps(by.get(macro,{})):
                dependent.append(macro)
        items.append({**gap,'direct_paper_value_dependencies':dependent,
            'dependency_status':'DIRECT_REPORTED_VALUE_DEPENDENCY' if dependent else 'NO_DIRECT_LEDGER_ENDPOINT_DEPENDENCY',
            'indirect_scope':'Generated root controls support instrument-validity premises and are independently checked; historical interval-endpoint equality is not established.'})
    return {'status':'DIRECT_DEPENDENCY' if any(r['direct_paper_value_dependencies'] for r in items) else 'NO_DIRECT_ENDPOINT_VALUE_DEPENDENCY',
            'items':items,'wording':'Direct manuscript value dependencies are listed per file. '+
                ('At least one reported value uses an uncomparable endpoint file.' if any(r['direct_paper_value_dependencies'] for r in items) else
                 'No selected ledger source or explicit binding uses an absent endpoint file. Generated root controls still support instrument-validity premises; their historical endpoint equality is unclaimed.')}


def pointer(doc,path):
    for key in path.strip('/').split('/'):
        key=key.replace('~1','/').replace('~0','~')
        doc=doc[int(key)] if isinstance(doc,list) else doc[key]
    return doc


def manuscript_macros(path, aliases):
    """Read literal result definitions, including nested TeX braces.

    Do not execute TeX. Result aliases must have exactly one zero-argument
    newcommand definition; an override or unparseable definition is a failure.
    """
    text=Path(path).read_text()
    begin='% >>> BEGIN GENERATED RESULT MACROS';end='% <<< END GENERATED RESULT MACROS'
    if text.count(begin)!=1 or text.count(end)!=1 or text.index(begin)>text.index(end):
        raise ValueError('manuscript needs one ordered result-macro marker pair')
    outside=re.sub(re.escape(begin)+r'.*?'+re.escape(end),'',text,flags=re.S)
    outside=re.sub(r'(?<!\\)%[^\n]*','',outside)
    used=set(re.findall(r'\\([A-Za-z]+)',outside)) & set(aliases)
    clean=re.sub(r'(?<!\\)%[^\n]*','',text)
    def argument(at):
        while at<len(clean) and clean[at].isspace():at+=1
        if at==len(clean) or clean[at]!='{':raise ValueError('unparseable result macro definition')
        start=at+1;depth=1;at+=1
        while at<len(clean):
            if clean[at]=='\\':at+=2;continue
            if clean[at]=='{':depth+=1
            elif clean[at]=='}':
                depth-=1
                if not depth:return clean[start:at],at+1
            at+=1
        raise ValueError('unbalanced result macro definition')
    definitions={}
    if re.search(r'\\csname',clean):
        raise ValueError('unsupported indirect TeX definitions (csname); manuscript display cannot be determined statically')
    # Other definition/patch APIs are valid TeX but not literal zero-argument
    # result definitions. Refuse them explicitly rather than using stale values.
    unsupported=r'\\(?:NewDocumentCommand|RenewDocumentCommand|ProvideDocumentCommand|DeclareDocumentCommand|NewExpandableDocumentCommand|RenewExpandableDocumentCommand|ProvideExpandableDocumentCommand|DeclareExpandableDocumentCommand|newrobustcmd|renewrobustcmd|providerobustcmd|appto|preto|apptocmd|pretocmd|patchcmd|DeclareMathOperator)\*?\s*(?:\{\s*\\([A-Za-z]+)\s*\}|\\([A-Za-z]+))'
    for match in re.finditer(unsupported,clean):
        if (match[1] or match[2]) in used:
            raise ValueError('unsupported result macro definition or patch: '+(match[1] or match[2]))
    for match in re.finditer(r'\\(?:def|gdef|edef|xdef|let|chardef|mathchardef|countdef|dimendef|skipdef|muskipdef|toksdef|font)\s*\\([A-Za-z]+)',clean):
        if match[1] in used:raise ValueError('overridden result macro: '+match[1])
    for match in re.finditer(r'\\(?:newcommand|renewcommand|providecommand|DeclareRobustCommand)\*?\s*(?:\{\s*\\([A-Za-z]+)\s*\}|\\([A-Za-z]+))',clean):
        name=match[1] or match[2]
        if name not in used:continue
        if name in definitions:raise ValueError('duplicate or overridden result macro: '+name)
        body,_=argument(match.end())
        if body.startswith(r'\ensuremath{') and body.endswith('}'):
            body=body[len(r'\ensuremath{'):-1]
        definitions[name]=body
    for name in used:
        if name not in definitions:raise ValueError('missing literal manuscript result definition: '+name)
    return used,definitions


def extract_paper_quantity(row,name,root,components,populations,views,evidence,*,specifications='specifications',v25=None):
    """Shared run-derived value and evidence; no expected value is an input."""
    regenerated={'aggregation':row.get('expression') or row.get('operation') or 'JSON-pointer extraction',
                 'selector':{k:row[k] for k in ('pointer','expression','operation','map','stat','model','negate') if k in row}}
    if row.get('view')=='census':
        if 'census' not in views:views['census']=census_paper_view(root/components['census'],worked=root/components['worked'] if 'worked' in components else None,specifications=specifications)
        doc=views['census'][row['file']]
        evidence['census']=views['census']['provenance']
        regenerated.update(evidence_catalog='census',sources=evidence['census']['sources'],
            context_record_files=evidence['census']['context_record_files'],
            aggregation=evidence['census']['aggregation']+'; '+row['file']+row.get('pointer',row.get('expression','')))
        if name=='SelectedCaseIndex':
            regenerated['sources']=regenerated['sources']+[evidence['census']['selected_identity_source']]
            regenerated['aggregation']='unique six-field identity join of selected worked context to ordered full-census inventory'
        if name=='RegisteredRobustGapBound':
            regenerated['sources']=[evidence['census']['specification']]
            regenerated['aggregation']='exact registered bound parsed from census maximal_gap_witness definition'
    elif row.get('view')=='census_attachments':
        from .paper_census import attachment_quantities
        if 'census_attachments' not in views:views['census_attachments']=attachment_quantities(root/components['attachments'])
        doc=views['census_attachments']
        if 'model' in row:
            candidates=[r for r in doc['records'] if r['view']==row['map'] and r['metric']=='dtv_loss' and r['model_or_recorded_contrast']==row['model']]
            if len(candidates)!=1:raise ValueError('no unique scientific attachment summary selector')
            doc={'value':candidates[0]['quantiles']['exact'][row['stat']]};row={**row,'pointer':'/value'}
        evidence['census_attachments']=views['census_attachments']['provenance']
        regenerated.update(evidence_catalog='census_attachments',**evidence['census_attachments'])
    elif row.get('view')=='canonical_census':
        from .v25_paper import canonical_population
        if 'canonical_census' not in views:views['canonical_census']=canonical_population(Path(root),components,specifications)
        doc={'value':views['canonical_census']['summaries'][row['map']]['exact'][row['stat']]}
        row={**row,'pointer':'/value'}
        evidence['canonical_census']=views['canonical_census']['provenance']
        regenerated.update(evidence_catalog='canonical_census',sources=[str(root/components['census']/'complete.json'),str(root/components['attachments']/'complete.json')],aggregation=evidence['canonical_census']['aggregation'])
    elif row.get('view')=='worked':
        if 'worked' not in views:views['worked']=worked_paper_view(root/components['worked'])
        doc=views['worked']
        regenerated['sources']=[str(root/components['worked']/x) for x in ('original/certificates.json','selected/certificates.json','selected/CONTEXT.json')]
    elif row.get('view')=='lean_audit':
        doc=populations['lean_audit'];regenerated['sources']=[str(root/components.get('lean','lean')/'audit_receipt.json')]
    elif row.get('view') in ('v25','v25_selected'):
        if v25 is None:raise FileNotFoundError('supply --v25-output from a completed registered reproduce v25 run')
        from .v25_paper import population_view,selected_canonical
        if row['view']=='v25_selected':
            if 'v25_selected' not in views:views['v25_selected']=selected_canonical(Path(root),components,specifications)
            doc=views['v25_selected']
            regenerated.update(sources=[str(root/components['worked']/'selected/CONTEXT.json'),str(root/components['census']/'complete.json'),str(root/components['attachments']/'complete.json')],aggregation='identity join to the retained selected fixture; public v25 canonical.construct; binary64 NumPy M @ q; math.fsum TV minus recorded q_full TV')
        else:
            key='v25_'+row['evaluation']
            if key not in views:views[key]=population_view(Path(v25),row['evaluation'],specifications=specifications)
            doc=views[key]
            provenance=doc.get('provenance',{'sources':[str(Path(v25)/row['evaluation']/'evaluation/complete.json')],
                'aggregation':'registered committed population view; selector above'})
            regenerated.update(sources=provenance['sources'],aggregation=provenance['aggregation'])
    elif row.get('view')=='public_registry':
        from born_ladder.__main__ import REGISTRY
        doc={'commands':len(REGISTRY)}
        regenerated['sources']=['born_ladder.__main__.REGISTRY']
    elif row.get('public_spec'):
        from .specification import PublicSpecification
        spec=PublicSpecification(Path(specifications),row['public_spec'])
        regenerated['sources']=[str(Path(specifications)/'predictive.json'),str(Path(specifications)/'born_route_rebuild1_spec_v24.json')]
        if 'selection' in row:
            selection=row['selection'];doc=spec.get(selection['pointer'])
            if 'id' in selection:
                found=[item for item in doc if item['id']==selection['id']]
                if len(found)!=1:raise ValueError('no unique public specification setting')
                doc=pointer(found[0],selection['value_pointer'])
            row={**row,'operation':selection.get('operation','identity')}
            text=None
        else:text=row['expression'].split('#',1)[1].split(' [',1)[0]
        if text is None:pass
        elif 'items[id=' in text:
            parent,rest=text.split('/items[id=',1);identifier,tail=rest.split(']',1)
            doc=next(r for r in spec.get(parent+'/items') if r['id']==identifier)
            row={**row,'expression':'#'+tail};
        else:doc=spec.get(text);row={**row,'operation':'identity_count' if '[SeedCount]' in row['expression'] else 'identity','expression':None}
    elif row.get('evaluation'):
        doc=populations[row['evaluation']]
        component=row['evaluation'].replace('-','_')+'_evaluation'
        if component in components:
            evaluation=root/components[component]
            regenerated['sources']=[str(last_attempt(evaluation)/'evaluation.json')]
        else:regenerated['sources']=['caller-supplied population view: '+row['evaluation']]
    else:
        directory=root/components[row['component']]
        if row['file'].startswith('@attempt/'):
            actual=last_attempt(directory)/row['file'].removeprefix('@attempt/')
        else:actual=directory/row['file']
        doc=read(actual);regenerated['sources']=[str(actual)]
    if 'aggregate' in row:
        aggregate=row['aggregate'];op=aggregate['operation']
        selected=pointer(doc,aggregate['pointer']) if aggregate.get('pointer') else doc
        if op=='length':value=len(selected)
        elif op=='object_key':
            if aggregate['key'] not in selected:raise ValueError('missing registered object key')
            value=int(aggregate['key'])
        else:raise ValueError('unsupported explicit paper aggregation: '+op)
    elif row.get('operation')=='identity':value=doc
    elif row.get('operation')=='identity_count':value=len(doc)
    elif row.get('expression'):value=expression(doc,row['expression'])
    elif row.get('operation')=='minimum_competitor_lower':
        stats=doc['statistics'];value=min(v['bca_simultaneous_lower'] for k,v in stats.items() if 'S2' not in k)
    else:value=pointer(doc,row['pointer'])
    if row.get('decode_json_string') and isinstance(value,str):value=json.loads(value)
    if isinstance(value,dict) and set(value)=={'numerator','denominator'}:
        from fractions import Fraction
        value=str(Fraction(value['numerator'],value['denominator']))
    if row.get('negate'):value=-value
    return value,regenerated


def compare_paper(c,ledger,aliases,bindings,root,components,populations,*,paper=None,specifications='specifications',v25=None):
    """No number may silently disappear because its extractor is unavailable."""
    entries={e['id']:e for e in ledger['entries']};names={a['macro']:a for a in aliases};by={r['macro']:r for r in bindings}
    if len(by)!=len(bindings):raise ValueError('duplicate paper macro binding')
    unavailable=[];compared=[];documentary=[];views={};definitions=None;checks=[];evidence={}
    if paper is not None:
        used,definitions=manuscript_macros(paper,names)
        names={k:v for k,v in names.items() if k in used}
    for name,a in names.items():
        e=entries[a['id']]
        direction=a.get('direction') or e.get('rounding_direction') or ('lower' if 'outward lower' in e.get('rounding_rule','') else 'upper' if 'outward upper' in e.get('rounding_rule','') else None)
        if definitions is not None:
            c.compare('manuscript_defined_display_vs_ledger',definitions[name],render(e['value'],a['format'],direction),name)
        if name not in by:
            automatic=automatic_paper_binding(e,name)
            if automatic is not None:by[name]=automatic
        # Formal/toolchain/source-setting/history-only facts have no regenerated
        # scientific estimator; their literal public inputs are checked elsewhere.
        relevant=name in by or e['evidence_type'] in ('hash_bound_attachment','recomputed_by_public_command','descriptive_recomputation','ledger_aggregation_of_publicly_recomputed_per_case_values','count_of_artifacts','independently_rederived_earlier','audit_metadata','full_cohort_external_exact_check')
        if not relevant:
            documentary.append({'macro':name,'evidence_type':e['evidence_type'],'source':e['source'],'disposition':'formal/source-setting or historical documentary fact; not a regenerated population estimator'})
            continue
        if name not in by:
            unavailable.append({'macro':name,'ledger_id':a['id'],'reason':'no declared regenerated field extractor; may be historical-only or v25 outside this historical profile'});continue
        row=by[name]
        try:
            value,regenerated=extract_paper_quantity(row,name,root,components,populations,views,evidence,specifications=specifications,v25=v25)
            expected=e['value']
            if type(value) is float:
                from fractions import Fraction
                expected=float(Fraction(str(expected)))
            elif type(value) is int and isinstance(expected,str):
                from fractions import Fraction
                f=Fraction(expected)
                expected=f.numerator if f.denominator==1 else expected
            elif isinstance(value,str) and isinstance(expected,str) and ('/' in value or '/' in expected):
                # Ledger p/q and certificate canonical rational spellings
                # may differ (e.g. -1/1 versus -1). Compare exact mathematical
                # values; retain the representation difference separately.
                from fractions import Fraction
                if value!=expected:
                    c.record('paper_rational_spelling',name,value,expected,'canonical exact-rational representation for ledger comparison only',True)
                value,expected=str(Fraction(value)),str(Fraction(expected))
            c.compare('paper_full_precision',value,expected,name)
            c.compare('manuscript_display',render(value,a['format'],direction),render(e['value'],a['format'],direction),name)
            if definitions is not None:
                c.compare('manuscript_defined_display_vs_regenerated',definitions[name],render(value,a['format'],direction),name)
            compared.append(name)
            import struct
            exact=type(value) is type(expected) and (struct.pack('!d',value)==struct.pack('!d',expected) if type(value) is float else value==expected)
            checks.append({'macro':name,'ledger_id':a['id'],'ledger_source':e.get('source'),
                           'regenerated_source':regenerated,'regenerated_value':value,'ledger_value':e['value'],
                           'full_precision_exact':exact,'display_exact':render(value,a['format'],direction)==render(e['value'],a['format'],direction),
                           'manuscript_definition_exact':definitions[name]==render(value,a['format'],direction) if definitions is not None else None})
        except (KeyError,FileNotFoundError,ValueError) as exc:unavailable.append({'macro':name,'reason':str(exc)})
    result=c.result();result['unavailable_paper_quantities']=unavailable;result['paper_macros_compared']=compared;result['documentary_or_formal_macros']=documentary
    result['paper_quantity_checks']=checks;result['paper_regenerated_evidence']=evidence
    if unavailable:
        c.record('unavailable_paper_quantities','',unavailable,None,'UNRESOLVED: no verified extractor; not a match',False)
        result['overall_agreement']=False
    result['status']='FAIL' if any(g['failed'] for g in result['field_groups'].values()) else 'UNRESOLVED' if unavailable else 'PASS' if result['overall_agreement'] else 'UNRESOLVED'
    return result


def automatic_paper_binding(entry,name):
    """Unambiguous stored JSON-pointer bindings; no guessed numerical values."""
    source=entry.get('source','');path=source.split('#',1)[0]
    from .paper_census import binding as census_binding
    census=census_binding(entry,name)
    if census is not None:return census
    if entry.get('id')=='PublicVerificationCommands':return {'macro':name,'view':'public_registry','pointer':'/commands'}
    if entry.get('id')=='LeanDeclarationsAudited':return {'macro':name,'view':'lean_audit','pointer':'/declarations'}
    from .v25_paper import binding
    corrective=binding(entry,name)
    if corrective is not None:return corrective
    if 'A2_AXIOM_AUDIT.json' in path:
        return {'macro':name,'view':'lean_audit','expression':source}
    if name in ('CarrierSize','LabelMaps','AtomicEffects') or re.match(r'(NoLift(?:First|Second|Third|Fourth)Gap|Ensemble(?:Left|Right|Gap)|Order(?:Forward|Reverse|Gap))',name):
        return {'macro':name,'view':'worked','pointer':'/'+name}
    match=re.search(r'#(/[^;\n]*?)(?: \[|;|$)',source)
    ptr=match.group(1).strip() if match else None
    if 'g2a_evaluation' in path:
        if 'minimum competitor simultaneous lower' in source:
            return {'macro':name,'evaluation':'competitor','operation':'minimum_competitor_lower'}
        if ptr:return {'macro':name,'evaluation':'competitor','pointer':ptr,'negate':'negation' in source}
    if 'g2c_v23_evaluation' in path and ptr:
        return {'macro':name,'evaluation':'cross-term','pointer':ptr}
    if '/p6/verdict.json' in path and ptr:
        return {'macro':name,'component':'locked','file':'verdict.json','expression':source}
    if 'CENSUS/INVENTORY.json' in path:
        return {'macro':name,'view':'census','file':'INVENTORY.json','expression':source}
    if path.endswith('A3_ROBUST_CENSUS_CERTIFICATE.json'):
        return {'macro':name,'view':'census','file':'robust','expression':source}
    if path.endswith('SELECTION_PROPOSAL.json') and ptr=='/picked_provenance_key/scale':
        return {'macro':name,'component':'worked','file':'selected/CONTEXT.json','pointer':'/born/scale'}
    if path.endswith('selected_raw_performance_verbatim.json') and ptr=='/verbatim_JSON_value_strings/total_count':
        return {'macro':name,'component':'attachments','file':'@attempt/attachments.json','pointer':'/0/fields/total_count','decode_json_string':True}
    if '/CENSUS/structural_results.json' in path or '/CENSUS/structural_completion_results.json' in path:
        return {'macro':name,'view':'census','file':path.rsplit('/',1)[1],'expression':source}
    if '/CB2/RETURN_CARRIER_INVENTORY.json' in path and ptr:
        return {'macro':name,'view':'census','file':'inventory','pointer':ptr.replace('/paired_unit_contexts','/paired_contexts')}
    if path.endswith('non_trace_rederivation.json') and ptr:
        return {'macro':name,'component':'worked','file':'original/certificates.json','pointer':'/finite_family/non_density'+ptr}
    if 'E2/C_certificate.json' in path and ptr:
        return {'macro':name,'component':'worked','file':'original/certificates.json','pointer':'/finite_events'+ptr}
    if 'born_route_rebuild1_spec_v24.json' in path and '#' in source:
        return {'macro':name,'public_spec':'v24','expression':source}
    if '/CENSUS/descriptive_summaries.json' in path and ptr:
        # The directory is resolved by the caller from its completed attachment
        # seal, not by following the historical absolute path.
        return {'macro':name,'component':'attachments','file':'@attempt/descriptive_summaries.json','pointer':ptr}
    return None


def expression(doc,source):
    """Ledger field/aggregation notation; no inferred or hard-coded results."""
    from fractions import Fraction
    suffix=source.split('#',1)[1].split(';',1)[0].strip()
    if suffix.startswith('length'):return len(doc)
    if suffix.startswith('/'):
        path=suffix.split(' [',1)[0].strip();value=pointer(doc,path)
        if '[length]' in suffix or '[SeedCount]' in suffix:return len(value)
        if '[object key]' in suffix:return int(path.rsplit('/',1)[1])
        return value
    m=re.match(r'count\((.*)\)',suffix)
    if m:
        conditions=[]
        for part in m.group(1).split(','):
            item=re.fullmatch(r'([^!=>]+)(!=|=|>)(.+)',part.strip())
            if not item:raise ValueError('invalid ledger count predicate')
            field,op,target=item.groups();conditions.append((field.replace('.','/'),op,target))
        def yes(row):
            for field,op,target in conditions:
                value=pointer(row,field)
                if op=='>':
                    if Fraction(str(value))<=Fraction(target):return False
                elif (str(value)==target)!=(op=='='):return False
            return True
        return sum(yes(r) for r in doc)
    m=re.match(r'(min|max|median)\(\*\s+(/[^\[)]*)',suffix)
    if m:
        operation,path=m.groups();values=[Fraction(str(pointer(r,path.strip()))) for r in doc]
        if 'absolute value' in suffix:values=list(map(abs,values))
        values.sort();v=values[0] if operation=='min' else values[-1] if operation=='max' else (values[(len(values)-1)//2]+values[len(values)//2])/2
        return str(v)
    m=re.match(r'sum\(([^)]+)\)',suffix)
    if m:return sum(pointer(r,m.group(1)) for r in doc)
    raise ValueError('unsupported ledger expression: '+suffix)


def census_paper_view(root, *, worked=None, specifications='specifications'):
    """Recompute scalar census results from this run's committed records."""
    from .paper_census import census_quantities
    return census_quantities(root,worked=worked,specifications=specifications)


def worked_paper_view(root):
    """Exact algebra of already certified endpoints; no predictive statistics."""
    from fractions import Fraction as Q
    original=read(root/'original/certificates.json');selected=read(root/'selected/certificates.json')
    context=read(root/'selected/CONTEXT.json')
    result={'CarrierSize':len(selected['six_state']['G']),'LabelMaps':len(context['lens']),
            'AtomicEffects':sum(len(v) for v in original['finite_family']['atomic_effects'].values())}
    for name,rows in zip(('First','Second','Third','Fourth'),original['lean_certificates']['B04'][-1],strict=True):
        result['NoLift'+name+'Gap']=str(max(Q(rows[1]['L'])-Q(rows[0]['U']),Q(rows[0]['L'])-Q(rows[1]['U'])))
    probabilities={}
    for side,rows in zip(('Left','Right'),original['lean_certificates']['B05'][-1],strict=True):
        for component,row in zip(('First','Second'),rows,strict=True):
            result['Ensemble'+side+'Weight'+component]=row['weight']
            result['Ensemble'+side+'Ray'+component]=row['ray']
        for suffix,field in (('Lower','Plo'),('Upper','Phi')):
            value=sum(Q(row['weight'])*Q(row['mass'])*Q(row[field]) for row in rows)
            probabilities[side,suffix]=value;result['Ensemble'+side+suffix]=str(value)
    for suffix,left,right in (('Lower','Lower','Upper'),('Upper','Upper','Lower')):
        result['EnsembleGap'+suffix]=str(probabilities['Right',left]-probabilities['Left',right])
    order=original['lean_certificates']['B07']
    for side,row in zip(('Forward','Reverse'),order,strict=True):
        result['Order'+side+'Lower']=row['L'];result['Order'+side+'Upper']=row['U']
    result['OrderGapLower']=str(Q(order[1]['L'])-Q(order[0]['U']))
    result['OrderGapUpper']=str(Q(order[1]['U'])-Q(order[0]['L']))
    return result


def paper_projection(doc):
    """Release bulky saved draws only after their complete comparison."""
    if isinstance(doc,dict):return {k:paper_projection(v) for k,v in doc.items()
        if k not in ('rng_audit','replicate_estimates','replicate_membership','rotation_evidence','persistence_contract')}
    if isinstance(doc,list):return None if len(doc)>128 else [paper_projection(v) for v in doc]
    return doc
