"""Record regular Rust checks and schema validation without calling models."""
import json
import re
import subprocess
import time
from pathlib import Path
from openapi_spec_validator import validate_spec

ROOT = Path(__file__).resolve().parents[1]
def main():
    started=time.perf_counter()
    result=subprocess.run(["cargo","test","--locked"],cwd=ROOT,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=600)
    raw=result.stdout+result.stderr
    matches=re.findall(r"test result: (\w+)\. (\d+) passed; (\d+) failed; (\d+) ignored",raw)
    spec=json.loads((ROOT/"data/contracts/openapi.json").read_text(encoding="utf-8"))
    validate_spec(spec)
    report={"measured_at":time.strftime("%Y-%m-%dT%H:%M:%S%z"),"command":"cargo test --locked","exit_code":result.returncode,"elapsed_seconds":round(time.perf_counter()-started,3),"rust":{"passed":sum(int(x[1])for x in matches),"failed":sum(int(x[2])for x in matches),"ignored":sum(int(x[3])for x in matches)},"openapi":{"valid":True,"paths":len(spec['paths']),"operations":sum(k in ('get','put','post','delete','patch','head','options')for p in spec['paths'].values()for k in p)},"passed":result.returncode==0 and bool(matches)}
    out=ROOT/"validation/reports/current";out.mkdir(parents=True,exist_ok=True)
    (out/"unit-checks.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    (out/"unit-checks.log").write_text(raw,encoding="utf-8")
    print(json.dumps(report))
    assert report['passed'], raw

if __name__ == "__main__":main()
