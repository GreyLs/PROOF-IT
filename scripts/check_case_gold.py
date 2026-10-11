"""Run developer-authored semantic regressions against actual Qwen, preserving evidence."""
from pathlib import Path
import subprocess,json,hashlib,time,sys
ROOT=Path(__file__).resolve().parents[1]
start=time.monotonic();lines=[];cases=[]
p=subprocess.Popen(['cargo','test','live_reasoning_regressions','--','--ignored','--nocapture'],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
for line in p.stdout:
    lines.append(line);print(line,end='',flush=True)
    if line.startswith('LIVE_GOLD '):
        _,index,payload=line.split(' ',2);cases.append({'fixture':int(index),'evaluation':json.loads(payload)})
code=p.wait()
(ROOT/'validation/reports/current/case-gold-results.json').write_text(json.dumps({'passed':code==0,'elapsed_seconds':round(time.monotonic()-start,2),'cases':cases,'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ['src/cases.rs','src/interview.rs']},'independent_validation':False,'fixture_author':'implementation developer; explicit correct and incorrect mechanisms'},ensure_ascii=False,indent=2),encoding='utf-8')
(ROOT/'runtime/case-gold.log').write_text(''.join(lines),encoding='utf-8')
sys.exit(code)
