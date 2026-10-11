"""Capture actual release/browser builds and artifact fingerprints."""
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def main():
    node=ROOT/'.tools/node-v24.21.0-win-x64/node.exe'
    if not node.exists():node=Path(shutil.which('node')or'node')
    cli=node.parent/'node_modules/npm/bin/npm-cli.js'
    env={**os.environ,'PATH':str(node.parent)+os.pathsep+os.environ['PATH']}
    commands=[(['cargo','build','--release','--locked'],ROOT),([str(node),str(cli),'run','build'],ROOT/'web')]
    checks=[];logs=[]
    for command,cwd in commands:
        t=time.perf_counter()
        r=subprocess.run(command,cwd=cwd,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=600,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        checks.append({'command':command,'exit_code':r.returncode,'seconds':round(time.perf_counter()-t,3)})
        logs.append(r.stdout+r.stderr)
        if r.returncode:break
    paths=[ROOT/'target/release/fsp-trajectory.exe',*ROOT.glob('web/dist/assets/*'),*ROOT.glob('ml_time_forecasting/artifacts/*.cbm')]
    report={'measured_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'checks':checks,'passed':len(checks)==2 and all(x['exit_code']==0 for x in checks),'sha256':{str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()for p in paths if p.is_file()}}
    (ROOT/'validation/reports/current/build.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (ROOT/'validation/reports/current/build.log').write_text('\n'.join(logs),encoding='utf-8')
    print(json.dumps(report))
    assert report['passed']

if __name__=='__main__':main()
