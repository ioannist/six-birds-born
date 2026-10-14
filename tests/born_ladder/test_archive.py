"""The actual copy path and its complete union verification."""
import hashlib,json
from pathlib import Path
import pytest
from born_ladder.archive import copy_set,union_files,verify

def fixture(tmp_path):
 source=tmp_path/'source';source.mkdir();files={}
 for name,blob in [('main',b'original'),('extra',b'failed extra output')]:
  (source/name).write_bytes(blob);files[name]={'sha256':hashlib.sha256(blob).hexdigest(),'size_bytes':len(blob)}
 main=source/'main_manifest.json';art=source/'artifact_manifest.json'
 main.write_text(json.dumps({'files':{'main':files['main']}}));art.write_text(json.dumps({'outputs':{'extra':files['extra']['sha256']}}))
 union=union_files(source,main,art);m=source/'copy_set.json';m.write_text(json.dumps({'files':union}))
 return source,tmp_path/'archive',union,m

def test_union_extra_missing_and_corrupted(tmp_path):
 src,dst,files,m=fixture(tmp_path);assert len(files)==4
 copy_set(src,dst,files);assert verify(dst,m)['verified_files']==4
 (dst/'extra').unlink();assert verify(dst,m)['mismatches']==[{'path':'extra','status':'MISSING'}]
 (dst/'extra').write_bytes(b'corrupted');assert verify(dst,m)['mismatches']==[{'path':'extra','status':'DIFFERS'}]
 assert (src/'extra').read_bytes()==b'failed extra output'

def test_actual_copier_matching_reuse_and_differing_refusal(tmp_path):
 src,dst,files,m=fixture(tmp_path);assert copy_set(src,dst,files)['COPIED']==4
 assert copy_set(src,dst,files)['REUSED']==4
 (dst/'extra').write_bytes(b'differs')
 with pytest.raises(ValueError,match='differs'):copy_set(src,dst,files)
 assert (dst/'extra').read_bytes()==b'differs'

def test_actual_copier_destination_and_parent_symlinks(tmp_path):
 src,dst,files,m=fixture(tmp_path);link=tmp_path/'link';link.symlink_to(src,target_is_directory=True)
 for bad in [link,link/'child']:
  with pytest.raises(ValueError,match='symlink'):copy_set(src,bad,files)
 assert not (src/'child').exists()
 copy_set(src,dst,files);(dst/'extra').unlink();(dst/'extra').symlink_to(src/'extra')
 with pytest.raises(OSError):copy_set(src,dst,files)
 with pytest.raises(ValueError,match='outside'):copy_set(src,src/'not_created',files)
 assert not (src/'not_created').exists()

def test_actual_copier_interruption_retains_partial_and_finished(tmp_path):
 src,dst,files,m=fixture(tmp_path)
 def interrupt(p,n):
  if p.name=='extra':raise InterruptedError('simulated interruption')
 with pytest.raises(InterruptedError):copy_set(src,dst,files,interrupt)
 assert (dst/'artifact_manifest.json').read_bytes()==(src/'artifact_manifest.json').read_bytes()
 assert (dst/'extra.archive-partial').read_bytes()==(src/'extra').read_bytes()
 with pytest.raises(FileExistsError):copy_set(src,dst,files)
 assert (src/'extra').read_bytes()==b'failed extra output'

def test_actual_copier_concurrent_destination_never_clobbered(tmp_path):
 src,dst,files,m=fixture(tmp_path)
 def concurrent(p,n):
  if p.name=='extra':p.write_bytes(b'concurrent writer')
 with pytest.raises(FileExistsError):copy_set(src,dst,files,concurrent)
 assert (dst/'extra').read_bytes()==b'concurrent writer'
 assert (dst/'extra.archive-partial').read_bytes()==(src/'extra').read_bytes()

def test_source_storage_symlink_is_dereferenced(tmp_path):
 src,dst,files,m=fixture(tmp_path);storage=tmp_path/'storage';storage.write_bytes((src/'extra').read_bytes());(src/'extra').unlink();(src/'extra').symlink_to(storage)
 copy_set(src,dst,files)
 assert not (dst/'extra').is_symlink() and (dst/'extra').read_bytes()==storage.read_bytes()
 assert (src/'extra').is_symlink() and storage.exists()

