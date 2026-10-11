"""Capture the password-only access build and contract; preserve baseline benchmarks."""
import hashlib,json,time
from pathlib import Path
from openapi_spec_validator import validate
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'validation/reports/current'
def main():
 contract=json.loads((ROOT/'data/contracts/openapi.json').read_text(encoding='utf-8'));validate(contract)
 files=[ROOT/'target/release/fsp-trajectory.exe',ROOT/'web/dist/index.html',*(ROOT/'web/dist/assets').glob('*'),ROOT/'web/public/media/auth-network.mp4']
 baseline=json.loads((OUT/'source-manifest.json').read_text(encoding='utf-8'))
 report={'passed':True,'generated_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'scope':'authenticated interface, public contribution and numerical research revision; individual benchmark dates and scopes preserved','baseline_source_fingerprint':baseline['source_fingerprint'],'sha256':{str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()for p in files if p.is_file()},'openapi':{'validated':True,'paths':len(contract['paths']),'operations':sum(method in ('get','post','put','patch','delete','head','options')for methods in contract['paths'].values()for method in methods)}}
 (OUT/'interface-revision-build.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps({'passed':True,'openapi':report['openapi']}))
if __name__=='__main__':main()
