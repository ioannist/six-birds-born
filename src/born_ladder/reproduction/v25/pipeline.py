"""Synthetic conformance and fresh-only commitment/construction pipeline."""
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import time
from .specification import Specification,canonical_bytes,digest
from .predictions import predict,commit,read_committed
from .inference import competitor,cross_term


def write_new(path,value):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:
        stream.write(canonical_bytes(value)+b'\n'); stream.flush(); os.fsync(stream.fileno())


def worker_identity(spec):
    from born_ladder.reproduction.stage_environment import check_current,profile_path
    return check_current(json.loads(profile_path(spec.directory,'predictive_v25').read_bytes()))


def artifact_bindings(directory):
    directory=Path(directory)
    return [{'path':path.relative_to(directory).as_posix(),'bytes':path.stat().st_size,
             'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in sorted(directory.rglob('*')) if path.is_file()]


def verify_artifacts(directory,bindings):
    if artifact_bindings(directory)!=bindings:
        raise ValueError('completed scientific artifacts changed')


def before_publication(spec,plan):
    after=worker_identity(spec)
    if after!=plan['runtime']:
        raise ValueError('computing versions or threads changed before publication')
    return after


def begin(spec,output,inputs):
    from born_ladder.reproduction.runs import validate_output,exclusive_output
    output=validate_output(output,Path.cwd())
    output.mkdir(parents=True,exist_ok=True)
    identity=worker_identity(spec)
    plan={'schema':'born_v25_stage_plan_v1','scientific_digest':spec.digest,'runtime':identity,
          'inputs':inputs}
    path=output/'plan.json'
    if path.exists():
        if canonical_bytes(json.loads(path.read_bytes()))!=canonical_bytes(plan):
            raise ValueError('v25 incompatible resume: specification, inputs or computing versions differ')
    else: write_new(path,plan)
    return output,plan


def scored_rows(prediction,counts,metadata):
    """Only called after a checked prediction commitment has been read."""
    restricted=prediction['restricted']; laws=prediction['predictions']; rows=[]
    coefficients=prediction['legacy']['coefficients']
    from born_ladder.snapshot.identities import kind_cell_id
    for kind in ('raw','package'):
        labels=restricted['labels'][kind]; alphabet=sorted(set(labels)); empirical=[counts[kind].count(label)/len(counts[kind]) for label in alphabet]
        mapped={law:[math.fsum(q[i] for i,label in enumerate(labels) if label==outcome) for outcome in alphabet] for law,q in laws.items()}
        losses={law:0.5*math.fsum(abs(a-b) for a,b in zip(values,empirical,strict=True)) for law,values in mapped.items()}
        brier={law:math.fsum((a-b)**2 for a,b in zip(values,empirical,strict=True)) for law,values in mapped.items()}
        contrast={'D__'+law+'_minus_q_full':value-losses['q_full'] for law,value in losses.items() if law!='q_full'}
        contrast['S2__q_full_minus_2xL_full']=losses['q_full']-2*losses['L_full']
        control={'I':'pass','A':'pass','F':'pass','C':'pass' if prediction['canonical_controls']['status']=='pass' else 'missing'}
        if control['C']!='pass': contrast['D__q_diag_canonical_minus_q_full']=None
        row={**metadata,'kind':kind,'_derived_kind':'raw' if kind=='raw' else 'pkg',
             'kind_cell_id':kind_cell_id(metadata['unit_id'],'raw' if kind=='raw' else 'pkg'),'integer_counts':[counts[kind].count(x) for x in alphabet],
             'total_count':len(counts[kind]),'dtv_loss':losses,'brier_score':brier,'pairwise_contrast':contrast,
             'controls':control,'nondegenerate':sum(abs(x)>1e-9 for x in coefficients)>=2,
             'prediction_commitment_sha256':digest(prediction),'tie_flag':{name:abs(value)<=1e-12 for name,value in contrast.items() if value is not None}}
        rows.append(row)
    return rows


def descriptive(spec,predictions,rows,evaluation,seeds,configs):
    """Whole-slot support: never drop a missing unit or change denominator."""
    from born_ladder.snapshot import g2a,g2c_evaluate as g2c
    import numpy as np
    count=spec.science['orientation_sensitivity']['random_orientation_count']; slots=[]
    contributing={r['unit_id'] for r in rows if r['eligibility'] and
                  (evaluation=='competitor' or r['nondegenerate'])}
    def evaluate(selector):
        if not contributing:
            return {'status':'unavailable','missing_units':[], 'reason':'empty required admitted cohort'}
        missing=[identity for identity in sorted(contributing)
                 if identity not in predictions or selector(predictions[identity]) is None]
        if missing:
            return {'status':'unavailable','missing_units':missing}
        vector_rows=[]; unit_contrasts=[]
        for row in rows:
            if row['unit_id'] not in contributing:
                # Non-contributing rows (e.g. planned exclusions) may carry no losses.
                vector_rows.append({**row,
                    'dtv_loss':None if row['dtv_loss'] is None else {**row['dtv_loss'],'orientation':0.0},
                    'brier_score':None if row['brier_score'] is None else {**row['brier_score'],'orientation':0.0}})
                continue
            pred=predictions[row['unit_id']]; q=selector(pred); labels=pred['restricted']['labels'][row['kind']]
            alphabet=row.get('ordered_union_outcome_labels',sorted(set(labels)))
            matrix=row.get('M_raw_or_content_hash' if row['kind']=='raw' else 'M_pkg_or_content_hash')
            if matrix is None:matrix=[[float(label==outcome) for label in labels] for outcome in alphabet]
            empirical=[x/row['total_count'] for x in row['integer_counts']]
            mapped=(np.asarray(matrix)@np.asarray(q)).tolist()
            loss=0.5*math.fsum(abs(a-b) for a,b in zip(mapped,empirical,strict=True))
            contrast=loss-row['dtv_loss']['q_full']
            unit_contrasts.append({'unit_id':row['unit_id'],'kind':row['kind'],
                                  'unzeroed_contrast':contrast,'tie':abs(contrast)<=1e-12})
            vector_rows.append({**row,'pairwise_contrast':{'D__orientation_minus_q_full':loss-row['dtv_loss']['q_full']},
                   'dtv_loss':{**row['dtv_loss'],'orientation':loss},'brier_score':{**row['brier_score'],'orientation':0.0}})
        aggregate={}
        for kind in ('raw','package'):
            if evaluation=='competitor':
                values,_,_=g2a._hierarchical_values([r for r in vector_rows if r['kind']==kind and r['eligibility']],
                             'D__orientation_minus_q_full',factor2=2.0)
                aggregate[kind]=(g2a._mean([g2a._mean([values[seed][config] for config in configs]) for seed in seeds])
                      if set(values)==set(seeds) and all(set(values[seed])==set(configs) for seed in seeds) else None)
            else:
                controls=[{'unit_id':r['unit_id'],'kind_cell_id':r['kind_cell_id'],'nondegenerate':r['nondegenerate']} for r in vector_rows]
                values=g2c._source_seed_values(vector_rows,controls,metric='dtv',seeds=seeds,diagonal_label='orientation')[0]
                vector=g2c._combined_seed_vector(values,kind='raw' if kind=='raw' else 'pkg',seeds=seeds)
                aggregate[kind]=None if vector is None else g2a._mean(vector)
        return {'status':'complete' if all(v is not None for v in aggregate.values()) else 'unavailable',
                'contrasts':aggregate,'unit_contrasts':unit_contrasts}
    for slot in range(count):
        slots.append({'slot':slot,**evaluate(lambda p,k=slot:p['orientations'][k]['q']
                      if p['orientations'][k]['status']=='complete' else None)})
    references={name:evaluate(lambda p,name=name:p['canonical_certificate'].get('q_diag_canonical')
                    if name=='canonical' else p['historical_svd_reference'].get('q')
                    if p['historical_svd_reference']['status']=='complete' else None)
                for name in ('canonical','historical_svd')}
    complete=all(row['status']=='complete' for row in slots)
    summaries={}
    if complete:
        for kind in ('raw','package'):
            values=[row['contrasts'][kind] for row in slots]
            summaries[kind]={'min':min(values),'q1':g2a._type7(values,0.25),'median':g2a._type7(values,0.5),
                             'q3':g2a._type7(values,0.75),'max':max(values),'mean':g2a._mean(values),
                             'at_or_below_zero':sum(x<=0 for x in values),
                             'at_or_below_margin':sum(x<=1/240 for x in values)}
    return {'status':'complete' if complete else 'distribution-unavailable','slots':slots,'summaries':summaries,
            'references':references,'registered_slots':count,'complete_slots':sum(s['status']=='complete' for s in slots),
            'scope':'descriptive only; no inference, orientation optimization or primary verdict dependency'}


def synthetic_payload(rank=2,n=8):
    if n not in (8,32) or not 1<=rank<=6: raise ValueError('synthetic supported shape')
    # Exact dyadic Walsh directions, emitted in a fixed order; no RNG/seeds.
    emitted=[[((-1.0 if (i & column).bit_count()%2 else 1.0)/4) for i in range(n)] for column in range(1,rank)]
    if rank==1: emitted=[[1.0/4]*n]
    p=[float((i+1)**2)/sum((j+1)**2 for j in range(n)) for i in range(n)]
    return {'identity':['SYNTHETIC','shape',1,'context',rank,0],'emitted':emitted,'preparation':p,
            'labels':{'raw':[i%2 for i in range(n)],'package':[(i//2)%2 for i in range(n)]}}


def smoke(*,output,specifications='specifications',replicates=200,evaluations=('competitor','cross-term')):
    spec=Specification(specifications); started=time.monotonic(); cpu=time.process_time()
    output,plan=begin(spec,output,{'mode':'synthetic','replicates':replicates,'evaluations':list(evaluations)})
    from born_ladder.reproduction.runs import exclusive_output
    with exclusive_output(output):
        if (output/'complete.json').exists():
            completed=json.loads((output/'complete.json').read_bytes())
            verify_artifacts(output/completed['attempt'],completed['artifacts'])
            return completed
        attempts=output/'attempts'; attempts.mkdir(exist_ok=True)
        attempt=attempts/('attempt_'+str(len(list(attempts.iterdir()))+1).zfill(4)); attempt.mkdir()
        write_new(attempt/'worker_receipt.json',{'pid':os.getpid(),'runtime':plan['runtime'],
                    'diagnostic_cpu_features':__import__('numpy')._core._multiarray_umath.__cpu_features__,
                    'checked_in_actual_computing_process':True})
        seeds=list(range(101,121)); configs=['synthetic-a','synthetic-b']; reports={}; prediction_cost=[]
        reserved={x for name in ('competitor','cross-term') for x in spec.grid(name)['seeds']}
        if reserved.intersection(seeds): raise ValueError('synthetic seeds collide with acquisition blocks')
        for evaluation in evaluations:
            predictions={}; rows=[]
            for seed in seeds:
                for group_index,config in enumerate(configs):
                    payload=synthetic_payload(2+group_index,8)
                    identity=['EXP-112' if group_index==0 or evaluation=='competitor' else 'EXP-105',config,seed,'synthetic-context',2+group_index,0]
                    payload['identity']=identity
                    # Synthetic preparations vary before commitment, never tuned by loss.
                    weights=[float((i+1+(seed%5))**2) for i in range(8)]; total=math.fsum(weights)
                    payload['preparation']=[x/total for x in weights]
                    unit_id=digest(identity); directory=attempt/evaluation/'predictions'/unit_id
                    tick=time.monotonic(); prediction=predict(spec,evaluation,payload,runtime_sha256=digest(plan['runtime'])); commit(directory,prediction)
                    prediction_cost.append(time.monotonic()-tick)
                    committed,seal=read_committed(directory); predictions[unit_id]=committed
                    # Sample endpoint labels are generated/accessed only after sealing.
                    states=[(i+seed)%8 for i in range(24)]
                    counts={kind:[payload['labels'][kind][i] for i in states] for kind in ('raw','package')}
                    write_new(directory/'synthetic_samples.json',{'endpoints':states,'commitment':seal})
                    metadata={'unit_id':unit_id,'seed':seed,'config_or_null':config,'invocation_id':digest(identity[:3]),
                       'context':'synthetic-context','partition':'synthetic-partition','resolution':identity[4],'step':0,
                       'source_key':'EXP-112' if group_index==0 or evaluation=='competitor' else 'G2x',
                       'fixed_census_config_or_experiment_key':config,'eligibility':True,'exclusion_reason_code':None}
                    rows.extend(scored_rows(committed,counts,metadata))
            write_new(attempt/evaluation/'units.json',rows)
            controls=[{'unit_id':r['unit_id'],'kind_cell_id':r['kind_cell_id'],'nondegenerate':r['nondegenerate']} for r in rows]
            result=(competitor(spec,rows,seeds=seeds,configs=configs,replicates=replicates) if evaluation=='competitor' else
                    cross_term(spec,rows,controls,seeds=seeds,replicates=replicates))
            result['mode']='synthetic-full-contract' if replicates is None else 'synthetic-reduced'
            result['acquisition_scope']='synthetic only; no registered seed or retained scored input'
            write_new(attempt/evaluation/'population.json',result)
            description=descriptive(spec,predictions,rows,evaluation,seeds,configs)
            write_new(attempt/evaluation/'orientation_description.json',description)
            reports[evaluation]={'joint':result['joint'],'family':result['family'],'description':description['status']}
        after=before_publication(spec,plan)
        complete={'status':'synthetic-complete','scientific_digest':spec.digest,'reports':reports,
                  'attempt':attempt.relative_to(output).as_posix(),'wall_seconds':time.monotonic()-started,
                  'cpu_seconds':time.process_time()-cpu,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                  'prediction_commit_seconds':prediction_cost,'runtime_sha256':digest(after),
                  'artifacts':artifact_bindings(attempt)}
        write_new(output/'complete.json',complete)
        return complete
