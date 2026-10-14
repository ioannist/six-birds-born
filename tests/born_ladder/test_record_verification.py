"""Score-only gates, corruption refusal and optional explicit local archive replay."""
import ast
import hashlib
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import numpy as np
import pytest

from born_ladder.record_tests import scorer, scoring, independent
from born_ladder.record_tests.inputs import Inputs, safe_path
from born_ladder.record_tests.verify import differences, verify


def test_frozen_tail_ties_holm_and_bound():
    x = np.ones(20)
    indices = np.tile(np.arange(20), (199, 1))
    assert scorer.centered_p(x, 1., indices) == independent.tail(x, 1., indices) == 1.
    assert scorer.centered_p(x, .99, indices) == independent.tail(x, .99, indices) == .005
    assert scorer.lower_bound(x, indices, 6) == independent.bound(x, indices, 6)
    p = dict(D2=.001, G2=.011, D3=.02, G3=.2, D4=.2, G4=1.)
    result = scorer.holm(p, 'primary')
    assert result['ordered'] == ['D2', 'G2', 'D3', 'G3', 'D4', 'G4']
    assert result['reject'] == dict(D2=True, G2=False, D3=False, G3=False, D4=False, G4=False)
    assert result['adjusted']['G2'] == .05499999999999999


def test_scope_uses_mean_not_max_and_no_context_removed():
    values = {'a': [.012] * 96, 'b': [.006] * 96}
    result = scorer.scope_audit(values, {2: ['a', 'b']})[2]
    assert result['status'] == 'in_scope' and result['failing_fraction'] == .5
    assert np.isclose(result['mean_C95'], .009, rtol=0, atol=1e-17) and result['max_C95'] == .012
    assert set(result['context_C95']) == {'a', 'b'}
    assert scorer.nearest_95(range(96)) == 91


def test_rank_pass_requires_all_gates():
    b = dict(D=.02, G=.02, R=.001, O=.02)
    assert scoring.rank_claim(True, True, .1, .01, b)
    for key, val in [('D', .01), ('G', .01), ('R', .01), ('O', .01)]:
        assert not scoring.rank_claim(True, True, .1, .01, {**b, key: val})
    assert not scoring.rank_claim(True, True, .01, .01, b)
    assert not scoring.rank_claim(True, False, .1, .01, b)


def test_production_and_independent_synthetic_case():
    # Two states, twelve identical preparations; no fit or random data production.
    h = {'kernel': [[.7, .3], [.2, .8]],
         'recipes': [{'states': [0], 'weights_num': [1], 'denominator': 1}] * 60}
    c = {'joint_by_state': [0, 1], 'alphabet_raw_package': [[0, 0], [1, 1]]}
    e = dict(exp='fixture', config='fixture', k=2, step_index=0, map_sha256='fixture', m=2, h_c=1)
    laws = scoring.oracle_laws(h, c, 1)
    p = {'rank': 2, 'selectors': {}, 'predictions': {name: laws.tolist() for name in ['square', 'selected_classical', 'diagonal', 'ed2', 'selected_order']}}
    labels = np.zeros((20, 12, 32, 8), dtype=int)
    contrasts, report = scoring.evaluate_context(p, labels, laws)
    alt = independent.reconstruct_case(e, p, labels, h, c, [.003] * 96)
    assert all(np.array_equal(contrasts[k], alt['contrasts'][k]) for k in 'DGRO')
    assert scoring.signal([laws])[0] == alt['signal']
    assert report['models']['square']['expected_excess'] < 1e-14
    rows = [{'id': 'fixture', 'rank': r, 'laws': laws, 'contrasts': contrasts, 'test_C_values': [.003] * 96} for r in (2, 3, 4)]
    alt_rows = [{**alt, 'id': 'fixture', 'rank': r} for r in (2, 3, 4)]
    indices = {f: np.tile(np.arange(20), (999, 1)) for f in ('primary', 'reversal', 'order')}
    a = scoring.campaign(rows, dict.fromkeys((2, 3, 4), .01), indices)
    b = independent.reconstruct(alt_rows, dict.fromkeys((2, 3, 4), .01), indices)
    assert differences(a, b) == 0


def test_input_receipt_missing_altered_and_escape_refused(tmp_path):
    with pytest.raises(FileNotFoundError):
        Inputs(tmp_path/'missing', '0'*64, sealed_root=tmp_path, opened_root=tmp_path, certification_root=tmp_path)
    p = tmp_path/'receipt.json'; p.write_text('{}')
    with pytest.raises(ValueError, match='hash mismatch'):
        Inputs(p, '0'*64, sealed_root=tmp_path, opened_root=tmp_path, certification_root=tmp_path)
    with pytest.raises(ValueError, match='escapes'):
        safe_path(tmp_path, '../outside')
    original = tmp_path/'row'; original.write_text('original')
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    original.write_text('altered')
    receipt = {'schema': 'test_b_score_inputs_v1', 'files': {'p5': {'row': digest}, 'p6': {}, 'cert': {}}}
    p.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match='committed input differs'):
        Inputs(p, hashlib.sha256(p.read_bytes()).hexdigest(), sealed_root=tmp_path, opened_root=tmp_path, certification_root=tmp_path)


