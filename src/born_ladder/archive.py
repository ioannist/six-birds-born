"""Explicit archive roots, lexical extraction and write-once commitments."""
from pathlib import Path
import hashlib,json,os
from . import metadata
from .arithmetic import qserial

def sha(path):
 with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def put(path,value):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 data=value if isinstance(value,bytes) else (value if isinstance(value,str) else json.dumps(qserial(value),indent=2,sort_keys=True,allow_nan=False)+'\n').encode()
 # Exclusive creation: a prior artifact is never rewritten, even on mismatch.
 with path.open('xb') as stream:stream.write(data)
def verify_files(root,files):
 archive=Archive(root)
 for name,expected in files.items():
  actual=sha(archive.path(name))
  expected=expected['sha256'] if isinstance(expected,dict) else expected
  if actual!=expected:raise ValueError('commitment mismatch: '+name)
 return len(files)
class Archive:
 def __init__(self,root):
  # An explicit checked logical-to-execution correspondence is an I/O view,
  # not a changed selection key or an assertion of historical execution.
  if isinstance(root,dict):
   if root.get('schema')!='born_structural_input_view_v1':raise ValueError('unsupported structural input view')
   self.root=Path(root['root']).resolve();self.input_files=root['files']
  else:self.root=Path(root).resolve();self.input_files=None
 def path(self,name):
  p=Path(name)
  if p.is_absolute() or '..' in p.parts:raise ValueError('archive path must be relative: '+str(name))
  candidate=Path(self.input_files[str(p)]) if self.input_files is not None else self.root/p
  # Archive copies may dereference original storage symlinks; location is explicit.
  return candidate
 def line(self,pointer,payload=False):
  with self.path(pointer['path']).open('rb') as stream:stream.seek(pointer['byte_offset']);raw=stream.readline()
  core=raw.rstrip(b'\n')
  if 'line_sha256' in pointer and hashlib.sha256(core).hexdigest()!=pointer['line_sha256']:raise ValueError('line commitment mismatch')
  if payload:
   tag,body=core.split(b' ',1)
   if hashlib.sha256(body).hexdigest()!=pointer['payload_sha256']:raise ValueError('payload commitment mismatch')
   return body.decode(),len(tag)+1,raw
  return core.decode(),0,raw
 def structural(self,row):
  key=row['provenance_key'];a=key['kernel']['artifact']
  if sha(self.path(a['path']))!=a['file_sha256']:raise ValueError('kernel file hash mismatch')
  text,_,_=self.line(a,True);lo,hi=a['char_range'];blob=text[lo:hi].encode()
  if hashlib.sha256(blob).hexdigest()!=a['field_sha256']:raise ValueError('kernel field hash mismatch')
  return json.loads(blob)
 def verify_seal(self,path):
  seal=json.loads(self.path(path).read_text())
  verify_files(self.root,seal.get('outputs',{}))
  prev=seal.get('previous')
  if prev:
   if sha(self.path(prev['path']))!=prev['sha256']:raise ValueError('previous seal mismatch')
   self.verify_seal(prev['path'])
  return seal

# Integrity utilities extracted without behavior changes from the historical
# archive copier and verifier. Source storage links are dereferenced;
# destination ancestors and files are never followed through symlinks.
import argparse,stat

