"""Public-claim adapters. Historical evidence is explicit, local and read-only.

A bundle.json declares roots, a root/path -> SHA-256 allowlist and claim inputs.
These receipts are inputs, not a mechanism for manufacturing historical evidence.
Documentary boundary checks establish receipt consistency, not universal absence.
"""
from fractions import Fraction as Q
from pathlib import Path
import json
import math

from . import arithmetic as A
from .archive import sha
from .instruments import Instrument, FIELDS


def bundle_content_digest(doc):
    """Scientific contract digest; only storage locations may relocate.

    Claim bindings, admitted file names/digests and root names are anchored.
    Root VALUES are excluded so identical evidence can move to another disk.
    Every resolved byte is still checked after the anchor, before dispatch.
    """
    import hashlib
    payload={key:doc[key] for key in ('schema','files','claims')}
    payload['root_names']=sorted(doc['roots'])
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()


def verify_trust_anchor(doc):
    from importlib.resources import files
    anchor=json.loads(files('born_ladder').joinpath('evidence_anchor.json').read_text())
    if bundle_content_digest(doc) not in anchor['accepted_content_sha256']:
        raise ValueError('frozen historical bundle trust anchor mismatch; rehashed replacement evidence is not admitted')


class Evidence:
    def __init__(self, data, *, trusted=True):
        path = Path(data)
        self.file = path / 'bundle.json' if path.is_dir() else path
        if not self.file.is_file():
            raise ValueError('local claim bundle required: --data <bundle.json or directory containing bundle.json>')
        self.doc = json.loads(self.file.read_text())
        if self.doc.get('schema') != 'born_claim_bundle_v1':
            raise ValueError('expected born_claim_bundle_v1 with roots, files and claims')
        self.trusted=trusted
        if trusted:
            verify_trust_anchor(self.doc)
        self.roots = {name: (self.file.parent / value).resolve(strict=True)
                      for name, value in self.doc['roots'].items()}
        for name, digest in self.doc['files'].items():
            if sha(self.path(name)) != digest:
                raise ValueError('local evidence commitment differs: ' + name)

    def root(self, name):
        return self.roots[name]

    def path(self, name):
        if name not in self.doc['files']:
            raise ValueError('input not admitted by the bundle: ' + name)
        root, relative = name.split('/', 1)
        p = self.root(root) / relative
        if Path(relative).is_absolute() or not p.resolve().is_relative_to(self.root(root)):
            raise ValueError('input escapes supplied root: ' + name)
        if not p.is_file():
            raise ValueError('missing local input: ' + name)
        return p

    def read(self, name):
        return json.loads(self.path(name).read_text())

    def config(self, claim):
        if claim not in self.doc['claims']:
            raise ValueError(f'{claim} needs its named input contract in bundle.json claims.{claim}')
        return self.doc['claims'][claim]


def model(context):
    v = [Q(x) for x in context['born']['sym_eigvec_basis'][0]]
    n = len(v); mean = sum(v) / n; w = [x-mean for x in v]; s = sum(x*x for x in w)
    if s <= 0: raise ValueError('rank-two frame required')
    P = [[Q(1,n)+a*b/s for b in w] for a in w]
    return Instrument(context, w, s, P, [[Q(x) for x in row] for row in context['kernel']])


def analytic_control(claim, lean_root="lean_born"):
    """Non-empirical construction controls; uniform proofs are audited by Lean."""
    if claim in ('P06','B02'):
        from .claim_checks import embedded_carrier, structure_checks
        return structure_checks(embedded_carrier(lean_root),claim)
    from .programs import execute
    n=32; w=[Q(2*i-31) for i in range(n)]; s=sum(x*x for x in w)
    P=[[Q(1,n)+a*b/s for b in w] for a in w]
    ctx={'identity':{'source':'synthetic control'},'lens':{f:[i%2 for i in range(n)] for f in FIELDS}}
    m=Instrument(ctx,w,s,P,[[Q(int(i==j)) for j in range(n)] for i in range(n)])
    source={'kind':'density','matrix':A.qstrings(m.pure(0)),'protocol':{'public':'retained'}}
    run=execute(m,source,[{'kind':'lens','field':FIELDS[0],'mode':'retain'}])
    if run['status']!='HALT': raise ValueError('analytic interpreter failed')
    if claim=='B03':
        from .transport import Transport
        t=Transport(m.x,m.w,m.s,m.P,m.K);p=[Q(1,n)]*n
        if t.encode(p)!=t.encode(list(p)): raise ValueError('public descriptor replay differs')
        return 'exact public preparation plus fixed encoder determines the state; no normalized-history reconstruction asserted'
    if claim=='B14':
        for command in ('K','F','autonomous','if'):
            bad=execute(m,source,[{'kind':command,'mode':'retain'}])
            if bad['status']!='HALT_FAILURE': raise ValueError('undeclared command admitted')
        return 'only adopted measurement commands are admitted; native production, imported-operation return and promotion are not established'
    raise ValueError('unknown analytic control')


