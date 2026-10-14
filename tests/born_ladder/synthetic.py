"""Deterministic non-empirical controls, independent exact fixture construction.

Compact descriptors are committed instead of huge rational matrices. No archived
mode, kernel, preparation, loss or measured outcome is copied into these controls.
"""
from fractions import Fraction as F
import json
from pathlib import Path
from born_ladder.independent import recompute


def fixture(name='ordinary'):
    descriptor = json.loads((Path(__file__).with_name('fixtures') / (name + '.json')).read_text())
    assert descriptor['historical_data'] is False
    n = 32
    w = [F(2*i-31) for i in range(n)]
    if name == 'tiny':
        w[1] = w[0] + F(1, 2**250)
        mean = sum(w)/n
        w = [(x-mean)/2**540 for x in w]
    s = sum(x*x for x in w)
    P = [[F(1,n)+a*b/s for b in w] for a in w]
    K = [[F(3,4)*int(i==j)+F(1,4*n) for j in range(n)] for i in range(n)]
    raw = [int(i != 31) for i in range(n)]
    pkg = [int(i >= 16) for i in range(n)]
    labels = sorted(set(zip(raw,pkg)))
    joint = [labels.index(x) for x in zip(raw,pkg)]
    context = {'identity': {'unit_id': 'synthetic_'+name, 'source': 'non-empirical control'},
               'lens': dict(raw_by_state=raw, package_by_state=pkg, joint_by_state=joint),
               'kernel': [[float(x) for x in row] for row in K],
               'born': {'sym_eigvec_basis': [list(map(str,w))], 'starts': [0], 'tau': 0,
                        'p_theory': [float(i==0) for i in range(n)]},
               'exact': {'w':list(map(str,w)), 's':str(s), 'P':[[str(x) for x in row] for row in P]},
               'archived_unit_structural': {'raw': {'basis_and_projector_inputs': {'projector':[[float(x) for x in row] for row in P]}}}}
    r = recompute(context)
    assert r['witness']['pair'] == [0,1] and r['witness']['context'] == 'raw_by_state' and r['witness']['atom'] == 0
    # Certificate expectations follow exact two-coordinate projection identities.
    def rho(i):
        a,b=F(1,n),w[i]/s;den=n*a*a+s*b*b
        return [[a*a*n/den,a*b*s/den],[a*b*n/den,b*b*s/den]]
    def read(i):
        return sum((1+n*w[i]*w[j]/s)**2 for j in [31])/(n*(1+n*w[i]**2/s))
    # Complete old view generated from the synthetic descriptor, no hidden fields.
    view={'context':context['identity'],'preparation_receipt':{'class':'Audit A anonymous simplex mathematical source','recipe_id':None},
          'actual_passive_laws':{f:{str(g):str(int(q[0]==g)) for g in sorted(set(q))} for f,q in context['lens'].items()},
          't':0,'lag':8,'history_horizons':[0],'coefficient_history_arrays':None,'acquired_passive_prefix':[],
          'commands':[],'acquired_upper_outcomes':[],'status':'PREPARATION_ENTRY','precision':'exact coefficient contract',
          'source_policy':'fixed amended full simplex, no sampled preparation population'}
    d=read(0)-read(1)
    strict={'status':'PASS','witness_type':'CERTIFIED STRICT REFINEMENT','pairs_visited':1,'pair':[0,1],
            'preparations':{'p':[str(int(i==0)) for i in range(n)],'p_prime':[str(int(i==1)) for i in range(n)]},
            'complete_equal_old_view':view,'all_old_fields_exact_equal':True,'rho_left':[[str(x) for x in row] for row in rho(0)],
            'rho_right':[[str(x) for x in row] for row in rho(1)],'density_exact_inequality':True,
            'first_separating_readout':{'context':'raw_by_state','numeric_atom':0,'left_exact':str(read(0)),
                                      'right_exact':str(read(1)),'difference_exact':str(d),'difference_display':float(d)},
            'point_identifying_receipt_rejects_witness':True}
    correspondence={'status':'FAILED' if name=='basis' else 'PASS','constructor_maximum_difference':'1/1000' if name=='basis' else '0',
                    'constructor_literal_bit_equality_status':'FAILED' if name=='basis' else 'PASS',
                    'uniform_projector_TV_bound_exact':'1/100000000000000' , 'delta_squared_exact':r['delta_squared_exact'],
                    'constructor_categorical_shape_parity':True,'rounded_nonvanishing':True,
                    'native_preparation_replay_maximum_error_exact':'0','own_input_exact_source_vs_landed_maximum_error':'0',
                    'own_input_rounded_evaluation_error':'0','native_numpy_vs_landed_fsum_maximum_error':'0'}
    cp={'status':'FAILED','error_type':'OverflowError'} if name=='tiny' else {'status':'PASS'}
    reviewed={'unit_id':'synthetic_'+name, 'overall_status':'FAILED' if name in ('basis','tiny') else 'PASS',
              'certificates':{'correspondence':correspondence,'strictness':strict,'C_premises':cp},
              'failures':[],'synthetic_control':True}
    return {'context':context,'reviewed_certificates':reviewed,'completion':{'registered_numerical_gate_status':'PASS'},'synthetic_control':True}
