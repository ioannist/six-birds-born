"""Worked-case certificates from public run captures, without archived conclusions."""
from fractions import Fraction as Q
from pathlib import Path
import itertools
import json
import resource
import time

from born_ladder import arithmetic as A
from born_ladder.claim_checks import non_trace_fragment, parent_certificate
from born_ladder.instruments import Instrument, tests, FIELDS
from born_ladder.transport import Transport
from .runs import Manifest, exclusive_output, validate_output
from .worked_science import induced, joined, sequential_certificate, finite_certificate, ensembles, order_certificate, order_diagnostics
from .embedding import transport, ensemble, fragment, order, ri


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    blob=json.dumps(A.qserial(value),indent=2,sort_keys=True,allow_nan=False)+'\n'
    if path.exists():
        if path.read_text()!=blob:raise ValueError('resume input or scientific result changed: '+str(path))
    else:
        temporary=path.with_suffix(path.suffix+'.tmp');temporary.write_text(blob);temporary.replace(path)


def frame(context):
    v=list(map(Q,context['born']['sym_eigvec_basis'][0]));n=len(v)
    if n!=32:raise ValueError('worked case requires 32 states')
    w=[x-sum(v)/n for x in v];s=sum(x*x for x in w)
    if s<=0:raise ValueError('worked case has zero centered vector')
    K=[list(map(Q,row)) for row in context['kernel']]
    if len(K)!=n or any(len(row)!=n or min(row)<0 for row in K):raise ValueError('kernel shape/positivity')
    P=[[Q(1,n)+a*b/s for b in w] for a in w]
    return w,s,P,K


def captured_context(runs, wanted, specifications, capture_grid):
    """Read one successful execution, bind header maps to emitted preparation/vector."""
    # Resolve the registered grid's seed references with the public run planner.
    from dataclasses import asdict
    from .runs import RunSpecifications
    jobs=[asdict(j) for j in RunSpecifications(specifications).grid(capture_grid) if j.configuration==wanted['configuration']]
    if len(jobs)!=1:raise ValueError('worked-case grid identity is ambiguous')
    job=jobs[0];matches=[]
    for root in map(Path,runs):
        stored=read(root/'runset.json');jobs_by_id={j['id']:j for j in stored['invocations']}
        for identifier,row in Manifest(root).completed().items():
            j=jobs_by_id[identifier]
            if all(j[k]==job[k] for k in ('experiment','configuration','seed','scale')):matches.append((root,row))
    if len(matches)!=1:raise ValueError('expected one successful capture for '+wanted['configuration'])
    root,row=matches[0]
    def artifacts(suffix):return [root/a['path'] for a in row['artifacts'] if a['path'].endswith(suffix)]
    kernels=artifacts('.kernel.json');headers=artifacts('.audit.jsonl')
    if len(kernels)!=1 or len(headers)!=1:raise ValueError('worked case needs full K and audit-header capture')
    kernel=read(kernels[0]);header=json.loads(headers[0].open().readline())
    if (kernel['exp'],kernel['config'],kernel['kernel_seed'],kernel['n'])!=(job['experiment'],job['configuration'],job['seed'],job['scale']):raise ValueError('kernel capture identity differs')
    if kernel['kernel']!=header['kernel']:raise ValueError('kernel/header matrix differs')
    contexts=[c for c in header['contexts'] if (c['k'],c['step_index'])==(wanted['resolution'],wanted['step_index'])]
    if len(contexts)!=1:raise ValueError('worked-case maps unavailable or duplicated')
    lens=contexts[0];stdout=next(root/a['path'] for a in row['artifacts'] if a['path'].endswith('stdout.bin'))
    born=[]
    with stdout.open() as stream:
        for line in stream:
            if line.startswith('KEY_BORN_PROBE_JSON '):
                b=json.loads(line.split(' ',1)[1])
                if (b['cell'],b['k'],b['step_index'])==(job['configuration'],wanted['resolution'],wanted['step_index']):born.append(b)
    if len(born)!=1:raise ValueError('worked-case emitted source unavailable or duplicated')
    born=born[0]
    if born['partition']!=lens['raw_by_state'] or born['packaging']!=lens['package_by_state']:raise ValueError('emitted/header maps differ')
    if (born['seed'],born['scale'])!=(job['seed'],job['scale']):raise ValueError('emitted source identity differs')
    if len(born['sym_eigvec_basis'])!=1 or len(born['sym_eigvec_basis'][0])!=32:
        raise ValueError('worked-case rank-two emitted span differs')
    starts=born['starts'];tau=born['tau']
    if not starts or any(type(i) is not int or not 0<=i<32 for i in starts) or type(tau) is not int or tau<0:
        raise ValueError('worked-case preparation recipe differs')
    from born_ladder.certificates import native_step
    preparation=[0.]*32
    for i in starts:preparation[i]+=1./len(starts)
    for _ in range(tau):preparation=native_step(kernel['kernel'],preparation)
    if preparation!=born['p_theory']:
        raise ValueError('worked-case preparation replay differs')
    alphabet=sorted(set(zip(born['partition'],born['packaging'])))
    if lens['joint_by_state']!=[alphabet.index(pair) for pair in zip(born['partition'],born['packaging'])]:raise ValueError('immutable joint maps differ')
    return {'identity':{'exp':job['experiment'],'config':job['configuration'],'seed':job['seed'],'scale':job['scale'],'k':wanted['resolution'],'step_index':wanted['step_index']},
            'kernel':kernel['kernel'],'born':born,'lens':{f:lens[f] for f in FIELDS}}