def test_b_inputs(e):
    from .record_tests.inputs import Inputs
    c=e.config('TB01')
    return Inputs(e.path(c['receipt']),c['receipt_sha256'],sealed_root=e.root(c['sealed_root']),
                  opened_root=e.root(c['opened_root']),certification_root=e.root(c['certification_root']))


def _exact_chart(m,p):
    pivot=next(x for x in p if x>0)
    roots=[]
    for x in p:
        z=x/pivot; a,b=math.isqrt(z.numerator),math.isqrt(z.denominator)
        if a*a!=z.numerator or b*b!=z.denominator:
            raise ValueError('registered rational-root fiber witness needed')
        roots.append(Q(a,b))
    return m.n*sum(w*x for w,x in zip(m.w,roots))/(m.s*sum(roots))


def no_lift(e,c):
    from .transport import Transport
    m=model(e.read(c['context']));t=Transport(m.x,m.w,m.s,m.P,m.K)
    for field,joined in [('amplitude_certificate',False),('joined_certificate',True)]:
        certificate=e.read(c[field])
        for operation in ('K','K2'):
            row=certificate['operations'][operation]['certificate']
            p=list(map(Q,row['p_minus'] if joined else row['p']))
            q=list(map(Q,row['p_plus'] if joined else row['p_prime']))
            if len(p)!=m.n or len(q)!=m.n or sum(p)!=1 or sum(q)!=1 or min(p+q)<0 or _exact_chart(m,p)!=_exact_chart(m,q):
                raise ValueError('encoder-fiber equality failed')
            if joined:
                for parts in m.parts.values():
                    if any(sum(p[i] for i in S)!=sum(q[i] for i in S) for S in parts.values()):
                        raise ValueError('retained old record differs')
            left=t.encode(t.propagate(p,operation));right=t.encode(t.propagate(q,operation))
            if not (left.hi<right.lo or right.hi<left.lo):
                raise ValueError('successor split not certified')
    return 'original-fixture encoder and joined-state K/K2 splits independently checked; no transfer to RI'


def sequential_boundary(e,c):
    from .transport import Transport
    from .ensemble import EnsembleInstrument
    m=model(e.read(c['context']));inst=EnsembleInstrument(Transport(m.x,m.w,m.s,m.P,m.K))
    cert=e.read(c['certificate']);pair=cert['pair_certificate'];word=cert['witness']
    left=[(Q(l),Q(w)) for l,w in pair['left']];right=[(Q(l),Q(w)) for l,w in pair['right']]
    if not left or not right or any(w<0 for _,w in left+right):
        raise ValueError('nonnegative probability ensembles required')
    def density(ensemble):
        return [[sum(weight*m.pure(lam)[i][j] for lam,weight in ensemble) for j in range(2)] for i in range(2)]
    if sum(w for _,w in left)!=1 or sum(w for _,w in right)!=1 or density(left)!=density(right):
        raise ValueError('barycenter equality failed')
    def prob(ensemble):
        S=inst.parts[word['context']][word['g']];index=list(inst.parts[word['context']]).index(word['j'])
        total=A.I(0)
        for lam,weight in ensemble:
            mass,successor=inst.general_branch(1,lam,S,word['h'])
            if successor is not None:total+=weight*mass*inst.read(successor,word['context'])[index]
        return total
    d=prob(left)-prob(right)
    if d.lo<=0<=d.hi: raise ValueError('sequential density obstruction unresolved')
    bound=word['left_minus_right']
    if d.hi<Q(bound['lo']) or d.lo>Q(bound['hi']):raise ValueError('independent enclosure differs from reviewed certificate')
    return 'equal exact barycenters have different completion-word laws; instantaneous trace pairing remains intact'


