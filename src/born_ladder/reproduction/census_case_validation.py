"""Complete input binding and independent field audit for a new census case.

No production certificate constructor, interval arithmetic or instrument imports.
The native SVD constructor is replayed for its explicitly platform-dependent
bit diagnostics; mathematical carrier/root/enclosure checks use Fraction here.
"""
from fractions import Fraction as Q
import hashlib
import json
import math
from pathlib import Path

from born_ladder.archive import Archive, canonical, safe_name, sha
from born_ladder import metadata

FIELDS = ('raw_by_state', 'package_by_state', 'joint_by_state')
IDENTITY = ('unit_id','experiment','actual_source_cell','seed','scale','resolution','step','context','partition','invocation_id')


class RetainedInputs:
    """Read the census's sealed storage view; hash shared captures only once."""
    def __init__(self, root):
        self.root = Path(root).resolve(); self.hashes = {}
        seal = json.loads((self.root/'complete.json').read_text())
        self.commitments = {r['path']: r['sha256'] for r in seal['artifacts']}
        summary = seal['summary']
        inventory_name = str(Path(summary['inventory_directory'])/'INVENTORY.json')
        self.verify(self.root/inventory_name, self.commitments[inventory_name])
        self.inventory = {r['unit_id']: r for r in json.loads((self.root/inventory_name).read_text())}
        self.indices = {uid:index for index,uid in enumerate(self.inventory)}
        self.symbolic_replays = {}
        plan = self.root/'census_plan.json'
        self.verify(plan, self.commitments['census_plan.json'])
        document = json.loads(plan.read_text())
        self.files = document['logical_to_execution_files']
        self.capture_bindings = {}
        for row in document.get('capture_bindings',[]):
            capture_key = (row['invocation_id'], row['config'])
            if capture_key in self.capture_bindings:
                raise ValueError('duplicate retained invocation/configuration capture')
            self.capture_bindings[capture_key] = row
        self.archive = Archive({'schema':'born_structural_input_view_v1','root':str(self.root),'files':self.files})

    def verify(self, path, expected):
        path = Path(path)
        if path not in self.hashes:self.hashes[path] = sha(path)
        if self.hashes[path] != expected:raise ValueError('retained input hash differs: '+str(path))

    def path(self, name):
        name = str(safe_name(name))
        return self.root/name if name in self.commitments else self.archive.path(name)

    def line(self, pointer, payload=False):
        name = str(safe_name(pointer['path'])); path = self.path(name)
        self.verify(path, pointer['file_sha256'])
        view = Archive({'schema':'born_structural_input_view_v1','root':str(self.root),'files':{name:str(path)}})
        return view.line(pointer, payload)


def locate_inputs(directory):
    for parent in Path(directory).resolve().parents:
        if (parent/'complete.json').is_file() and (parent/'census_plan.json').is_file():
            return RetainedInputs(parent)
    raise ValueError('retained inventory/source view required for independent validation')