def selected_witness(m):
    # Original RI rule: labels in numeric order, then pairs in state order.
    tried=0
    for block in m.parts['joint_by_state'].values():
        for i,j in itertools.combinations(block,2):
            tried+=1
            if any(q[i]!=q[j] for q in m.x['lens'].values()):continue
            left,right=m.pure(32*m.w[i]/m.s),m.pure(32*m.w[j]/m.s)
            if left==right:continue
            readouts=[]
            for field,part in m.parts.items():
                for label,S in part.items():
                    a=A.asI(A.trace(A.matmul(left,m.C[S])));b=A.asI(A.trace(A.matmul(right,m.C[S])));diff=a-b
                    if diff.lo>0 or diff.hi<0:readouts.append({'context':field,'outcome':label,'left':a.json(),'right':b.json(),'difference':diff.json()})
            if readouts:
                from born_ladder.certificates import old_view
                p=[Q(int(k==i)) for k in range(32)];pp=[Q(int(k==j)) for k in range(32)]
                old,other=old_view(m,p),old_view(m,pp)
                if old!=other:raise ValueError('selected initial record descriptions differ')
                return {'pairs_tested':tried,'certificate':{'point_indices':[i,j],'p':A.qserial(p),'p_prime':A.qserial(pp),
                        'left_density':A.ijs(left),'right_density':A.ijs(right),'density_separation':A.separated(left,right),'readout_splits':readouts,
                        'left_old_view':old,'right_old_view':other,'old_field_matches':{k:old[k]==other[k] for k in old},'every_old_field_equal':True}}
    raise ValueError('selected strict-refinement witness unresolved')


def original_certificates(context, contract):
    w,s,P,K=frame(context);t=Transport(context,w,s,P,K);m=Instrument(context,w,s,P,K)
    amplitude=induced(context,w,s,P,K);augmented=joined(t)
    two_read=sequential_certificate(t,contract['ensemble_frame_charts'])
    basis=[A.eye(),m.C[m.parts['joint_by_state'][0]],m.C[m.parts['joint_by_state'][1]]]
    finite={'basis_exact':A.qserial(basis),'parent':parent_certificate(m),
            'programs':[{'contexts':list(cs),'words':[list(word) for word in words],'events':1<<len(words)} for cs,words in tests(m)],
            'atomic_effects':{f:[A.qserial(m.C[S]) for S in part.values()] for f,part in m.parts.items()},
            'non_density':non_trace_fragment(m,basis)}
    return {'amplitude':amplitude,'joined':augmented,'ensemble':two_read,'finite_family':finite,
            'finite_events':finite_certificate(m,ensembles(w,contract['ensemble_frame_charts'])),'order':order_certificate(m),
            'lean_certificates':{'B04':A.qserial(transport.extract(context,amplitude,augmented)),
                                 'B05':A.qserial(ensemble.extract(context,two_read)),
                                 'B06':A.qserial(fragment.extract(context,finite)),
                                 'B07':A.qserial(order.extract(context))}}



def validate_contract(contract):
    if contract['schema']!='born_worked_case_contract_v1':raise ValueError('unknown worked-case contract')
    expected={'null_direction_amplitude_scale':'1/4','source_root_bits':A.BITS,
              'lean_root_bits':{'B04':40,'B05':64,'B07':64},
              'registered_family':{'maps':list(FIELDS),'program_lengths':[1,2],'all_words':True,'all_groupings':True}}
    if any(contract[k]!=value for k,value in expected.items()):
        raise ValueError('worked-case numerical contract differs from the implemented historical algorithm')