def census(e,c,claim):
    from .independent import recompute, independent_type7
    from .certificates import registered_correspondence, point_search
    old=e.read(c['original']);completed=e.read(c['completed'])
    if len(old)!=120 or len(completed)!=120 or [r['unit_id'] for r in old]!=[r['unit_id'] for r in completed]:
        raise ValueError('frozen 120-context inventory incomplete')
    if sum(r['overall_status']=='PASS' for r in old)!=100 or sum(r['overall_status']=='FAILED' for r in old)!=20:
        raise ValueError('original implementation statuses lost')
    if not all(r['overall_registered_claim_status']=='PASS' for r in completed):
        raise ValueError('supplementary completion failed')
    if claim=='B09':
        if sum(r['literal_constructor_claim']=='FAILED' for r in completed)!=116:
            raise ValueError('literal constructor count differs')
        return '116 literal constructor failures preserved separately from 120 completed numerical gates'
    if claim=='P11':
        from .summaries import summarise
        from .census import scientific
        rows=e.read(c['attachments']);expected=e.read(c['summaries'])
        if len(rows)!=240 or {r['unit_id'] for r in rows}!={r['unit_id'] for r in old}:
            raise ValueError('historical attachment inventory incomplete')
        if scientific(summarise(rows,120))!=scientific(expected):raise ValueError('descriptive summaries differ')
        for r in rows:
            name=c['contexts']+'/'+r['unit_id']+'/'+r['view']+'_original.jsonl'
            if sha(e.path(name))!=r['original_row_copy_sha256']:raise ValueError('verbatim attachment differs')
        return '120 original/completion records and 240 verbatim attachments; no rescoring or structural filtering'
    zeros=contexts=0
    for original,completion in zip(old,completed):
        ctx=e.read(c['contexts']+'/'+original['unit_id']+'/CONTEXT.json')
        if claim=='B10':r=recompute(ctx)
        if claim=='P03':
            from .claim_checks import pipeline
            if 'formula' not in c:raise ValueError('P03 requires the anchored archived formula input in claims.P03.formula')
            r=pipeline(ctx,e.path(c['formula']))
            stored=original['certificates']['correspondence']
            for key in ('delta_squared_exact','constructor_categorical_shape_parity','native_preparation_replay_maximum_error_exact',
                        'rounded_nonvanishing','uniform_projector_TV_bound_exact','own_input_exact_source_vs_landed_maximum_error',
                        'own_input_rounded_evaluation_error','native_numpy_vs_landed_fsum_maximum_error'):
                if r[key]!=stored[key]:raise ValueError('recomputed pipeline quantity differs: '+key)
            for key,value in r['uniform_floating_envelope'].items():
                if value!=stored['uniform_floating_envelope'][key]:raise ValueError('recomputed arithmetic accounting differs: '+key)
            if not registered_correspondence(r):raise ValueError('recomputed numerical gate failed')
        elif claim=='P10':
            checked=point_search(A,model(ctx));stored=original['certificates']['strictness']
            if checked['pair']!=stored['pair'] or checked['pairs_visited']!=stored['pairs_visited'] or checked['first_separating_readout']!=stored['first_separating_readout']:
                raise ValueError('strictness first pair/readout differs')
        elif claim=='B08':
            stored=original['certificates']['strictness'];checked=point_search(A,model(ctx))
            for key in ('pair','complete_equal_old_view','rho_left','rho_right','first_separating_readout'):
                if checked[key]!=stored[key]:raise ValueError('recomputed exact access witness differs: '+key)
            if checked['complete_equal_old_view']['precision']!='exact coefficient contract' or not Q(checked['first_separating_readout']['difference_exact']):
                raise ValueError('recomputed access witness not separated')
        elif claim=='B10':
            for field,atom,det in r['atoms']:
                if Q(det)==0:
                    block=[i for i,v in enumerate(ctx['lens'][field]) if v==atom]
                    if len(block)!=1:raise ValueError('zero-determinant atom is not a singleton')
                    w=Q(r['w'][block[0]]);trace=Q(1,32)+w*w/Q(r['s'])
                    if not 0<trace<1:raise ValueError('singular singleton is zero or a projector')
            zeros+=r['zero_atoms'];contexts+=bool(r['zero_atoms'])
    if claim=='B10':
        if (contexts,zeros)!=(20,27):raise ValueError('zero-determinant counts differ')
        return '20 contexts / 27 singleton zero-Gram-determinant atoms, independently recomputed'
    if claim=='B08':return 'recomputed 120 complete-old-view equalities, density inequalities and exact readout gaps; finite-sample/precision access not certified'
    return '120 '+('recomputed projector, preparation replay, own-input prediction, floating accounting and all registered pipeline quantities (conditional arithmetic premises)' if claim=='P03' else 'exact complete-old-view strictness witnesses')+' verified'



