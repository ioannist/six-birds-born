"""Targeted P1 acceptance: recovery, scientific namespaces and retained probes."""
import ast
import hashlib
import importlib
import json
import os
import re
import copy
import shutil
from pathlib import Path

import numpy as np
import pytest

from born_ladder.reproduction.specification import PublicSpecification, canonical_json_bytes
from born_ladder.snapshot.rng import RNGStream, key_deriver
from born_ladder.snapshot.errors import SpecMismatch

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO/'specifications'
REFERENCE = json.loads((Path(__file__).parent/'fixtures/e2e_rng_reference.json').read_text())


class _ScientificImports(ast.NodeTransformer):
    def visit_FunctionDef(self, node):
        node = copy.deepcopy(node)
        # P5 adds only an explicit reduced-cohort I/O argument. Normalize its
        # registered default back to 140; all numerical body statements remain
        # checked against the recovered historical fingerprint.
        if node.name == 'run' and node.args.args and node.args.args[-1].arg == 'expected_units':
            assert node.args.defaults[-1].value == 140
            node.args.args.pop(); node.args.defaults.pop()
            class RegisteredCount(ast.NodeTransformer):
                def visit_Name(self, part):
                    return ast.copy_location(ast.Constant(140), part) if part.id == 'expected_units' else part
                def visit_JoinedStr(self, part):
                    if ast.unparse(part).startswith("f'expected exactly "):
                        return ast.JoinedStr(values=[ast.Constant('expected exactly 140 frozen audit headers, got '),
                                                    copy.deepcopy(part.values[-1])])
                    return self.generic_visit(part)
            node = RegisteredCount().visit(node)
        return self.generic_visit(node)

    def visit_ImportFrom(self, node):
        node = copy.deepcopy(node)
        if node.module:
            node.module = node.module.replace('scripts.rebuild1.', 'born_ladder.snapshot.')
            node.module = node.module.replace('born_ladder.reproduction.predictive.', 'born_ladder.snapshot.')
        return node

    def visit_Constant(self, node):
        node = copy.deepcopy(node)
        if isinstance(node.value, str):
            node.value = node.value.replace('ledger', 'record')
        return node


