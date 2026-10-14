"""Sample-free canonical and descriptive predictions and immutable commitment."""
import json
import math
import os
from pathlib import Path
from born_ladder.snapshot.rng import RNGStream
from .canonical import construct, controls
from .specification import canonical_bytes, digest

FIELDS={'identity','emitted','preparation','labels'}


def restricted_input(payload):
    """Explicit extraction: no endpoints, frequencies, losses or fitting fields."""
    result={key:payload[key] for key in sorted(FIELDS)}
    identity=result['identity']
    if not isinstance(identity,list) or len(identity)!=6:
        raise ValueError('complete six-component unit identity required')
    n=len(result['preparation'])
    if set(result['labels'])!={'raw','package'} or any(len(x)!=n for x in result['labels'].values()):
        raise ValueError('paired label dimensions differ')
    return json.loads(canonical_bytes(result))


def midpoint_uniform(word):
    if type(word) is not int or not 0<=word<2**64: raise ValueError('not a u64')
    return ((word>>12)+0.5)/2**52


def normal_matrix(stream,rank):
    values=[]; words=[]
    while len(values)<rank*rank:
        a,b=stream.word(),stream.word(); words.extend([a,b])
        u,v=midpoint_uniform(a),midpoint_uniform(b)
        radius=math.sqrt(-2*math.log(u)); angle=2*math.pi*v
        values.extend([radius*math.cos(angle),radius*math.sin(angle)])
    return [values[i*rank:(i+1)*rank] for i in range(rank)],words


def orientation_law(B,rotation,p):
    n=len(B); rank=len(B[0]); roots=[math.sqrt(x) for x in p]
    z=[math.fsum(B[i][h]*roots[i] for i in range(n)) for h in range(rank)]
    norm=math.sqrt(math.fsum(x*x for x in z)); a=[x/norm for x in z]
    rotated=[[math.fsum(B[i][h]*rotation[h][j] for h in range(rank)) for j in range(rank)] for i in range(n)]
    rotated_a=[math.fsum(rotation[h][j]*a[h] for h in range(rank)) for j in range(rank)]
    q=[math.fsum(rotated[i][h]*rotated[i][h]*rotated_a[h]*rotated_a[h] for h in range(rank)) for i in range(n)]
    if any(not math.isfinite(x) or x< -1e-12 for x in q) or abs(math.fsum(q)-1)>1e-10:
        raise ValueError('orientation probability/mass gate')
    return q


def orientations(spec,evaluation,restricted,certificate,*,qr=None):
    import numpy as np
    if qr is None: qr=lambda G:np.linalg.qr(G,mode='reduced')
    count=spec.science['orientation_sensitivity']['random_orientation_count']
    if certificate['status']!='certified':
        return [{'slot':k,'status':'unresolved','attempts':[], 'reason':'canonical unavailable'} for k in range(count)]
    B=np.asarray(certificate['basis_columns'],dtype=np.float64).T.tolist(); rank=len(B[0]); rows=[]
    for slot in range(count):
        attempts=[]
        for attempt in range(8):
            key=spec.orientation_key(evaluation,restricted['identity'],digest(restricted),slot,attempt)
            stream=RNGStream(key); G,words=normal_matrix(stream,rank)
            detail={'attempt':attempt,'master_key':key.hex(),'stream_counter':stream.counter,
                    'remaining_words':len(stream._buffer),'words':words,'normal_matrix':G}
            try:
                Q,R=qr(np.asarray(G)); Q=np.asarray(Q); R=np.asarray(R)
                if Q.shape!=(rank,rank) or R.shape!=(rank,rank): raise ValueError('QR dimensions')
                if not np.isfinite(Q).all() or not np.isfinite(R).all() or any(R[j,j]==0 for j in range(rank)):
                    raise ValueError('zero/nonfinite QR pivot')
                signs=[1 if R[j,j]>0 else -1 for j in range(rank)]
                Q=Q*np.asarray(signs)[None,:]; R=np.asarray(signs)[:,None]*R
                law=orientation_law(B,Q.tolist(),restricted['preparation'])
                detail.update(status='complete',orthogonal_matrix=Q.tolist(),triangular_matrix=R.tolist(),signs=signs)
                attempts.append(detail); rows.append({'slot':slot,'status':'complete','attempts':attempts,'q':law})
                break
            except (ValueError, ArithmeticError, np.linalg.LinAlgError) as error:
                detail.update(status='rejected',reason=str(error)); attempts.append(detail)
        else: rows.append({'slot':slot,'status':'unresolved','attempts':attempts,'reason':'eight attempts exhausted'})
    return rows