def artifact(e, item):
    """Yield a verified raw or chunked-zstd artifact without publishing files.

    Chunk paths remain historical identities within the explicit archive root.
    The bundled manifest binds compressed and reconstructed byte identities.
    """
    from contextlib import contextmanager
    import subprocess
    import threading
    @contextmanager
    def opened():
        if isinstance(item,str):
            path=e.path(item)
            with path.open('rb') as stream:yield stream,e.doc['files'][item],path.stat().st_size
            return
        manifest=e.read(item['manifest'])
        rows=[r for r in manifest['artifacts'] if r['archive_id']==item['archive_id']]
        if len(rows)!=1:raise ValueError('ambiguous/missing archived artifact')
        row=rows[0];paths=[]
        for chunk in row['chunks']:
            name=item['root']+'/'+chunk['path'];path=e.path(name)
            if e.doc['files'][name]!=chunk['sha256'] or path.stat().st_size!=chunk['size_bytes']:
                raise ValueError('compressed chunk commitment differs')
            paths.append(path)
        proc=subprocess.Popen(['zstd','-d','--stdout','--no-progress'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        errors=[]
        def feed():
            import hashlib
            hasher=hashlib.sha256();size=0
            try:
                for path in paths:
                    with path.open('rb') as f:
                        while block:=f.read(2**20):
                            hasher.update(block);size+=len(block);proc.stdin.write(block)
                if (hasher.hexdigest(),size)!=(row['compressed_stream']['sha256'],row['compressed_stream']['size_bytes']):
                    raise ValueError('compressed stream commitment differs')
            except Exception as exc:errors.append(exc)
            finally:proc.stdin.close()
        thread=threading.Thread(target=feed,daemon=True);thread.start()
        try:
            yield proc.stdout,row['original_sha256'],row['original_size_bytes']
            thread.join()
            if proc.wait()!=0 or errors:raise ValueError('archive decompression failed: '+str(errors)+proc.stderr.read().decode())
        finally:
            if proc.poll() is None:proc.terminate()
            proc.stdout.close();proc.wait();thread.join();proc.stderr.close()
    return opened()


def verify_artifact(e,item):
    import hashlib
    with artifact(e,item) as (stream,digest,size):
        h=hashlib.sha256();actual_size=0
        while block:=stream.read(2**20):h.update(block);actual_size+=len(block)
        if (h.hexdigest(),actual_size)!=(digest,size):raise ValueError('reconstructed artifact commitment differs')
    return digest


def historical_claim(claim,e,historical_root=None):
    if not getattr(e,'trusted',False):raise ValueError('frozen historical dispatch requires an anchored Evidence bundle')
    c=e.config(claim)
    if claim=='TB01':
        from .record_tests.verify import verify
        r=verify(test_b_inputs(e));return f"informative negative: ranks 2–4 FAIL, scope/signal PASS; {r['input_files_verified']} files, both derivations exact"
    if claim in ('P03','P10','P11','B08','B09','B10'):return census(e,c,claim)
    if claim=='B04':return no_lift(e,c)
    if claim=='B05':return sequential_boundary(e,c)
    if claim=='B07':
        m=model(e.read(c['context']));R=m.pure(0)
        a=m.probability(R,m.word(('raw_by_state','package_by_state'),(1,0))[1])
        b=m.probability(R,m.word(('package_by_state','raw_by_state'),(0,1))[1])
        if not (a.hi<b.lo or b.hi<a.lo):raise ValueError('registered order witness not separated')
        return 'registered raw1/package0 order laws differ; no contextuality inferred from disturbance'
    if claim=='B06':
        from .claim_checks import non_trace_fragment
        cert=e.read(c['certificate'])
        if 'context' not in c:raise ValueError('B06 needs the anchored original apparatus context in claims.B06.context')
        result=non_trace_fragment(model(e.read(c['context'])),cert['basis_exact'])
        if result['coordinate_determinant_exact']!=cert['coordinate_determinant_exact']:
            raise ValueError('informational completeness certificate differs')
        return ('recomputed non-PSD trace-one valuation positive on all '+str(result['events'])+
                ' finite registered events, normalized and additive by trace linearity; informationally complete basis excludes every density representation; generated-H classification UNRESOLVED')
    if claim=='B13':
        from .snapshot.return_inventory import verify_return_inventory
        keys=('inventory','selection','census_inventory')
        kwargs={key+'_path':e.path(c[key]) for key in keys}
        kwargs.update({key+'_sha256':e.doc['files'][c[key]] for key in keys})
        verify_return_inventory(data_root=e.root(c['source_root']),**kwargs)
        return '120 available rank-two contexts among 2,122, complete structural source joins checked without performance selection'
    if claim=='P12':
        from .snapshot.historical import HistoricalInputs
        from .snapshot.frozen_spec import FrozenSpec
        from .snapshot.verification import verify_units
        if not historical_root:raise ValueError('P12 additionally requires --historical-root <preserved RB1 specs/source bundle>')
        from importlib.resources import files
        anchor=json.loads(files('born_ladder').joinpath('evidence_anchor.json').read_text())
        if sha(Path(historical_root)/'manifest.json')!=anchor['historical_manifest_sha256']:
            raise ValueError('frozen historical source manifest trust anchor mismatch')
        history=HistoricalInputs(historical_root)
        for stage in ('g2a','g2c'):
            item=c[stage]
            spec=(FrozenSpec.load_g2r_g2a_replay(repo_root=e.root(c['source_root']),historical_root=history.root) if stage=='g2a'
                  else FrozenSpec.load(history.path('born_route_rebuild1_spec_v24.json'),repo_root=e.root(c['source_root']),historical_root=history.root))
            with artifact(e,item['units']) as (stream,digest,size):
                replay=verify_units(stream,spec=spec,stage=stage,expected_sha256=digest,expected_size_bytes=size)
            expected=e.read(item['verification'])
            for key in ('stage','rows','eligible','excluded','per_kind','laws_checked','maximum_value_difference','sha256','size_bytes'):
                if replay[key]!=expected[key]:raise ValueError('archived unit replay differs: '+stage+'/'+key)
            verify_artifact(e,item['evaluation'])
        return 'G2a/G2c historical evaluation receipts bound and every unit law/loss checked; population significance remains historical, not recomputed'
    if claim=='B11':
        receipt=e.read(c['receipt']);binary=e.path(c['binary'])
        if sha(binary)!=receipt['recovered']['sha256']:raise ValueError('recovered executable differs')
        if not receipt['source_build_correspondence'].startswith('NOT SEPARATELY CERTIFIED'):
            raise ValueError('source/build uncertainty was changed')
        return 'historical executable identity verified; complete source/build correspondence remains UNPROVED'
    if claim=='B01':
        roles=e.read(c['component_roles']);dispositions=e.read(c['provenance'])
        if dispositions['components']['Lueders_rule']!='IMPORTED' or dispositions['components']['full_interval_external_access']!='IMPORTED' or dispositions['new_runs']!=0:
            raise ValueError('production/import role boundary differs')
        if not all(any(row['component']==component for row in roles) for component in dispositions['components']):
            raise ValueError('component-role inventory incomplete')
        return 'hash-bound component-role/import record; adopted operations are not credited with substrate production'
    if claim=='B12':
        import hashlib
        raw=e.read(c['raw']);pkg=e.read(c['pkg']);opening=e.read(c['opening']);join=e.read(c['join'])
        key=join['complete_provenance_key']
        if (key['experiment'],key['config_or_null'],key['seed'],key['resolution'],key['step']) != ('EXP-112','A13_A11',840007,2,0):
            raise ValueError('selected RI fixture changed')
        for kind,row in [('raw',raw),('pkg',pkg)]:
            if row['not_recalculated'] is not True or not row['verbatim_JSON_value_strings']:
                raise ValueError('selected RI historical attachment changed')
            for field,value in row['field_value_sha256'].items():
                if hashlib.sha256(row['verbatim_JSON_value_strings'][field].encode()).hexdigest()!=value:
                    raise ValueError('verbatim performance field differs')
            if row['source_pointer']!=join['raw_pkg'][kind]['source']:
                raise ValueError('complete raw/package source join differs')
        if not opening['immutable_source_verification'] or not opening['no_reselection_or_scoring']:
            raise ValueError('historical opening receipt changed')
        return 'selected RI historical unit attachment bound; no population return reassigned to this unit or imported operations'
    raise ValueError('no registered historical adapter')
