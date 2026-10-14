"""Optional diagnostic Python read/child-command log; no scientific computation."""
import os
import sys
import json
from pathlib import Path


def install():
    target=os.environ.get('BORN_LADDER_READ_AUDIT')
    if not target:return
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
    def hook(event,args):
        if event=='open' and isinstance(args[0],(str,bytes)):
            path=os.fsdecode(args[0]);mode=args[1];flags=args[2]
            if isinstance(mode,str) and not any(x in mode for x in 'wa+') or mode is None and flags&os.O_ACCMODE==os.O_RDONLY:
                row={'pid':os.getpid(),'event':'read','path':os.path.abspath(path)}
            else:return
        elif event=='subprocess.Popen':
            row={'pid':os.getpid(),'event':'child','executable':str(args[0]),'argv':args[1],'cwd':str(args[2] or os.getcwd())}
        else:return
        os.write(fd,(json.dumps(row,default=str,separators=(',',':'))+'\n').encode())
    sys.addaudithook(hook)