def carrier_certificate(m):
    # Exact quadratic-coefficient identity is checked by the existing public code.
    parent_certificate(m)
    v=list(map(Q,m.x['born']['sym_eigvec_basis'][0]));rowsums=list(map(sum,m.K));atoms=[]
    if min(rowsums)<=0:raise ValueError('kernel row support missing')
    # Gram bounds for (ones/sqrt(32), emitted): diagonal entries are 1
    # and ||v||², and the off-diagonal square is (sum v)²/32.
    # Gershgorin gives eigenvalues in [1/4,9/4], hence both singular
    # directions exceed the public rank cutoff 32*2^-52*sigma_max.
    # This checks rank without an SVD or asserting anything about its basis.
    if not Q(1,2)<=sum(x*x for x in v)<=2 or sum(v)**2/32>Q(1,16):
        raise ValueError('emitted span numerical-rank margin unresolved')
    for field,part in m.parts.items():
        for label,block in part.items():
            H=[[Q(len(block)),sum(m.w[i] for i in block)],[sum(m.w[i] for i in block),sum(m.w[i]**2 for i in block)]]
            atoms.append({'context':field,'outcome':label,'states':list(block),'H':A.qserial(H),
                          'effect':A.qserial(m.C[block]),'Gram_det':str(A.det(H))})
    checked=[]
    for name,amp in [('uniform',[Q(1)]*32)]+[('delta'+str(i),[Q(int(j==i)) for j in range(32)]) for i in range(32)]:
        projected=A.mv(m.P,amp);mass=sum(x*x for x in projected)
        aa=sum(amp)/32;bb=sum(a*w for a,w in zip(amp,m.w))/m.s
        rho=[[aa*aa*32/mass,aa*bb*m.s/mass],[aa*bb*32/mass,bb*bb*m.s/mass]]
        for part in m.parts.values():
            for block in part.values():
                if A.trace(A.matmul(rho,m.C[block]))!=sum(projected[i]**2 for i in block)/mass:
                    raise ValueError('carrier trace coefficient identity failed')
        checked.append(name)
    return {'exact_source_rank':2,'landed_retained_rank':2,'mean':str(sum(v)/32),'s':str(m.s),
            'distinct_mode_values':len(set(m.w)),'P_symmetric_idempotent_constant':True,'parent_sum_exact_I':True,
            'atom_positivity':atoms,'trace_check_preparations':checked,'K_row_masses':A.qserial(rowsums),
            'K_max_row_mass_error':str(max(abs(x-1) for x in rowsums)),'K_no_row_normalization':True}


def run_worked_cases(*,runs,output,specifications=Path('specifications')):
    start=time.monotonic();cpu=time.process_time();output=validate_output(output,Path.cwd())
    contract=read(Path(specifications)/'worked_cases.json')
    validate_contract(contract)
    with exclusive_output(output):
        for name,wanted in contract['contexts'].items():
            context=captured_context(runs,wanted,specifications,contract['capture_grid']);w,s,P,K=frame(context)
            context['exact']={'w':A.qserial(w),'s':str(s),'projector':A.qserial(P)}
            directory=output/name;write(directory/'CONTEXT.json',context)
            if name=='original':cert=original_certificates(context,contract)
            else:
                m=Instrument(context,w,s,P,K);witness=selected_witness(m)
                cert={'parent':parent_certificate(m),'carrier':carrier_certificate(m),'strictness':witness,'six_state':A.certify_G(s),
                      'lean_certificates':{'RI':A.qserial(ri.extract(context,witness))}}
                write(directory/'initial_strictness_certificate.json',witness)
                write(directory/'six_state_certificate.json',cert['six_state'])
            write(directory/'certificates.json',cert)
            if name=='original':
                # Separate supplementary scientific output permits old completed
                # certificates/Lean inputs to resume without rewriting them.
                m=Instrument(context,w,s,P,K)
                write(directory/'order_diagnostics.json',order_diagnostics(m))
        summary={'schema':'born_worked_case_certificates_v1','completed':['original','selected'],'wall_seconds':time.monotonic()-start,
                 'cpu_seconds':time.process_time()-cpu,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                 'output_bytes':sum(p.stat().st_size for p in output.rglob('*') if p.is_file())}
        # Resource measurements belong to the attempt, never to a scientific certificate.
        attempt=len(list(output.glob('cost_*.json')))+1;write(output/f'cost_{attempt:04d}.json',summary)
    return summary
