"""Project-local toolchain. No system PATH or global installation is changed."""
from pathlib import Path
import urllib.request, json, zipfile, hashlib, re, concurrent.futures
ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'.tools'
DEST.mkdir(exist_ok=True)
def get(url):
    with urllib.request.urlopen(url,timeout=90) as r: return r.read()
def node():
    version='v24.21.0'
    filename=f'node-{version}-win-x64.zip'
    checks=get(f'https://nodejs.org/dist/{version}/SHASUMS256.txt').decode()
    expected=next(x.split()[0] for x in checks.splitlines() if x.endswith('  '+filename))
    p=DEST/filename
    if not p.exists(): p.write_bytes(get(f'https://nodejs.org/dist/{version}/{filename}'))
    assert hashlib.sha256(p.read_bytes()).hexdigest()==expected
    with zipfile.ZipFile(p) as z: z.extractall(DEST)
    print('NODE',DEST/f'node-{version}-win-x64',flush=True)
def postgres():
    url='https://get.enterprisedb.com/postgresql/postgresql-17.6-1-windows-x64-binaries.zip'
    p=DEST/url.rsplit('/',1)[1]
    if not p.exists(): p.write_bytes(get(url))
    with zipfile.ZipFile(p) as z: z.extractall(DEST/'postgres17')
    (DEST/'postgres-download.json').write_text(json.dumps({'url':url,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()},indent=2))
    print('POSTGRES',url,flush=True)
with concurrent.futures.ThreadPoolExecutor(2) as pool:
    futures=[pool.submit(node),pool.submit(postgres)]
    for f in futures:
        try: f.result()
        except Exception as e: print(type(e).__name__,str(e),flush=True)
