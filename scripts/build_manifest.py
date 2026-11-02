"""Hash the distributable, non-ignored tree; no timestamp or private path leakage."""
from pathlib import Path
import hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[1]

def files():
    result=subprocess.run(['git','ls-files','-z','--cached','--others','--exclude-standard'],cwd=ROOT,capture_output=True,check=True)
    return sorted({s for s in result.stdout.decode().split('\0') if s and (ROOT/s).is_file() and s!='RELEASE_MANIFEST.json'})

if __name__=='__main__':
    records=[{'path':s,'sha256':hashlib.sha256((ROOT/s).read_bytes()).hexdigest(),'bytes':(ROOT/s).stat().st_size} for s in files()]
    out={'candidate':'0.1.0-rc1','publication':'not approved; private candidate','files':records}
    (ROOT/'RELEASE_MANIFEST.json').write_text(json.dumps(out,indent=2)+'\n')
    print(f'Manifest: {len(records)} files')