def legacy_laws(spec,restricted):
    """One historical implementation; the caller must have passed worker checks."""
    import numpy as np
    from born_ladder.snapshot.g2a import _oriented_basis
    from born_ladder.snapshot.universal_shapes import _formula_contract,_recomputed_laws
    from born_ladder.reproduction.specification import PublicSpecification
    p=restricted['preparation']; born={'p_theory':p,'sym_eigvec_basis':restricted['emitted']}
    basis=_oriented_basis(born)
    coefficients=(np.asarray(basis['emitted_basis']).T@np.sqrt(np.asarray(p))).tolist()
    formulas=_formula_contract(PublicSpecification(spec.directory,'v8'))
    predictions,masses,diagnostics=_recomputed_laws({'unrounded_p_full':p,'basis_and_projector_inputs':basis,
            'spectral_coefficients':{'values':coefficients,'mode_ids':['M'+str(i) for i in range(len(coefficients))]}},formulas)
    return basis,predictions,masses,diagnostics,coefficients


def predict(spec,evaluation,payload,*,runtime_sha256=None):
    restricted=restricted_input(payload)
    cert=construct(restricted['emitted'],restricted['preparation'],
                   refinement=tuple(spec.science['canonical_diagonal']['rounding']['refinement_bits']))
    from .checker import check_certificate,check_controls
    check_certificate(restricted['emitted'],restricted['preparation'],cert,
                      refinement=tuple(spec.science['canonical_diagonal']['rounding']['refinement_bits']))
    basis,laws,masses,diagnostics,coefficients=legacy_laws(spec,restricted)
    checks=controls(cert,basis['emitted_basis'],laws['q_full'],basis['projector'])
    check_controls(cert,basis['emitted_basis'],laws['q_full'],checks,basis['projector'])
    original_diag=laws.pop('q_diag')
    if cert['status']=='certified': laws['q_diag_canonical']=cert['q_diag_canonical']
    return {'schema':'born_v25_predictions_v1','scientific_digest':spec.digest,'evaluation':evaluation,
            'runtime_sha256':runtime_sha256,
            'restricted':restricted,'restricted_sha256':digest(restricted),
            'canonical_certificate':cert,'canonical_controls':checks,'predictions':laws,
            'legacy':{'basis':basis,'masses':masses,'diagnostics':diagnostics,'coefficients':coefficients},
            'orientations':orientations(spec,evaluation,restricted,cert),
            'historical_svd_reference':{'status':'complete','q':original_diag,
                                      'scope':'fresh v25 or explicitly synthetic only; descriptive'}}


def commit(directory,prediction):
    directory=Path(directory); directory.mkdir(parents=True,exist_ok=True)
    raw=canonical_bytes(prediction); file=directory/'prediction.json'
    # Exclusive create: a completed prediction never changes. A killed partial
    # write has no seal and must be a new attempt, never interpreted as complete.
    with file.open('xb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    seal={'schema':'born_v25_prediction_commitment_v1','prediction_sha256':digest(prediction),
          'restricted_sha256':prediction['restricted_sha256'],'scientific_digest':prediction['scientific_digest']}
    with (directory/'commitment.json').open('x') as stream:
        json.dump(seal,stream,sort_keys=True); stream.flush(); os.fsync(stream.fileno())
    return seal


def read_committed(directory):
    directory=Path(directory)
    seal=json.loads((directory/'commitment.json').read_bytes())
    prediction=json.loads((directory/'prediction.json').read_bytes())
    if seal['prediction_sha256']!=digest(prediction) or seal['restricted_sha256']!=digest(prediction['restricted']):
        raise ValueError('prediction commitment differs')
    if seal['scientific_digest']!=prediction['scientific_digest']:
        raise ValueError('prediction scientific commitment differs')
    return prediction,seal