def bind_inputs(c, context, inventory, inputs):
    uid = inventory['unit_id']; key = inventory['provenance_key']
    expected_identity = {k:key[k] for k in IDENTITY}
    c.compare('complete_context_schema',sorted(context),sorted(['identity','kernel','born','lens','exact','archived_unit_structural']))
    c.compare('retained_context_identity',context['identity'],expected_identity)
    c.compare('retained_inventory_gates',
        [inventory['n'],inventory['retained_rank'],inventory['original_columns'],inventory['immutable_join_verified'],inventory['source_span_available']],
        [32,2,2,True,True])
    kernel = inventory['kernel']; pointer = kernel['artifact']
    c.compare('retained_kernel_identity',[kernel,key['kernel']],[key['kernel'],kernel])
    c.compare('retained_kernel_contract',[kernel['operation'],kernel['status'],pointer['exponent'],pointer['matrix_shape']],['K','AVAILABLE',1,[32,32]])
    # An adapter has no seed/configuration header. Bind its native field/file
    # commitments to the sealed invocation/configuration acquisition join, so a
    # different case's valid K adapter cannot be substituted.
    if 'native_capture_sha256' in pointer:
        configuration = key['config_or_null'] or key['actual_source_cell']
        binding=inputs.capture_bindings[(key['invocation_id'], configuration)]
        c.compare('retained_kernel_capture_join',
            [pointer['path'],pointer['file_sha256'],pointer['native_capture_sha256'],
             pointer['native_kernel_field_sha256'],pointer['field_sha256']],
            [binding['adapter_path'],binding['adapter_sha256'],binding['native_capture_sha256'],
             binding['kernel_field_sha256'],binding['kernel_field_sha256']])
        c.compare('retained_kernel_capture_configuration',binding['config'],configuration)
    body, prefix, _ = inputs.line(pointer, True)
    lo, hi = pointer['char_range']; field = body[lo:hi]
    c.compare('retained_kernel_field_commitment',hashlib.sha256(field.encode()).hexdigest(),pointer['field_sha256'])
    K = json.loads(field)
    c.compare('retained_exponent_one_metadata',
        metadata.metadata(body,metadata.SEQ_KEYS)['tau']-metadata.metadata(body,metadata.SEQ_KEYS)['t_mid'],1)
    c.compare('retained_kernel_values',context['kernel'],K)
    c.compare('retained_kernel_shape',[len(K),*[len(row) for row in K]],[32]+[32]*32)
    if len(K)!=32 or any(len(row)!=32 for row in K) or any(not math.isfinite(v) or v<0 for row in K for v in row):
        raise ValueError('invalid retained matrix shape or entries')
    born_body, _, _ = inputs.line(inventory['source']['born'], True)
    born = metadata.metadata(born_body,metadata.BORN_KEYS|{'p_theory','pi'})
    c.compare('retained_complete_born_inputs',context['born'],born)
    c.compare('retained_born_provenance',
        [born[k] for k in ('seed','cell','scale','k','step_index')],
        [key[k] for k in ('seed','actual_source_cell','scale','resolution','step')])
    c.compare('retained_preparation_recipe',key['preparation']['starts'],born['starts'])
    c.compare('retained_preparation_lag',key['preparation']['tau'],born['tau'])
    maps = {'raw_by_state':born['partition'],'package_by_state':born['packaging']}
    pairs = sorted(set(zip(born['partition'],born['packaging'])))
    maps['joint_by_state'] = [pairs.index(pair) for pair in zip(born['partition'],born['packaging'])]
    c.compare('retained_lens_inputs',context['lens'],maps)
    c.compare('retained_inventory_maps',
        [inventory['lenses'][name+'_map'] for name in ('raw','package','joint')],[maps[f] for f in FIELDS])
    c.compare('retained_lens_field_commitments',key['lens_inputs'],metadata.refs(born_body,{'partition','packaging'}))
    c.compare('retained_mode_field_commitment',key['source_span_input']['mode_input'],metadata.refs(born_body,{'sym_eigvec_basis'})['sym_eigvec_basis'])
    c.compare('retained_mode_dimensions',[len(born['sym_eigvec_basis']),*[len(v) for v in born['sym_eigvec_basis']]],[1,32])
    c.compare('retained_complete_span_input',key['source_span_input'],
        {'constant_column':'all ones on ordered micro support','mode_input':metadata.refs(born_body,{'sym_eigvec_basis'})['sym_eigvec_basis'],
         'mode_shapes':[len(v) for v in born['sym_eigvec_basis']],'spectral_mode_count':len(born['sym_eigvec_basis'])})
    units = {}
    c.compare('retained_kind_membership',sorted(p['kind'] for p in inventory['kind_records']),['pkg','raw'])
    for pointer_unit in inventory['kind_records']:
        body_unit, _, _ = inputs.line(pointer_unit)
        structural_keys = metadata.UNIT_KEYS|{'unrounded_p_full','spectral_coefficients'}
        unit = metadata.metadata(body_unit,structural_keys); kind = pointer_unit['kind']; units[kind] = unit
        refs = metadata.refs(body_unit,structural_keys)
        c.compare('retained_unit_field_commitments',
            {k:refs.get(k) for k in pointer_unit['fields']},pointer_unit['fields'],kind)
        c.compare('retained_unit_complete_inputs',context['archived_unit_structural'][kind],unit,kind)
        c.compare('retained_unit_provenance',{k:unit.get(k) for k in metadata.UNIT_KEYS & set(key)},
            {k:key[k] for k in metadata.UNIT_KEYS & set(key)},kind)
        c.compare('retained_unit_preparation',unit['unrounded_p_full'],born['p_theory'],kind)
        c.compare('retained_basis_preparation_commitments',
            [refs['basis_and_projector_inputs']['field_sha256'],refs['unrounded_p_full']['field_sha256']],
            [key['basis_projector_field_sha256'],key['preparation_input_sha256']],kind)
        c.compare('retained_kind_identity',unit['kind_cell_id'],hashlib.sha256((uid+kind).encode()).hexdigest(),kind)
        c.compare('retained_unit_labels',unit['ordered_state_labels'],['state_'+str(i) for i in range(32)],kind)
        for f,label,prefix_label in [('M_raw_or_content_hash','partition','group_'),('M_pkg_or_content_hash','packaging','package_')]:
            c.compare('retained_unit_label_maps',unit[f],
                [[float(prefix_label+str(g)==lab) for g in born[label]] for lab in unit['ordered_union_outcome_labels']],kind+'/'+f)
    c.compare('retained_context_kind_membership',sorted(context['archived_unit_structural']),['pkg','raw'])
    c.compare('retained_shared_basis',units['raw']['basis_and_projector_inputs'],units['pkg']['basis_and_projector_inputs'])
    return {'K':K,'born':born,'units':units,'identity':expected_identity,'pointer':pointer,
            'byte_range':[pointer['byte_offset']+prefix+len(body[:lo].encode()),pointer['byte_offset']+prefix+len(body[:hi].encode())]}