def digest(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def safe_name(name):
 p=Path(name)
 if p.is_absolute() or '..' in p.parts or not p.parts:raise ValueError('unsafe archive name: '+name)
 return p


def union_files(root,main,artifacts,excluded=()):
 """Materialize once. Verification uses this table, not a smaller manifest."""
 root=Path(root);files={};excluded=set(excluded)
 for table in (json.loads(Path(main).read_text())['files'],json.loads(Path(artifacts).read_text())['outputs']):
  for name,entry in table.items():
   safe_name(name)
   if name.startswith('scratch/code_closure/venv/') or name in excluded:continue
   value=entry if isinstance(entry,dict) else {'sha256':entry,'size_bytes':(root/name).stat().st_size}
   if name in files and files[name]!=value:raise ValueError('conflicting copy-set entry: '+name)
   files[name]=value
 for p in (Path(main),Path(artifacts)):
  name=str(p.resolve().relative_to(root.resolve()));files[name]={'sha256':digest(p),'size_bytes':p.stat().st_size}
 return dict(sorted(files.items()))


def validate_destination(source,destination):
 source=Path(source).resolve();dest=Path(os.path.abspath(destination))
 if dest==source or source in dest.parents:raise ValueError('destination must be outside source repository')
 for p in [*reversed(dest.parents),dest]:
  if p.is_symlink():raise ValueError('symlink destination/ancestor refused: '+str(p))
  if p.exists() and not p.is_dir():raise ValueError('non-directory ancestor: '+str(p))
 return dest


def directory_fd(path):
 """Walk from / using directory FDs, refusing races through symlink ancestors."""
 fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
 try:
  for part in Path(os.path.abspath(path)).parts[1:]:
   try:os.mkdir(part,dir_fd=fd)
   except FileExistsError:pass
   new=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=new
  return fd
 except BaseException:os.close(fd);raise


def publish(source,destination,entry,after_chunk=None):
 """No-replace link publication; matching regular files only may be reused."""
 fd=directory_fd(destination.parent);name=destination.name;partial=name+'.archive-partial'
 try:
  try:existing=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
  except FileNotFoundError:existing=None
  if existing is not None:
   with os.fdopen(existing,'rb') as f:
    if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):raise ValueError('existing destination not regular')
    if os.fstat(f.fileno()).st_size!=entry['size_bytes'] or hashlib.file_digest(f,'sha256').hexdigest()!=entry['sha256']:raise ValueError('existing archive differs: '+str(destination))
   return 'REUSED'
  partial_fd=os.open(partial,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644,dir_fd=fd)
  with Path(source).open('rb') as src,os.fdopen(partial_fd,'wb') as dst:
   h=hashlib.sha256();size=0
   while blob:=src.read(1024*1024):
    dst.write(blob);dst.flush();h.update(blob);size+=len(blob)
    if after_chunk:after_chunk(destination,size)
   os.fsync(dst.fileno())
  if h.hexdigest()!=entry['sha256'] or size!=entry['size_bytes']:raise ValueError('source/copy differs: '+str(source))
  os.link(partial,name,src_dir_fd=fd,dst_dir_fd=fd,follow_symlinks=False) # EEXIST cannot clobber
  os.unlink(partial,dir_fd=fd);os.fsync(fd)
  return 'COPIED'
 finally:os.close(fd)


def copy_set(source,destination,files,after_chunk=None):
 source=Path(source).resolve();dest=validate_destination(source,destination)
 # Validate every name and source BEFORE destination creation.
 for name,entry in files.items():
  safe_name(name)
  if digest(source/name)!=entry['sha256'] or (source/name).stat().st_size!=entry['size_bytes']:raise ValueError('source mismatch: '+name)
 counts={'COPIED':0,'REUSED':0}
 for name,entry in sorted(files.items()):counts[publish(source/name,dest/name,entry,after_chunk)]+=1
 return {'union_count':len(files),**counts}


def main():
 p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--destination',required=True);p.add_argument('--copy-set',required=True);a=p.parse_args()
 c=Path(a.copy_set);name=c.resolve().relative_to(Path(a.source).resolve());safe_name(str(name));files=json.loads(c.read_text())['files'];print(json.dumps(copy_set(a.source,a.destination,files),sort_keys=True))
 # Self-excluded copy-set metadata uses the very same safe publisher.
 dest=validate_destination(a.source,a.destination)
 publish(c,dest/name,{'sha256':digest(c),'size_bytes':c.stat().st_size})


def verify(root,manifest):
 root=Path(root);m=json.loads(Path(manifest).read_text());files=m.get('files',m.get('outputs',{}));bad=[];size=0
 if not files:raise ValueError('empty archive manifest')
 for name,entry in files.items():
  path=safe_name(name);expected=entry['sha256'] if isinstance(entry,dict) else entry
  try:
   with (root/path).open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
   actual_size=(root/path).stat().st_size;size+=actual_size
   if actual!=expected or isinstance(entry,dict) and actual_size!=entry['size_bytes']:bad.append({'path':name,'status':'DIFFERS'})
  except FileNotFoundError:bad.append({'path':name,'status':'MISSING'})
 return {'status':'PASS' if not bad else 'FAIL','verified_files':len(files),'bytes':size,'mismatches':bad}


if __name__=="__main__":main()
