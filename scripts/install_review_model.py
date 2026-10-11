"""Complete the official Ollama manifest using TLS-verified registry downloads.

The registry sometimes fails DNS in Go on this Windows machine. curl's resolver
can use an explicit public Cloudflare address while verifying the registry's TLS
hostname. Every small layer is SHA-256 checked. Existing weight blobs are reused.
"""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
STORE=Path('C:/Users/Arkadiy/.ollama/models')

def get(path):
    return subprocess.check_output(['curl.exe','-fsSL','--retry','3','--connect-timeout','10','--resolve','registry.ollama.ai:443:104.18.16.170','https://registry.ollama.ai/v2/library/gpt-oss/'+path],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))

def main():
    manifest=get('manifests/20b');data=json.loads(manifest)
    for layer in [data['config'],*data['layers']]:
        digest=layer['digest'];path=STORE/'blobs'/digest.replace(':','-')
        if layer['size']>1_000_000:
            if not path.exists() or path.stat().st_size!=layer['size']:
                raise RuntimeError('Pull the official gpt-oss:20b weights first')
            print('Official weight blob available',flush=True)
            continue
        content=get('blobs/'+digest)
        if len(content)!=layer['size'] or hashlib.sha256(content).hexdigest()!=digest.split(':')[1]:
            raise RuntimeError('Registry integrity mismatch')
        path.write_bytes(content)
    dest=STORE/'manifests/registry.ollama.ai/library/gpt-oss/20b';dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(manifest)
    print('Official gpt-oss:20b manifest installed',flush=True)
if __name__=='__main__':main()