def test_cli_publishes_metadata_with_the_same_safe_path(tmp_path):
 import subprocess,sys
 src,dst,files,m=fixture(tmp_path)
 command=[sys.executable,'-m','born_ladder.archive']
 proc=subprocess.run([*command,'--source',str(src),'--destination',str(dst),'--copy-set',str(m)],capture_output=True,text=True,check=True)
 assert json.loads(proc.stdout)['union_count']==4
 assert (dst/m.name).read_bytes()==m.read_bytes()
 assert verify(dst,dst/m.name)['status']=='PASS'
 proc=subprocess.run([*command,'--source',str(src),'--destination',str(dst),'--copy-set',str(m)],capture_output=True,text=True,check=True)
 assert json.loads(proc.stdout)['REUSED']==4
 (dst/m.name).write_bytes(b'altered self metadata')
 proc=subprocess.run([*command,'--source',str(src),'--destination',str(dst),'--copy-set',str(m)],capture_output=True,text=True)
 assert proc.returncode!=0 and (dst/m.name).read_bytes()==b'altered self metadata'


def test_historical_source_inputs_are_explicit_and_pin_checked(tmp_path):
 from born_ladder.snapshot.provenance import measure_historical_sources
 from born_ladder.snapshot.errors import IncompleteCampaign,SpecMismatch
 names=('born_probe.py_sha256','born_probe_extended.py_sha256','contracts.py_sha256')
 sources={};pins={}
 for i,name in enumerate(names):
  path=tmp_path/str(i);path.write_bytes(('original historical source '+str(i)).encode())
  sources[name]=path;pins[name]=hashlib.sha256(path.read_bytes()).hexdigest()
 assert measure_historical_sources(pins,sources)==pins
 with pytest.raises(IncompleteCampaign,match='explicit historical'):measure_historical_sources(pins,{})
 sources[names[0]].write_bytes(b'release source substituted')
 with pytest.raises(SpecMismatch,match='SHA-256'):measure_historical_sources(pins,sources)