SCORE_ONLY_MODULES = {'scorer', 'scoring', 'inputs', 'independent', 'verify'}
PRODUCTION_MODULES = {'estimators', 'generators', 'generators_v6', 'generation_scorer',
    'test_b_census', 'test_b_census_v6', 'record_view_v6', 'scorer_v6',
    'cert_v6', 'real_v6', 'fresh_v6', 'workers', 'erasure'}


def _assert_score_only_source(text):
    tree = ast.parse(text)
    forbidden = PRODUCTION_MODULES | {'torch', 'scipy', 'sampler', 'sampling', 'fitting'}
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):
            assert all(not set(alias.name.split('.')) & forbidden for alias in node.names)
        elif isinstance(node,ast.ImportFrom):
            assert not set((node.module or '').split('.')) & forbidden
            assert not {alias.name for alias in node.names} & forbidden
        elif isinstance(node,ast.Call):
            if isinstance(node.func,ast.Attribute):
                assert node.func.attr not in {'write', 'write_text', 'write_bytes', 'mkdir',
                    'unlink', 'rename', 'save', 'savez', 'dump', 'tofile', 'touch',
                    'truncate', 'fit', 'sample'}
            is_open = ((isinstance(node.func,ast.Name) and node.func.id=='open')
                       or (isinstance(node.func,ast.Attribute) and node.func.attr=='open'))
            if is_open:
                positional = 1 if isinstance(node.func,ast.Name) else 0
                mode = next((k.value for k in node.keywords if k.arg=='mode'),None)
                if mode is None and len(node.args)>positional:mode=node.args[positional]
                if mode is not None:
                    assert isinstance(mode,ast.Constant) and isinstance(mode.value,str)
                    assert not set(mode.value) & set('wax+')
            if isinstance(node.func,ast.Attribute):
                assert 'random' not in ast.unparse(node.func).split('.')
    return tree


def test_public_record_code_has_no_fit_sampler_writer_or_torch():
    """The score-only dependency graph is separate from production modules."""
    root = Path('src/born_ladder/record_tests')
    assert not SCORE_ONLY_MODULES & PRODUCTION_MODULES
    assert {p.stem for p in root.glob('*.py')} == SCORE_ONLY_MODULES | PRODUCTION_MODULES | {'__init__'}
    for name in SCORE_ONLY_MODULES | {'__init__'}:
        _assert_score_only_source((root/(name+'.py')).read_text())
    # Seal-time diagnostic production is outside the score-only graph, but
    # this helper itself performs only arithmetic (no fit, sampler or write).
    _assert_score_only_source((root/'erasure.py').read_text())
    alt = ast.parse((root/'independent.py').read_text())
    assert not any(isinstance(n,ast.ImportFrom) and n.level for n in ast.walk(alt))
    for name in ('linear_helpers','record_helpers'):
        text = (Path('src/born_ladder/snapshot')/(name+'.py')).read_text()
        assert '_RecordingRNGStream' not in text and '_CanonicalJsonlStage' not in text


@pytest.mark.parametrize('source',[
    'import torch', 'from . import estimators', 'from .generators import draw',
    'from .erasure import diagnostics',
    'from pathlib import Path\nPath("output").write_text("value")',
    'open("output", "w")', 'import numpy as np\nnp.random.default_rng()',
])
def test_score_only_contract_rejects_production_dependencies_and_writes(source):
    with pytest.raises(AssertionError):_assert_score_only_source(source)