# Independent dyadic interval operations for the disclosed 384-bit contract.
# The endpoints are derived here, rather than compared only with a Decimal
# point control (which cannot certify an upper endpoint or its stored width).
DEN = 2**384
def interval(x):return x if isinstance(x,tuple) else (Q(x),Q(x))
def hull(a,b):return (Q((a.numerator*DEN)//a.denominator,DEN),Q(-((-b.numerator*DEN)//b.denominator),DEN))
def plus(a,b):
    a,b=interval(a),interval(b);return hull(a[0]+b[0],a[1]+b[1])
def minus(a,b):
    b=interval(b);return plus(a,(-b[1],-b[0]))
def times(a,b):
    a,b=interval(a),interval(b);v=[x*y for x in a for y in b];return hull(min(v),max(v))
def divide(a,b):
    b=interval(b)
    if b[0]<=0<=b[1]:raise ValueError('nonpositive enclosure denominator')
    return times(a,hull(min(1/b[0],1/b[1]),max(1/b[0],1/b[1])))
def square(a):
    a=interval(a);return hull(0 if a[0]<=0<=a[1] else min(v*v for v in a),max(v*v for v in a))
def root(a):
    a=interval(a)
    if a[0]<0:raise ValueError('negative radical')
    low=Q(math.isqrt((a[0].numerator*DEN*DEN)//a[0].denominator),DEN)
    high=Q(math.isqrt((a[1].numerator*DEN*DEN)//a[1].denominator),DEN)
    if high*high<a[1]:high+=Q(1,DEN)
    return low,high
def absolute(a):
    a=interval(a);return (Q(0) if a[0]<=0<=a[1] else min(abs(v) for v in a),max(abs(v) for v in a))
def total(values):
    out=interval(0)
    for value in values:out=plus(out,value)
    return out
def interval_json(a):return {'lo':str(a[0]),'hi':str(a[1]),'lo_approx':float(a[0]),'hi_approx':float(a[1])}
def serial(x):
    if isinstance(x,Q):return str(x)
    if isinstance(x,list):return [serial(v) for v in x]
    if isinstance(x,dict):return {k:serial(v) for k,v in x.items()}
    return x
def remove_costs(x):
    # Only declared top-level step costs are excluded. A nested field with
    # this name is still an unexpected stored field and must fail its schema.
    if isinstance(x,dict):return {k:v for k,v in x.items() if k!='wall_seconds'}
    return x


def typed_trine(s):
    """Complete JSON expectations from the exact real-trine coordinates."""
    d=3*s/32
    zero=(Q(0),Q(0));one=(Q(1),Q(0))
    matrices=[[[one,zero],[zero,zero]],
              [[(Q(1,4),Q(0)),(Q(0),Q(1,4))],[(Q(0),8/s),(Q(3,4),Q(0))]],
              [[(Q(1,4),Q(0)),(Q(0),Q(-1,4))],[(Q(0),-8/s),(Q(3,4),Q(0))]]]
    matrices += [[[(Q(int(i==j))-v[0],-v[1]) for j,v in enumerate(line)]
                  for i,line in enumerate(matrix)] for matrix in matrices[:]]
    return {'status':'PASS','G':[['32','0'],['0',str(s)]],'exact_radicand':str(d),
        'states_and_sharp_yes_effects':[
            [[{'rational':str(a),'radical_coefficient':str(b),'radicand':str(d),
               'root':'positive square root'} for a,b in line] for line in matrix] for matrix in matrices],
        'YES_table_exact':[[1,'1/4','1/4'],['1/4',1,'1/4'],['1/4','1/4',1],
                           [0,'3/4','3/4'],['3/4',0,'3/4'],['3/4','3/4',0]],
        'five_mixture_identities':[[[i,'1/2'],[i+3,'1/2']] for i in range(3)]+
                                  [[[i,'1/3'] for i in range(3)],[[i,'1/3'] for i in range(3,6)]],
        'projector_roots':True,'all_projectors_trace1_idempotent_G_adjoint':True,
        'transformation':'S=diag(sqrt32,sqrt(s)); R_G=S^-1 R_orth S. upper offdiag=sign sqrt(3s/32)/4, lower=32/s*upper. Every expression multiplied in Q[sqrt(3s/32)], sqrt positive. This is exact conjugacy with the external real trine, not a new state or test.',
        'real_positivity':'Positive G inner product (32,s>0); conjugacy to orthonormal real projectors proves PSD, not just trace/determinant.'}


def audit_original(c, directory, row, original, correspondence, s, inputs):
    """Bind original records and dispositions; replay successful native payloads.

    Recorded native exceptions are environment-specific events. They are
    explicitly qualified, rather than derived from the repaired exact proof.
    """
    stored=json.loads((directory/'original_implementation.json').read_text())
    c.compare('original_summary_file_binding',original,
              {'index':row['index'],'unit_id':row['unit_id'],**stored})
    premise=stored.get('C_premises',{});status=premise.get('status')
    c.compare('original_native_premise_status',type(status) is str and status in ('PASS','FAILED'),True)
    keys=['status'] if status=='PASS' else ['status','error_type','error']
    c.compare('original_native_premise_schema',sorted(premise),sorted(keys))
    qualified=[]
    if status=='FAILED':
        c.compare('original_native_exception_types',
                  [type(premise.get('error_type')) is str and bool(premise.get('error_type')),
                   type(premise.get('error')) is str],[True,True])
        qualified=['original_implementation.json/C_premises/status',
                   'original_implementation.json/C_premises/error_type',
                   'original_implementation.json/C_premises/error',
                   'original_implementation.json/status (native-event truth; disposition checked)',
                   'original_implementation.json/classification (native-event truth; disposition checked)']
    native_correspondence=correspondence['status']
    if Q(correspondence['constructor_maximum_difference'])>Q(correspondence['threshold_exact']):
        native_correspondence='FAILED'
    expected={'status':'PASS' if status==native_correspondence=='PASS' else 'FAILED',
        'correspondence_status':native_correspondence,'C_premises':premise,
        'classification':'extra SVD-coordinate requirement' if native_correspondence=='FAILED' else
                         'symbolic implementation failure' if status!='PASS' else 'completed original implementation',
        'origin':'re-executed original implementation checks on explicit construction inputs; not copied historical verdicts'}
    c.compare('complete_original_outcome',stored,expected)
    names=['CONTEXT.json','structural_completion_certificate.json','original_implementation.json',
           'six_state_exact_completion.json','integer_frame.json','maximal_gap_witness.json',
           'atom_classes.json','instrument_root_controls.json','landed_own_input_prediction.json']
    if status=='PASS':names.append('six_state_symbolic_original.json')
    c.compare('complete_case_record_population',sorted(p.name for p in directory.iterdir()),sorted(names))
    if status=='PASS':
        # This is a disclosed replay of the original implementation, distinct
        # from the independent exact trine proof. Do not call original_status.
        from .census_writers.legacy_trine import witness
        if s not in inputs.symbolic_replays:
            inputs.symbolic_replays[s]=json.loads(json.dumps(witness(s)[0]))
        c.compare('complete_original_symbolic_native_replay',
                  json.loads((directory/'six_state_symbolic_original.json').read_text()),inputs.symbolic_replays[s])
    return qualified


def principal(effect):
    C=effect; zero=[[Q(0)]*2 for _ in range(2)]
    if C==zero:return [[interval(0)]*2 for _ in range(2)],{'method':'exact zero','rational_root':serial(zero)}
    det=C[0][0]*C[1][1]-C[0][1]*C[1][0]; trace=C[0][0]+C[1][1]
    def rational_sqrt(q):
        a,b=math.isqrt(q.numerator),math.isqrt(q.denominator)
        return Q(a,b) if a*a==q.numerator and b*b==q.denominator else None
    d=rational_sqrt(det); z=rational_sqrt(trace+2*d) if d is not None else None
    if z is not None:
        R=[[(C[i][j]+(d if i==j else 0))/z for j in range(2)] for i in range(2)]
        return [[interval(v) for v in row] for row in R],{'method':'exact rational principal root','rational_root':serial(R),'trace_C':str(trace),'det_C':str(det)}
    d=root(det); z=root(plus(trace,times(2,d)))
    R=[[divide(plus(C[i][j],d) if i==j else C[i][j],z) for j in range(2)] for i in range(2)]
    encloses=all(total(times(R[i][k],R[k][j]) for k in range(2))[0]<=C[i][j]<=total(times(R[i][k],R[k][j]) for k in range(2))[1] for i in range(2) for j in range(2))
    if not encloses:raise ValueError('principal root square enclosure fails')
    return R,{'method':'certified principal radical (C+sqrt(det C)I)/sqrt(tr C+2sqrt(det C))','trace_C':str(trace),'det_C':str(det),
              'sqrt_det':interval_json(d),'denominator':interval_json(z),'root_squared_encloses_C':encloses}


def expected_strictness(context, recomputed):
    w=list(map(Q,recomputed['w']));s=Q(recomputed['s']);n=len(w);witness=recomputed['witness']
    i,j=witness['pair'];field=witness['context'];label=witness['atom']
    def density(point):
        lam=n*w[point]/s;den=n+s*lam*lam
        return [[Q(n)/den,lam*s/den],[lam*n/den,lam*lam*s/den]]
    states=[t for t,g in enumerate(context['lens'][field]) if g==label]
    def readout(point):return sum((1+n*w[point]*w[t]/s)**2 for t in states)/(n*(1+n*w[point]**2/s))
    left,right=readout(i),readout(j)
    old={'context':context['identity'],'preparation_receipt':{'class':'Audit A anonymous simplex mathematical source','recipe_id':None},
        'actual_passive_laws':{f:{str(g):str(Q(int(context['lens'][f][i]==g))) for g in sorted(set(context['lens'][f]))} for f in FIELDS},
        't':0,'lag':8,'history_horizons':[0],'coefficient_history_arrays':None,'acquired_passive_prefix':[],
        'commands':[],'acquired_upper_outcomes':[],'status':'PREPARATION_ENTRY','precision':'exact coefficient contract',
        'source_policy':'fixed amended full simplex, no sampled preparation population'}
    return {'status':'PASS','witness_type':'CERTIFIED STRICT REFINEMENT','pairs_visited':witness['visited'],'pair':[i,j],
        'preparations':{'p':[str(Q(int(t==i))) for t in range(n)],'p_prime':[str(Q(int(t==j))) for t in range(n)]},
        'complete_equal_old_view':old,'all_old_fields_exact_equal':all(context['lens'][f][i]==context['lens'][f][j] for f in FIELDS),
        'rho_left':serial(density(i)),'rho_right':serial(density(j)),'density_exact_inequality':density(i)!=density(j),
        'first_separating_readout':{'context':field,'numeric_atom':label,'left_exact':str(left),'right_exact':str(right),
            'difference_exact':str(left-right),'difference_display':float(left-right)},'point_identifying_receipt_rejects_witness':True}


def numerical_certificate(context, recomputed):
    """Audit all interval endpoints and native numerical diagnostics, not gates alone."""
    import numpy as np
    from born_ladder.snapshot.g2a import _oriented_basis
    born=context['born'];arch=context['archived_unit_structural']['raw']['basis_and_projector_inputs']
    rebuilt=_oriented_basis(born);differences=[]
    def compare(a,b,path=''):
        if isinstance(a,dict):
            if set(a)!=set(b):differences.append({'field':path,'categorical_or_shape_mismatch':True});return
            for key in a:compare(a[key],b[key],path+'/'+key)
        elif isinstance(a,list):
            if not isinstance(b,list) or len(a)!=len(b):differences.append({'field':path,'categorical_or_shape_mismatch':True});return
            for index,(x,y) in enumerate(zip(a,b)):compare(x,y,path+'/'+str(index))
        elif a!=b:
            differences.append({'field':path,'rebuilt':a,'archived':b,'absolute_difference':str(abs(Q(a)-Q(b)))})
    compare(rebuilt,arch)
    maxima={}
    for difference in differences:
        group=difference['field'].split('/')[1];maxima[group]=max(maxima.get(group,Q(0)),Q(difference.get('absolute_difference','0')))
    p=born['p_theory'];tilde=[[Q(v) for v in row] for row in arch['projector']];P=[[Q(v) for v in row] for row in recomputed['P']]
    delta2=sum((x-y)**2 for a,b in zip(P,tilde) for x,y in zip(a,b));delta=root(delta2)
    uniform=32*delta[1]*(2+delta[1]);roots=[root(v) for v in p]
    def probabilities(matrix):
        amps=[total(times(a,b) for a,b in zip(row,roots)) for row in matrix];mass=total(square(a) for a in amps)
        return [divide(square(a),mass) for a in amps]
    exact=probabilities(P);rounded=probabilities(tilde)
    # Independently replay the native fsum projector/square/mass rule.
    amplitudes=[math.fsum(float(v)*math.sqrt(x) for v,x in zip(row,p)) for row in arch['projector']]
    squares=[v*v for v in amplitudes];mass=math.fsum(squares);q=[v/mass for v in squares]
    source_error=max(absolute(minus(v,x))[1] for v,x in zip(exact,q))
    float_error=max(absolute(minus(v,x))[1] for v,x in zip(rounded,q))
    float_tv=sum(absolute(minus(v,x))[1] for v,x in zip(rounded,q))/2
    a=np.array(arch['projector'])@np.sqrt(np.array(p));direct=a*a/np.dot(a,a)
    parity=max(abs(Q(float(v))-Q(x)) for v,x in zip(direct,q))
    u=Q(1,2**53);eta=Q(1,2**1074);gamma=lambda n:n*u/(1-n*u)
    norm=root(sum(v*v for row in tilde for v in row))[1]
    eps=(1+delta[1])*u+gamma(66)*norm*(1+u)+4096*eta;normlo=root(Q(1,32))[0]-delta[1]
    envelope=eps*(2*(1+delta[1])+eps)/normlo**2+gamma(38)+2048*eta/normlo**2 if normlo>0 else None
    shape=not any(d.get('categorical_or_shape_mismatch') for d in differences)
    passed=shape and normlo>0 and all(v<=Q(1,10**12) for v in (uniform,source_error,float_error,parity))
    certificate={'status':'PASS' if passed else 'FAILED','threshold_exact':'1/1000000000000',
        'constructor_literal_bit_equality_status':'PASS' if not differences else 'FAILED','constructor_differences':differences,
        'constructor_group_maxima':serial(maxima),'constructor_maximum_difference':str(max((Q(d['absolute_difference']) for d in differences if 'absolute_difference' in d),default=Q(0))),
        'constructor_categorical_shape_parity':shape,'native_preparation_replay_maximum_error_exact':'0','delta_squared_exact':str(delta2),'delta_interval':interval_json(delta),
        'uniform_projector_TV_bound_exact':str(uniform),'uniform_projector_TV_bound_display':float(uniform),'rounded_nonvanishing':normlo>0,
        'own_input_exact_source_vs_landed_maximum_error':str(source_error),'own_input_exact_source_vs_landed_maximum_error_display':float(source_error),
        'own_input_rounded_evaluation_error':str(float_error),'own_input_rounded_evaluation_TV_error':str(float_tv),'native_numpy_vs_landed_fsum_maximum_error':str(parity),
        'uniform_floating_envelope':{'status':'conditional on stated arithmetic premises',
            'premises':['binary64 RN basic operations, absolute underflow eta=2^-1074','correctly rounded sqrt',
                'finite no-overflow fsum, conservative gamma66 including double rounding','square/mass/division gamma38 plus2048eta/normlo²'],
            'dot_root_norm_error':str(eps),'floating_TV_error_exact':str(envelope) if envelope is not None else None,
            'total_with_projector_TV_exact':str(uniform+envelope) if envelope is not None else None,
            'total_with_projector_display':float(uniform+envelope) if envelope is not None else None,'not_an_unconditional_platform_accuracy_proof':True},
        'fixed_output_own_input_certificate_independent_of_accuracy_premises':True}
    w=list(map(Q,recomputed['w']));s=Q(recomputed['s'])
    c0=divide(square(total(roots)),32);c1=divide(square(total(times(a,b) for a,b in zip(w,roots))),s)
    diagnostics={'status':'PASS','nonconstant_amplitude_energy_fraction':interval_json(divide(c1,plus(c0,c1))),
        'TV_exact_projected_square_to_uniform_micro32':interval_json(divide(total(absolute(minus(v,Q(1,32))) for v in exact),2)),
        'definitions':'orthonormal c0=sum sqrt(p)/sqrt32; c1=w.dot(sqrt(p))/sqrt(s), fraction=c1²/(c0²+c1²); TV at micro32 states',
        'structural_not_sampled_performance':True}
    return certificate,diagnostics,{'q_full':q,'no_scores_or_losses_computed':True,'source':'unchanged landed _recomputed_laws on immutable structural fields'}


def audit_certificate_fields(c, directory, row, cert, context, source, recomputed, atoms, roots, trine, inputs, original):
    directory=Path(directory);w=list(map(Q,recomputed['w']));s=Q(recomputed['s']);n=len(w)
    gram=[[str(n),'0'],['0',str(s)]]
    c.compare('complete_context_exact_frame',context['exact'],{'w':recomputed['w'],'s':recomputed['s'],'G':gram,'P':recomputed['P']})
    # Gram determinant n*s>0 certifies rank two; constant and centered columns
    # are orthogonal. Contracting the two rank-one factors proves P²=P.
    carrier={'status':'PASS','rank':2,'landed_retained_rank':source['units']['raw']['basis_and_projector_inputs']['effective_rank'],
        'distinct_w':len(set(w)),'G':gram,'P_symmetric_idempotent_constant':True,
        'parent_sum_exact_I':sum(w)==0 and sum(x*x for x in w)==s,
        'uniform_proof_binding':{'provided_uniform_proofs':{},'frame_context':str(inputs.root/row['context_directory']/'CONTEXT.json'),
                                 'frame_context_sha256':sha(directory/'CONTEXT.json')}}
    masses=[sum(Q(v) for v in r) for r in source['K']];error=max(abs(v-1) for v in masses)
    kernel={'status':'PASS','byte_range':source['byte_range'],'field_sha256':source['pointer']['field_sha256'],'exponent':1,
        'source':source['pointer'],'row_masses_exact':serial(masses),'maximum_row_mass_error_exact':str(error),
        'maximum_row_mass_error_display':float(error),'nonnegative_finite':True,'positive_row_masses':min(masses)>0,
        'no_row_normalization':True,'lens_source_unit_joins':True}
    correspondence,diagnostics,prediction=numerical_certificate(context,recomputed)
    qualified=audit_original(c,directory,row,original,correspondence,s,inputs)
    c.compare('complete_own_input_prediction',json.loads((directory/'landed_own_input_prediction.json').read_text()),prediction)
    factor={'status':'PASS','exact_public_preparation':'FACTORIZATION uniformly: public p + fixed encoder/model rules -> density and adopted branch products/sums, with ledger retained',
        'indexed_original_recipe':'FACTORIZATION','indexed_original_native_rule_exact_replay':True,
        'indexed_receipt':{'identity':source['identity'],'starts':source['born']['starts'],'tau':source['born']['tau'],
            'rule':'uniform over starts then sequential native binary64 accumulation','public_model_rules':'same fixed coefficients/encoder given to access-matched comparator'},
        'upper_access':'initial exact p31 independent reals,32roots/projection; fixed K/mode/lenses apparatus; pure ray1/general density2/effect3 independent reals plus exact descriptors/registers/setup. No finite exact-real bit bound or resource contest. No evolving p access.'}
    positive=sum(a['positive'] for a in atoms)
    premises={'status':'PASS','six_state_certificate_sha256':sha(directory/'six_state_exact_completion.json'),
        'new_G_frame_verified':True,'adopted_domain':'all external real densities/full effects with binary principal-root instruments and arbitrary finite nonadaptive commands; not encoded/native reachability',
        'atom_count':len(atoms),'strict_positive_atom_count':positive,'zero_atom_count':len(atoms)-positive,'negative_atom_count':0,
        'atom_certificates':atoms,'uniform_proofs_hash_binding':{},
        'invertible_atom_no_sharp_grouping_corollary':'PASS' if positive==len(atoms) else 'UNPROVED, strict positivity premise missing; full-domain C unaffected',
        'finite_root_sum_control':'PASS, not uniform proof replacement','six_state_certificate':str(inputs.root/row['context_directory']/'six_state_exact_completion.json'),
        'C_F':'PASS under its full-domain positive additive finite-simplex comparator premises',
        'C_M':'PASS under randomization/operational-mixture-identity/measurable-ontic premises','context_frame_sha256':sha(directory/'CONTEXT.json'),
        'contextual_ray_control':'PASS: barycenter branch intertwines Kraus map uniformly by linearity, law-only reproduction retained; single exact control checked',
        'commuting_simplex_control':{'status':'PASS','mass':str(Q(1,4)*Q(2,5)+Q(3,4)*Q(3,5)),
            'posterior':[str(Q(1,4)*Q(2,5)/Q(11,20)),str(Q(3,4)*Q(3,5)/Q(11,20))]},
        'zero_invalid_controls':'PASS','no_history_native_closure_H_classification_promotion_claim':True}
    expected={'kernel':kernel,'carrier':carrier,'correspondence':correspondence,'strictness':expected_strictness(context,recomputed),
              'factorization_controls':factor,'C_premises':premises,'diagnostics':diagnostics}
    c.compare('complete_scientific_certificate_groups',
              {name:remove_costs(value) for name,value in cert['certificates'].items()},expected)
    c.compare('complete_certificate_top_fields',remove_costs({k:v for k,v in cert.items() if k!='certificates'}),
        {'index':row['index'],'unit_id':row['unit_id'],'key_sha256':hashlib.sha256(canonical(inputs.inventory[row['unit_id']]['provenance_key'])).hexdigest(),
         'failures':[],'historical_fields_opened':False,'overall_status':'PASS'})
    c.compare('six_state_frame_binding',trine['G'],gram)
    # Full trine algebra is independently checked separately; reject missing,
    # extra or changed descriptive/status flags as well.
    c.compare('six_state_complete_schema',sorted(trine),sorted(['status','G','exact_radicand','states_and_sharp_yes_effects','YES_table_exact',
        'five_mixture_identities','projector_roots','all_projectors_trace1_idempotent_G_adjoint','transformation','real_positivity']))
    c.compare('six_state_quadratic_field_schema',
        [sorted(value) for matrix in trine['states_and_sharp_yes_effects'] for line in matrix for value in line],
        [sorted(['rational','radical_coefficient','radicand','root'])]*24)
    c.compare('six_state_scientific_flags',[trine['status'],trine['projector_roots'],trine['all_projectors_trace1_idempotent_G_adjoint']],['PASS',True,True])
    c.compare('six_state_contract_descriptors',
        [trine['transformation'],trine['real_positivity']],
        ['S=diag(sqrt32,sqrt(s)); R_G=S^-1 R_orth S. upper offdiag=sign sqrt(3s/32)/4, lower=32/s*upper. Every expression multiplied in Q[sqrt(3s/32)], sqrt positive. This is exact conjugacy with the external real trine, not a new state or test.',
         'Positive G inner product (32,s>0); conjugacy to orthonormal real projectors proves PSD, not just trace/determinant.'])
    classifications=[]
    for atom in atoms:
        states=atom['states'];effect=[[Q(v) for v in rr] for rr in atom['effect_exact']]
        constant=len({w[i] for i in states})==1;trace=effect[0][0]+effect[1][1]
        product=[[sum(effect[i][k]*effect[k][j] for k in range(2)) for j in range(2)] for i in range(2)]
        classifications.append({'context':atom['context'],'atom':atom['atom'],'states':states,'class':'singular' if constant else 'positive',
            'constant_block':constant,'singleton':len(states)==1,'Gram_det_exact':atom['Gram_det_exact'],'trace_exact':str(trace),
            'nonzero':trace>0,'nonprojective':product!=effect})
    c.compare('complete_atom_classes',json.loads((directory/'atom_classes.json').read_text()),
        {'schema':'born_census_atom_classes_v1','criterion':'singular iff w constant on active block','atoms':classifications,
         'all_singular_nonzero_nonprojective':all(a['nonzero'] and a['nonprojective'] for a in classifications if a['class']=='singular')})
    root_expectations=[];matrices={}
    for record in roots:
        states=record['subset'];a=sum((w[i] for i in states),Q(0));b=sum(w[i]**2 for i in states)
        effect=[[Q(len(states),n),a/n],[a/s,b/s]];matrix,certificate=principal(effect);matrices[tuple(states)]=matrix
        root_expectations.append({'subset':states,'root_certificate':certificate})
    c.compare('complete_principal_root_fields',roots,root_expectations)
    for field in FIELDS:
        labels=context['lens'][field];blocks=[tuple(i for i,v in enumerate(labels) if v==label) for label in sorted(set(labels))]
        for i in range(2):
            for j in range(2):
                value=total(total(times(matrices[S][i][k],matrices[S][k][j]) for k in range(2)) for S in blocks)
                c.compare('finite_principal_root_sum_enclosure',value[0]<=int(i==j)<=value[1],True,field+'/'+str(i)+'/'+str(j))
    return {'unchecked_scientific_fields':qualified,
            'original_native_failure_scope':'Recorded exception event bound to summary/file with schema and disposition checks; acquisition SymPy/GMP environment not replayed. Repaired exact proof remains independently checked.',
            'native_replayed_fields':['correspondence/constructor_*','correspondence/native_numpy_vs_landed_fsum_maximum_error','six_state_symbolic_original.json (when original symbolic execution passed)'],
            'uniform_theorem_scope':'qualified contract descriptors checked; this arithmetic comparison does not repeat the separate Lean theorem audit',
            'process_only_fields':['structural_completion_certificate.json/wall_seconds',
                'structural_completion_certificate.json/certificates/*/wall_seconds',
                'completion_row/context_directory (storage value; string type checked)',
                'instrument_root_controls.json/record order (records validated by subset identity)']}