def test_recovered_scientific_ast_fingerprints():
    reference = json.loads((Path(__file__).parent/'fixtures/e2e_source_equivalence.json').read_text())
    cache = {}
    checked = 0
    for module in reference['modules']:
        path = module['public_module']
        if path not in cache:
            cache[path] = {n.name:n for n in ast.parse((REPO/path).read_text()).body
                           if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
        for name, definition in module['definitions'].items():
            components = name.split('.')
            original_node = cache[path][components[0]]
            for component in components[1:]:
                original_node = next(n for n in original_node.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name == component)
            node = _ScientificImports().visit(copy.deepcopy(original_node))
            refactor=definition.get('refactor')
            if refactor:
                assert (path,name)==('src/born_ladder/record_tests/real_v6.py','erasure_not_computed')
                retained=_ScientificImports().visit(ast.parse(refactor['original_source']).body[0])
                assert hashlib.sha256(ast.dump(retained,include_attributes=False).encode()).hexdigest()==definition['normalized_ast_sha256']
                for helper_path,definitions in refactor['current_definitions'].items():
                    helpers={n.name:n for n in ast.parse((REPO/helper_path).read_text()).body if isinstance(n,ast.FunctionDef)}
                    for helper,digest in definitions.items():
                        assert hashlib.sha256(ast.dump(helpers[helper],include_attributes=False).encode()).hexdigest()==digest
            else:
                assert hashlib.sha256(ast.dump(node,include_attributes=False).encode()).hexdigest() == definition['normalized_ast_sha256']
            checked += 1
    assert checked >= 500


def test_recovery_lists_match_final_ast():
    for row in json.loads((SPEC/'source_recovery.json').read_text())['modules']:
        assert set(row) == {'original','original_sha256','public','classification'}
        assert not row['original'].startswith('scratch/')
        classification = row['classification']
        modules = row['public'] if isinstance(row['public'],list) else [row['public']]
        actual = {n.name for module in modules for n in ast.parse((REPO/module).read_text()).body
                  if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
        unchanged = set(classification['unchanged_definitions'])
        reused = set(classification['reused_definitions'])
        removed = set(classification['removed_process_definitions'])
        assert unchanged | reused <= actual
        assert not removed & actual
        assert not (unchanged | reused) & removed


def test_readable_specification_values_match_original_fingerprints():
    reference = json.loads((Path(__file__).parent/'fixtures/e2e_spec_value_reference.json').read_text())
    checked = 0
    for version in ('v8','v21','v23','v24'):
        spec = PublicSpecification(SPEC,version)
        for row in reference['rows']:
            if 'v'+str(row['version']) != version:
                continue
            pointer,expected = row['pointer'],row['published_value_sha256']
            encoded = json.dumps(spec.get(pointer),sort_keys=True,separators=(',',':')).encode()
            assert hashlib.sha256(encoded).hexdigest() == expected,(version,pointer)
            checked += 1
        text = (SPEC/('predictive_'+version+'.json')).read_text()
        assert '$scientific_ref' not in text
        assert '"grid"' in text and '"rng"' in text
    assert checked == 103
    assert not list(SPEC.glob('scientific_values_*.json'))


def test_shared_sections_match_prior_values_and_sharing_catalog():
    manifest = json.loads((SPEC/'predictive.json').read_text())
    references = []
    for version,entry in manifest['versions'].items():
        spec = PublicSpecification(SPEC,version)
        for pointer,expected in entry['scientific_value_sha256'].items():
            raw = json.dumps(spec.get(pointer),sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
            assert hashlib.sha256(raw).hexdigest() == expected,(version,pointer)
        index = json.loads((SPEC/entry['section_index']).read_text())
        references.extend((version,row) for row in index['sections'])
    assert all(row['encoding']=='json' and row['file'].endswith('.json') for _,row in references)
    assert not list(SPEC.rglob('*.gz'))
    catalog = json.loads((SPEC/'shared_sections/index.json').read_text())
    listed = {row['file']:row for row in catalog['sections']}
    assert set(listed) == {row['file'] for _,row in references}
    for file,entry in listed.items():
        uses = {(version,row['pointer']) for version,row in references if row['file']==file}
        assert uses == {(version,pointer) for version,pointers in entry['versions'].items() for pointer in pointers}
        assert {row['scientific_value_sha256'] for _,row in references if row['file']==file} == {entry['scientific_value_sha256']}
        # All versions resolve the same directly readable bytes, not a runtime
        # regeneration or a compressed table. The loader checks the value hash.
        text = (SPEC/file).read_text()
        assert hashlib.sha256(text.encode()).hexdigest()==entry['file_sha256']
        assert text == json.dumps(json.loads(text),indent=2,ensure_ascii=False)+'\n'
    reference = json.loads((Path(__file__).parent/'fixtures/e2e_spec_value_reference.json').read_text())
    for version,row in references:
        # Complete registered scientific sections, with no size-based splitting
        # into expression fragments or numbered argument files.
        assert row['pointer'] in {r['pointer'] for r in reference['rows'] if 'v'+str(r['version'])==version}
    assert len(listed) < len(references)


@pytest.mark.parametrize('section_kind',['ordinary','expression'])
def test_shared_section_corruption_is_rejected(tmp_path,section_kind):
    clone = tmp_path/'specifications'
    shutil.copytree(SPEC,clone)
    manifest = json.loads((clone/'predictive.json').read_text())
    index = json.loads((clone/manifest['versions']['v24']['section_index']).read_text())
    row = next(row for row in index['sections'] if (row['pointer']=='/completeness/g2c_raw_stdout_derivation') == (section_kind=='expression'))
    file = clone/row['file']
    raw = b'{"corrupted":true}\n'
    file.write_bytes(raw)
    with pytest.raises(SpecMismatch,match='shared scientific section hash differs'):
        PublicSpecification(clone,'v24')


def test_single_predictive_implementation():
    duplicate_names = {'artifact_paths','collector_structural','completeness','evidence',
        'g2a','g2c_collector_structural','g2c_controls','g2c_evaluate',
        'g2c_rotation_certificate','g2c_units','identities','inventory','provenance',
        'rng','runner_structural','status','universal_shapes','frozen_spec','evaluate_g2c_campaign'}
    root = REPO/'src/born_ladder/reproduction/predictive'
    assert all(not (root/(name+'.py')).exists() for name in duplicate_names)
    from born_ladder.reproduction.predictive import g2c_campaign, g2c_entry
    from born_ladder.snapshot import g2c_evaluate, g2c_units, g2a
    assert g2c_entry.evaluate_g2c_records is g2c_evaluate.evaluate_g2c_records
    assert g2c_entry.derive_sealed_g2c_unit_drafts is g2c_units.derive_sealed_g2c_unit_drafts
    from born_ladder.reproduction.predictive import evaluate_g2a_campaign
    assert evaluate_g2a_campaign.evaluate_g2a is g2a.evaluate_g2a


def test_public_contracts_and_source_namespace():
    for version in ('v8','v21','v23','v24'):
        spec=PublicSpecification(SPEC,version)
        assert len(spec.get('/rng/algorithms/bootstrap/key_fields'))==5
        assert spec.get('/inference/bootstrap/replicates')==20000
    spec=PublicSpecification(SPEC,'v24')
    assert spec._g2c_source_spec.scientific_rng_identity==PublicSpecification(SPEC,'v21').scientific_rng_identity
    assert canonical_json_bytes({'x':1})==b'{"x":1}\n'
    with pytest.raises(SpecMismatch,match='not published'):
        spec.get('/identity/attestation')


def test_retained_g2c_bootstrap_bytes():
    spec=PublicSpecification(SPEC,'v24')._g2c_source_spec
    ref=REFERENCE['g2c']
    key=key_deriver(spec)('bootstrap',{'stage_id':'g2c_v2',
        'statistic_id':'paired_kinds_sources_metrics','replicate_index':0})
    assert key.hex()==ref['audit']['master_key_sha256']
    stream=RNGStream(key)
    result=np.array([stream.unbiased_index(20) for _ in range(20)],dtype='<u8')
    expected=np.asarray(ref['membership']['sampled_seed_indices'],dtype='<u8')
    assert result.tobytes()==expected.tobytes()
    assert stream.counter-1==ref['audit']['highest_counter']
    # The public-file digest is intentionally a different namespace: using it
    # would silently change the scientific draws and must fail this comparison.
    altered=PublicSpecification(SPEC,'v21')
    altered.attestation.json_sha256=altered.public_manifest_sha256
    assert key_deriver(altered)('bootstrap',{'stage_id':'g2c_v2',
        'statistic_id':'paired_kinds_sources_metrics','replicate_index':0})!=key


@pytest.mark.parametrize('family',['primary','reversal','order'])
def test_retained_test_b_bootstrap_prefix_bytes(family):
    # Recompute the persisted prefix by the frozen rejection rule, without a
    # population statistic or a reduced-budget scientific claim.
    identity=json.loads((SPEC/'test_b.json').read_text())['inference_rng_identity']
    result=np.empty((64,20),dtype=np.uint8)
    for k in range(64):
        for i in range(20):
            z=0
            while True:
                key=f'TestB/v6/bootstrap/{identity}/{family}/{k}/{i}/{z}'
                x=int.from_bytes(hashlib.sha256(key.encode('ascii')).digest()[:8],'little')
                if x<((1<<64)//20)*20:
                    result[k,i]=x%20;break
                z+=1
    ref=REFERENCE['test_b'][family]
    assert result.tobytes()==np.asarray(ref['rows'],dtype=np.uint8).tobytes()
    assert hashlib.sha256(result.tobytes()).hexdigest()==ref['bytes_sha256']


_PRIVATE_ABSOLUTE_PATH = re.compile(r'(?<![A-Za-z0-9])/(?:home|mnt|root|media)/')


def _assert_public_text_hygiene(path, text):
    assert not _PRIVATE_ABSOLUTE_PATH.search(text), path


def test_public_modules_have_no_private_root_literals():
    modules = json.loads((SPEC/'source_recovery.json').read_text())['modules']
    for row in modules:
        paths = row['public'] if isinstance(row['public'],list) else [row['public']]
        tree = ast.Module(body=[n for path in paths for n in ast.parse((REPO/path).read_text()).body],type_ignores=[])
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='Path' and node.args and isinstance(node.args[0],ast.Constant):
                value = node.args[0].value
                if isinstance(value,str):
                    assert not value.startswith(('/home/','/mnt/','scratch/ladder/','scratch/test_b/','docs/internal/')),(row['public'],value)
    # Internal retained records are local-only and intentionally record original
    # private storage. Scan every public Markdown/JSON, including new specs.
    for root in (SPEC, REPO/'docs'):
        for path in root.rglob('*'):
            if path.is_file() and path.suffix in {'.md','.json'} and not path.is_relative_to(REPO/'docs/internal'):
                _assert_public_text_hygiene(path,path.read_text())
    spec = PublicSpecification(SPEC,'v8')
    with pytest.raises(SpecMismatch,match='implementation receipts'):
        spec.audit_implementation_manifest('rng',declared_pointers={'rng':'/rng'},manifest_path='receipt.json')


@pytest.mark.parametrize('extension',['.md','.json'])
def test_private_absolute_path_hygiene_rejects_text(extension):
    with pytest.raises(AssertionError):
        _assert_public_text_hygiene('public'+extension,'Use /mnt/private-data/test_b/')
    _assert_public_text_hygiene('public'+extension,'Supply OUTPUT_ROOT explicitly outside Git.')


def test_recovered_modules_import():
    for p in (REPO/'src/born_ladder/reproduction/predictive').glob('*.py'):
        if p.stem!='__init__':importlib.import_module('born_ladder.reproduction.predictive.'+p.stem)


def test_quadratic_ring_completion():
    from born_ladder.reproduction.census_writers.structural_completion import certify_G
    from fractions import Fraction
    result=certify_G(Fraction(1,1<<300))
    assert [[str(x) for x in row] for row in result['YES_table_exact']]==[['1','1/4','1/4'],['1/4','1','1/4'],['1/4','1/4','1'],['0','3/4','3/4'],['3/4','0','3/4'],['3/4','3/4','0']]
    assert result['all_projectors_trace1_idempotent_G_adjoint']


@pytest.mark.data
def test_historical_loader_seed_and_full_fit():
    from born_ladder.record_tests import estimators as E,real_v6 as R
    bundle=json.loads(Path(os.environ['BORN_LADDER_DATA']).read_text())
    root=Path(bundle['roots']['p5'])
    loader=R.P5RecordLoader(root)
    entry=loader.loader.manifest['allowed_files'][0]
    raw=loader.load(root/'record_view'/entry['file']);d=raw.canonical()
    archived=json.loads((root/'fits/original/cd42cae661f281764814_r2/models.json').read_text())
    assert d.context==archived['context']=='EXP-112::loo_A13::k9::s3::h8'
    assert d.table_hash==archived['table_hash']
    framed=E._seed('v5','square',d.table_hash,d.context,2,2,0)
    unframed=E._seed('v5','square',d.table_hash,d.context.removesuffix('::h8'),2,2,0)
    assert framed==14422621387058904548
    assert unframed==11592874682777534705
    result=E.fit_model('square',d,2)
    old=archived['models']['square']
    assert result.theta.tobytes()==np.asarray(old['theta'],dtype=float).tobytes()
    assert result.train_loss==old['train_loss']
    assert result.validation_loss==old['validation_loss']
    assert result.metadata==old['metadata']


@pytest.mark.data
def test_complete_cohort_reconstruction():
    # Complete reconstruction, not a membership sample. Inputs are explicit
    # public producer outputs in the supplied retained archive layout.
    from born_ladder.reproduction.census_writers.build_inventory import rebuild_inventory
    bundle=json.loads(Path(os.environ['BORN_LADDER_DATA']).read_text())
    root=Path(bundle['roots']['repo'])
    out=Path(os.environ['E2E_P1_COHORT_OUTPUT'])
    result=rebuild_inventory(archive_root=root,
        campaign_path=root/'results/derived/born_route_rebuild1_v2/rb1v2_g2c_campaign.json',
        invocation_path=root/'results/derived/born_route_rebuild1_v2/rb1v2_g2c_invocation_manifest.json',
        unit_logical_path='results/derived/born_route_rebuild1_v2/rb1v2_g2c_v23_units.jsonl',
        output_dir=out,historical_inputs=True)
    actual=json.loads((out/'INVENTORY.json').read_text())
    expected=json.loads((root/'scratch/ladder/CENSUS/INVENTORY.json').read_text())
    assert result['selected_count']==120
    assert actual==expected


@pytest.mark.data
def test_readable_values_equal_retained_original_specifications():
    from born_ladder.snapshot.historical import HistoricalInputs
    bundle = json.loads(Path(os.environ['BORN_LADDER_DATA']).read_text())
    history = HistoricalInputs(Path(os.environ['E2E_P1_HISTORICAL_ROOT']))
    references = json.loads((Path(__file__).parent/'fixtures/e2e_spec_value_reference.json').read_text())['rows']
    process_keys = {'archive2_consumption_binding','source_identity','publication_identity',
        'signed_pins','frozen_input_bindings','environment_evidence','review_bindings',
        'execution_packet','authority','launch_authorization','completion_receipt'}
    def stripped(value):
        if isinstance(value,dict):
            return {k:stripped(v) for k,v in value.items() if k not in process_keys}
        if isinstance(value,list):return [stripped(v) for v in value]
        return value
    checked = 0
    for version in ('v8','v21','v23','v24'):
        spec = PublicSpecification(SPEC,version)
        original = json.loads(history.read('born_route_rebuild1_spec_'+version+'.json',
                                           expected_sha256=spec.scientific_rng_identity))
        for row in references:
            if 'v'+str(row['version']) != version:
                continue
            pointer = row['pointer']
            value = original
            for key in pointer.strip('/').split('/'):
                value = value[int(key)] if isinstance(value,list) else value[key]
            assert spec.get(pointer) == stripped(value),(version,pointer)
            checked += 1
    assert checked == 103


@pytest.mark.data
def test_shared_snapshot_verifier_on_retained_unit_samples():
    """Exercise the verification path after consolidation; no population fit."""
    import io
    from born_ladder.claims import Evidence, artifact
    from born_ladder.snapshot.verification import verify_units
    evidence = Evidence(os.environ['BORN_LADDER_DATA'])
    config = evidence.config('P12')
    for stage,version in (('g2a','v8'),('g2c','v24')):
        records = []
        with artifact(evidence,config[stage]['units']) as (stream,_,_):
            while len(records) < 3:
                raw = stream.readline()
                assert raw, 'not enough retained eligible units'
                if json.loads(raw)['eligibility']:
                    records.append(raw)
            # The compressed archive reader validates its closure and full
            # compressed-stream commitment; consume the remainder without
            # computing further predictions or any population statistics.
            if isinstance(config[stage]['units'],dict):
                while stream.read(1 << 20):pass
        sample = b''.join(records)
        replay = verify_units(io.BytesIO(sample),spec=PublicSpecification(SPEC,version),
                              stage=stage,expected_sha256=hashlib.sha256(sample).hexdigest(),
                              expected_size_bytes=len(sample))
        assert replay['status'] == 'PASS' and replay['eligible'] == 3
        assert replay['laws_checked'] > 0
        recorded = evidence.read(config[stage]['verification'])
        assert replay['maximum_value_difference'] <= recorded['maximum_value_difference']
        print(json.dumps({'stage':stage,'rows':replay['rows'],
                          'laws_checked':replay['laws_checked'],
                          'maximum_value_difference':replay['maximum_value_difference']},sort_keys=True))


def _erasure_versions(alphabet):
    """Execute only hash-checked public/frozen functions, never fitter imports."""
    from types import SimpleNamespace
    reference=json.loads((Path(__file__).parent/'fixtures/e2e_source_equivalence.json').read_text())
    definition=next(m for m in reference['modules'] if m['public_module']=='src/born_ladder/record_tests/real_v6.py')['definitions']['erasure_not_computed']
    frozen=definition['refactor']['original_source']
    node=_ScientificImports().visit(ast.parse(frozen).body[0])
    assert hashlib.sha256(ast.dump(node,include_attributes=False).encode()).hexdigest()==definition['normalized_ast_sha256']
    namespace={'Path':Path,'np':np,'hashlib':hashlib,'json':json,
               '__package__':'born_ladder.record_tests','record_alphabet':alphabet}
    original=dict(namespace)
    exec('from __future__ import annotations\n'+frozen,original)
    public=ast.parse((REPO/'src/born_ladder/record_tests/real_v6.py').read_text())
    nodes=[node for node in public.body if isinstance(node,ast.FunctionDef) and node.name in
           ('sha','record_alphabet','eligible_entries','erasure_diagnostics','erasure_not_computed')]
    cert=ast.parse((REPO/'src/born_ladder/record_tests/cert_v6.py').read_text())
    cert_nodes=[node for node in cert.body if isinstance(node,ast.FunctionDef) and node.name in ('encoded','canonical_document')]
    cn={'Path':Path,'json':json}
    exec('from __future__ import annotations\n'+ast.unparse(ast.Module(body=cert_nodes,type_ignores=[])),cn)
    namespace['C']=SimpleNamespace(encoded=cn['encoded'],canonical_document=cn['canonical_document'])
    exec('from __future__ import annotations\n'+ast.unparse(ast.Module(body=nodes,type_ignores=[])),namespace)
    real_alphabet=namespace['record_alphabet']
    namespace['record_alphabet']=alphabet
    return original['erasure_not_computed'],namespace,real_alphabet


@pytest.mark.parametrize('raw_count,package_count',[(1,1),(2,3),(3,4),(4,5),(5,8),(32,32)])
def test_erasure_refactor_exact_output_equivalence(raw_count,package_count):
    # Preserve first-encounter ordering and deduplication across ranks/files.
    alphabets={'b':np.array([(r,p) for r in range(raw_count) for p in range(package_count)],dtype=np.int64),
               'a':np.array([[0,0],[1,1],[1,2]],dtype=np.int64)}
    calls=[]
    def alphabet(root,entry):calls.append(entry['file']);return alphabets[entry['file']]
    original,current,_=_erasure_versions(alphabet)
    entries=[({'file':name,'m':len(alphabets[name])},rank) for name,rank in [('b',2),('b',3),('a',4),('b',4)]]
    old=original(Path('.'),entries,{'manager_approval':True});old_calls=list(calls);calls.clear()
    new=current['erasure_not_computed'](Path('.'),entries,{'manager_approval':True})
    assert new==old and calls==old_calls==['b','a']
    assert json.dumps(new,sort_keys=True)==json.dumps(old,sort_keys=True)
    assert list(new)!=list(old)  # Declared top-level insertion-order change.
    assert [r['context_file'] for r in new['campaign_context_figures']]==['b','a']
    docs={'spec_reference','spec_quote','manager_ruling','manager_approval'}
    assert current['erasure_diagnostics'](Path('.'),entries)=={k:v for k,v in old.items() if k not in docs}


def test_erasure_refactor_error_boundary():
    original,current,_=_erasure_versions(lambda root,entry:np.empty((0,2),dtype=np.int64))
    entries=[({'file':'empty','m':0},2)]
    with pytest.raises(ValueError,match='negative shift count'):original(Path('.'),entries,{'manager_approval':True})
    with pytest.raises(ValueError,match='requires nonempty'):current['erasure_not_computed'](Path('.'),entries,{'manager_approval':True})
    # Empty entry populations themselves retain the original valid result.
    assert original(Path('.'),[],{'manager_approval':True})==current['erasure_not_computed'](Path('.'),[],{'manager_approval':True})
    for function in (original,current['erasure_not_computed']):
        with pytest.raises(KeyError,match='manager_approval'):function(Path('.'),[],{})


@pytest.mark.data
def test_erasure_refactor_real_pipeline_inputs():
    retained=os.environ.get('E2E_ERASURE_RETAINED_ROOT');p8=os.environ.get('E2E_ERASURE_P8_ROOT')
    if not retained or not p8:pytest.skip('set E2E_ERASURE_RETAINED_ROOT and E2E_ERASURE_P8_ROOT')
    retained=Path(retained);p8=Path(p8)
    original,current,reader=_erasure_versions(lambda root,entry:reader(root,entry))
    # Actual retained setup/manifest selection and commitment-checked reader.
    setup=json.loads((retained/'setup.json').read_text())
    entries=current['eligible_entries'](retained,setup)
    rules={'manager_approval':json.loads((retained/'controls/erasure.json').read_text())['manager_approval']}
    old=original(retained,entries,rules);new=current['erasure_not_computed'](retained,entries,rules)
    assert new==old and current['C'].encoded(new)==current['C'].encoded(old)
    assert new==json.loads((retained/'controls/erasure.json').read_text())
    # P8 has not sampled/sealed yet. Its eight prospective file identities and
    # alphabets are checked against the actual census and immutable captures;
    # neither a record view nor a seal is fabricated or written.
    census=json.loads((p8/'census/eligibility.json').read_text())
    manifest=json.loads((retained/'record_view/manifest.json').read_text())
    allowed=sorted((c['exp'],c['config'],c['k'],c['step_index']) for c in census['training_contexts']
                   if c['h_c'] is not None and c['primary_excluded_reason'] is None and c['m']>2)
    assert allowed==[(e['exp'],e['config'],e['k'],e['step_index']) for e in manifest['allowed_files']]
    captured={}
    for row in json.loads((p8/'header_inventory.json').read_text()):
        file=p8/'headers'/row['file'];raw=file.read_bytes().splitlines()[0]
        assert hashlib.sha256(raw).hexdigest()==row['header_sha256']
        header=json.loads(raw)
        for context in header['contexts']:
            captured[(row['exp'],row['config'],context['k'],context['step_index'])]=np.asarray(context['alphabet_raw_package'],dtype=np.int64)
    for entry in manifest['allowed_files']:
        key=entry['exp'],entry['config'],entry['k'],entry['step_index']
        assert np.array_equal(captured[key],reader(retained,entry))
        expected='v6_trainval_'+hashlib.sha256(f'{entry["exp"]}/{entry["config"]}/{entry["k"]}/{entry["step_index"]}/{entry["map_sha256"]}'.encode()).hexdigest()[:20]+'.json'
        assert entry['file']==expected
    p8_entries=[(entry,rank) for entry in manifest['allowed_files'] for rank in (2,3,4)
                if any(all(entry[k]==c[k] for k in ('exp','config','k','step_index','map_sha256')) for c in census['rank_contexts'][str(rank)])]
    assert [(e['file'],r) for e,r in p8_entries]==[(e['file'],r) for e,r in entries]
    current['record_alphabet']=lambda root,entry:captured[(entry['exp'],entry['config'],entry['k'],entry['step_index'])]
    p8_original,p8_current,_=_erasure_versions(current['record_alphabet'])
    assert p8_original(p8,p8_entries,rules)==p8_current['erasure_not_computed'](p8,p8_entries,rules)==old
    assert p8_current['erasure_diagnostics'](p8,p8_entries)=={k:v for k,v in old.items() if k not in ('spec_reference','spec_quote','manager_ruling','manager_approval')}