def test_tb01_dispatch_without_fitting_extra():
    # Block optional dependencies and every producer module in a fresh process.
    # Exercise actual TB01 dispatch; supply the already-tested synthetic score
    # inputs at the evidence boundary, without needing the retained archive.
    script = textwrap.dedent("""
        import importlib.abc, importlib.util, sys
        assert importlib.util.find_spec('torch') is None
        assert importlib.util.find_spec('scipy') is None
        class NoProduction(importlib.abc.MetaPathFinder):
            def find_spec(self,fullname,path=None,target=None):
                if fullname.split('.')[0] in {'torch','scipy'}:
                    raise AssertionError('fitting dependency imported: '+fullname)
                if fullname.startswith('born_ladder.record_tests.') and fullname.rsplit('.',1)[-1] not in {'scorer','scoring','inputs','independent','verify'}:
                    raise AssertionError('producer imported: '+fullname)
        sys.meta_path.insert(0,NoProduction())
        import numpy as np
        import born_ladder.claims as C
        from born_ladder.__main__ import verify_claim
        from born_ladder.record_tests import scoring, independent
        from born_ladder.record_tests.verify import verify as actual_verify
        laws = np.zeros((12,8,2))
        for i in range(12):laws[i,:,i%2]=1
        labels = np.zeros((20,12,32,8),dtype=int)
        predictions = {'rank':2,'selectors':{},'predictions':{
            name:laws.tolist() for name in ['square','selected_classical','diagonal','ed2','ed3','ed4','selected_order']}}
        contrasts,report = scoring.evaluate_context(predictions,labels,laws)
        header = {'kernel':[[1.,0.],[0.,1.]],'recipes':[
            {'states':[i%2],'weights_num':[1],'denominator':1} for i in range(60)]}
        context = {'joint_by_state':[0,1],'alphabet_raw_package':[[0,0],[1,1]]}
        c_values = [.003]*96
        entries = [dict(exp='synthetic',config='synthetic',k=2,step_index=i,
                   map_sha256='synthetic',m=2,h_c=1) for i,rank in enumerate((2,3,4))]
        rows=[]
        stored=[]
        for entry,rank in zip(entries,(2,3,4)):
            rows.append({'id':__import__('json').dumps((entry['exp'],entry['config'],entry['k'],entry['step_index'],entry['map_sha256']),separators=(',',':')),
                         'rank':rank,'laws':laws,'contrasts':contrasts,'test_C_values':c_values})
            stored.append({'context':entry,'rank':rank,**report})
        indices={f:np.tile(np.arange(20),(999,1)) for f in ('primary','reversal','order')}
        verdict=scoring.campaign(rows,dict.fromkeys((2,3,4),.01),indices)
        verdict['contexts']=stored
        class ScoreInputs:
            verified=[]
            files={'p6':{'verdict.json':'synthetic'}}
            def read(self,root,name):
                return verdict if name=='verdict.json' else {'margins':{'2':.01,'3':.01,'4':.01}}
            def indices(self):return indices
            def cases(self):
                for entry,rank in zip(entries,(2,3,4)):
                    yield entry,{**predictions,'rank':rank},labels,header,context,c_values
        class SyntheticEvidence:
            trusted=True
            def __init__(self,*args):pass
            def config(self,claim):return {}
        C.Evidence=SyntheticEvidence
        C.test_b_inputs=lambda evidence:ScoreInputs()
        result=verify_claim('TB01',data='synthetic-evidence-boundary')
        assert 'informative negative' in result
        assert not any(name.startswith(('torch','scipy')) for name in sys.modules)
        print('TB01 score-only synthetic dispatch passed without fitting extra')
    """)
    run = subprocess.run([sys.executable,'-c',script],capture_output=True,text=True)
    assert run.returncode==0,run.stdout+run.stderr


@pytest.mark.data
def test_reviewed_archived_negative_and_independent_values():
    from born_ladder.claims import Evidence, test_b_inputs
    inputs = test_b_inputs(Evidence(os.environ['BORN_LADDER_DATA']))
    result = verify(inputs)
    assert result['verdict']['category'] == 'FAIL'
    # Archived independent reconstruction table, at displayed precision.
    reviewed = {
        2: {'D': (-.001960839, -.00325545, 1., 1.), 'G': (.009490026, .00876602, .961480193, 1.),
            'O': (.036298032, .03364146, .000004999975, .000014999925), 'R': (.008654983, .00989517, .010849946, .032549837)},
        3: {'D': (-.006849931, -.00824288, 1., 1.), 'G': (.002974390, .00247016, 1., 1.),
            'O': (.064635479, .06159593, .000004999975, .000014999925), 'R': (.009558258, .01079262, .227203864, .227203864)},
        4: {'D': (-.005826496, -.00710443, 1., 1.), 'G': (-.000565124, -.00138144, 1., 1.),
            'O': (.049617844, .04709598, .000004999975, .000014999925), 'R': (.009067376, .01012861, .032104839, .064209679)}}
    for r, contrasts in reviewed.items():
        rank = result['independent_verdict']['ranks'][str(r)]
        assert rank['status'] == 'FAIL' and rank['gates']['scope'] and rank['gates']['signal']
        for letter, values in contrasts.items():
            f = 'primary' if letter in 'DG' else 'order' if letter == 'O' else 'reversal'
            row = result['independent_verdict']['inference'][f]; slot = f'{letter}{r}'
            actual = (row['estimates'][slot], row['bounds'][slot], row['p_raw'][slot], row['holm']['adjusted'][slot])
            assert np.allclose(actual, values, rtol=0, atol=5.1e-10)
    assert result['comparison']['inference_exact']