def test_completion_writer_requires_matching_original_evidence(tmp_path):
 from born_ladder.snapshot.g2c_v23 import completion_writer_descriptor
 from born_ladder.snapshot.errors import IncompleteCampaign,SpecMismatch
 path=tmp_path/'original_writer';path.write_bytes(b'original completion writer')
 row={'role':'v23_completion_writer','path':'historical/original_writer.py',
      'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'size_bytes':path.stat().st_size}
 authorization={'executing_code':[row]}
 assert completion_writer_descriptor(authorization,path,original_path='historical/original_writer.py')==row
 with pytest.raises(IncompleteCampaign,match='explicit historical'):completion_writer_descriptor(authorization,None,original_path='historical/original_writer.py')
 with pytest.raises(SpecMismatch,match='unique'):completion_writer_descriptor({'executing_code':[row,row]},path,original_path='historical/original_writer.py')
 with pytest.raises(SpecMismatch,match='original identity'):completion_writer_descriptor(authorization,path,original_path='different/original.py')
 path.write_bytes(b'new release source')
 with pytest.raises(SpecMismatch,match='commitment'):completion_writer_descriptor(authorization,path,original_path='historical/original_writer.py')


def test_remeasurement_never_reopens_retired_writer_location(tmp_path):
 from born_ladder.snapshot.g2c_v23 import remeasure_authorization_descriptor
 from born_ladder.snapshot.errors import SpecMismatch
 root=tmp_path/'public';root.mkdir();source=tmp_path/'bound_original';source.write_bytes(b'old committed writer')
 old_identity='retired/completion_writer.py'
 row={'role':'v23_completion_writer','path':old_identity,'size_bytes':source.stat().st_size,
      'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
 assert not (root/old_identity).exists()
 assert remeasure_authorization_descriptor(row,repo_root=root,
   completion_writer_input=source,completion_writer_original_path=old_identity)==source
 assert not (root/old_identity).exists()
 source.write_bytes(b'changed')
 with pytest.raises(SpecMismatch,match='commitment'):
  remeasure_authorization_descriptor(row,repo_root=root,
   completion_writer_input=source,completion_writer_original_path=old_identity)


def authorization_fixture(tmp_path, monkeypatch):
 """Synthetic receipt graph; the writer measurement/validator are never mocked.

 Only the large unrelated frozen implementation-contract audit is stubbed.
 All descriptor bytes, schema values, code census and receipt projections use
 the real validation code, through the retained P12 receipt caller.
 """
 from types import SimpleNamespace
 import born_ladder.snapshot.g2c_v23 as V
 canonical_json_bytes,sha256_bytes=V.canonical_json_bytes,V.sha256_bytes
 root=tmp_path/'public';root.mkdir()
 def descriptor(name,role,blob=b'evidence'):
  p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(blob)
  return V.identity_descriptor(p,role=role,repo_root=root,absolute=role in V.CURRENT_ABSOLUTE_ROLES)
 code=[descriptor(name,role,name.encode()) for name,role in V._REQUIRED_EXECUTING_CODE]
 source=tmp_path/'relocated_writer';source.write_bytes(b'archived original completion writer')
 old='retired/completion_writer.py'
 writer={'role':'v23_completion_writer','path':old,'size_bytes':source.stat().st_size,
         'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
 code=sorted([*code,writer],key=lambda r:r['path'].encode())
 by_role={r['role']:r for r in code}
 manifest=descriptor('scripts/rebuild1/implementation_manifest.jsonl','current_implementation_manifest')
 env=[descriptor('env/'+str(i),role) for i,role in enumerate([
  'v23_freeze_environment_census','v23_glibc_transition_evidence','v23_execution_environment_admission'])]
 history=descriptor('history.json','historical_evaluation_authorization')
 guard=descriptor('guard.py','v21_guard_launcher')
 route={'input_bindings':[],'complete_dependency_closure':[],
        'consumed_v21_evaluation_authorization':history,'reused_campaign_side_receipts':[],
        'source_outcome_evidence':[]}
 values={
  '/identity/json_sha256':'synthetic self hash',
  '/completeness/g2c_v24_sealed_input_route/source_identity':{'source':'synthetic'},
  '/completeness/g2c_v24_sealed_input_route':route,
  '/completeness/g2c_raw_stdout_derivation/controls/rotation':{},
  '/provenance/publication_environment_freeze_measurement/evidence':{k:v for k,v in env[0].items() if k!='role'},
  '/provenance/environment_transitions/0/package_update_evidence':{k:v for k,v in env[1].items() if k!='role'},
 }
 class Spec:
  repo_root=root
  path=root/"synthetic_spec.json"
  historical_companion="synthetic_spec.json"
  attestation=SimpleNamespace(json_sha256='synthetic hash',freeze_commit='synthetic commit',spec_id='synthetic spec',tag='synthetic tag')
  def get(self,pointer,*,expected_type):
   value=values[pointer];assert isinstance(value,expected_type);return value
 spec=Spec()
 auth={'schema':'RB1_G2C_V23_EVALUATION_AUTHORIZATION_V1',
       'publication_spec_identity':V.publication_identity(spec),'source_spec_identity':V.source_identity(spec),
       'v23_evaluation_count':1,'sealed_input_reuse_authorized':True,'authorized_outputs':[],
       'complete_input_identities':[],'historical_evaluation_authorization':history,
       'reused_campaign_side_receipts':[],'preserved_v21_outcome_evidence':[],
       'sealed_input_route_sha256':sha256_bytes(canonical_json_bytes(route)),
       'approved_rotation_contract_sha256':sha256_bytes(canonical_json_bytes({})),
       'publication_environment_evidence':env,'executing_code':code,
       'reviewed_responsibility_code':[by_role['v23_evaluator_entrypoint'],writer,
          *[r for r in code if r['role'] not in {'v23_evaluator_entrypoint','v23_completion_writer'}]],
       'implementation_manifest':manifest,'v23_single_attempt_guard':{'mechanism_identity':writer},
       'preserved_v21_guard_launcher':guard}
 values['/completeness/g2c_v24_evaluation_authorization']={
  'keys':list(auth),'record_schema':auth['schema'],
  'types':{k:{'kind':'exact_reference','expected_values':v} for k,v in auth.items()}}
 monkeypatch.setattr(V,'audit_v23_contracts',lambda s: None)
 return spec,auth,source,old


def test_p12_receipt_caller_forwards_relocated_writer_and_rejects_bad_evidence(tmp_path,monkeypatch):
 from born_ladder.snapshot.evaluate_g2c_campaign import _validate_receipt_semantics_independent
 from born_ladder.snapshot.errors import IncompleteCampaign
 spec,auth,source,old=authorization_fixture(tmp_path,monkeypatch)
 def check(path=source,identity=old):
  return _validate_receipt_semantics_independent(spec,role='evaluation_authorization',document=auth,
   completion_writer_input=path,completion_writer_original_path=identity)
 assert not (spec.repo_root/old).exists()
 assert check() is None
 with pytest.raises(IncompleteCampaign,match='explicit historical'):check(None)
 with pytest.raises(IncompleteCampaign,match='explicit historical'):check(identity=None)
 with pytest.raises(IncompleteCampaign,match='original identity'):check(identity='other/writer.py')
 original=source.read_bytes();source.write_bytes(b'altered writer')
 with pytest.raises(IncompleteCampaign,match='commitment'):check()
 source.write_bytes(original);source.unlink()
 with pytest.raises(IncompleteCampaign,match='regular nonsymlink'):check()
 assert not (spec.repo_root/old).exists()


def test_graph_census_uses_relocated_writer_bytes(tmp_path,monkeypatch):
 import born_ladder.snapshot.g2c_v23 as V
 from born_ladder.snapshot.errors import IncompleteCampaign,SpecMismatch
 spec,auth,source,old=authorization_fixture(tmp_path,monkeypatch)
 writer=next(r for r in auth['executing_code'] if r['role']=='v23_completion_writer')
 node={'node_id':'v23_completion_writer',**writer}
 kw={'completion_writer_input':source,'completion_writer_original_path':old}
 raw,location=V._graph_node_bytes(spec,node,repo_root=spec.repo_root,**kw)
 assert raw==source.read_bytes() and location==('filesystem',str(source.resolve()))
 assert V._independent_raw_binding_census(spec,[node],repo_root=spec.repo_root,**kw)==set()
 assert V.build_hash_graph(spec,[node],**kw)['nodes']==[node]
 with pytest.raises(IncompleteCampaign,match='explicit historical'):
  V._independent_raw_binding_census(spec,[node],repo_root=spec.repo_root)
 source.write_bytes(b'altered graph predecessor')
 with pytest.raises(SpecMismatch,match='commitment'):V.build_hash_graph(spec,[node],**kw)
 assert not (spec.repo_root/old).exists()


def test_all_keep_verification_callers_forward_both_writer_inputs():
 """Catch omitted keywords in every retained call, including aliases/wrappers."""
 import ast
 # All changed wrapper names; modules are public source, not a local receipt.
 files=[Path('src/born_ladder/snapshot/g2c_v23.py'),Path('src/born_ladder/snapshot/evaluate_g2c_campaign.py')]
 trees={p:ast.parse(p.read_text()) for p in files}
 names={'validate_v23_destinations'}
 for tree in trees.values():
  names|={f.name for f in tree.body if isinstance(f,ast.FunctionDef)
          and {'completion_writer_input','completion_writer_original_path'}<=
          {a.arg for a in f.args.kwonlyargs}}
 checked=0
 for p,tree in trees.items():
  for n in ast.walk(tree):
   if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in names:
    args={k.arg:k.value for k in n.keywords}
    assert {'completion_writer_input','completion_writer_original_path'}<=args.keys(),(p,n.lineno,n.func.id)
    for name in ('completion_writer_input','completion_writer_original_path'):
     value=args[name]
     # The legacy fixed-source census never admits a v23 completion writer;
     # its newly extracted measurement helper intentionally supplies None.
     legacy=[f for f in tree.body if isinstance(f,ast.FunctionDef) and f.name=='_fixed_identity_rows' and f.lineno<=n.lineno<=f.end_lineno]
     if legacy:
      assert isinstance(value,ast.Constant) and value.value is None
      continue
     assert (isinstance(value,ast.Name) and value.id==name) or (
      isinstance(value,ast.Attribute) and isinstance(value.value,ast.Name) and value.value.id=='args' and value.attr==name),(p,n.lineno,name)
    checked+=1
 assert checked==10  # exactly the retained verification callers; launch/publication callers removed
