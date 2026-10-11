"""Read-only runtime readiness without publishing secrets or identity data."""
import hashlib
import json
import subprocess
import time
from pathlib import Path
import httpx
from scripts.workbench_test_fixture import Fixture

ROOT=Path(__file__).resolve().parents[1]
def main():
    f=Fixture()
    try:
        with httpx.Client(trust_env=False,timeout=10)as c:
            public=c.get(f.cfg['BASE_URL']+'/api/health')
            models=c.get(f.cfg['OLLAMA_URL']+'/api/ps').json()['models']
            review=c.get(f.cfg['CODE_REVIEW_OLLAMA_URL']+'/api/tags').json()['models']
        gpu=next((m for m in models if m.get('name')==f.cfg['OLLAMA_MODEL']),{})
        q=f.db.execute("SELECT hits,greatest(0,extract(epoch from window_start+make_interval(mins=>15)-now()))::int FROM auth_throttle WHERE key_hash=%s",(hashlib.sha256(b'auth-ip:127.0.0.1').hexdigest(),)).fetchone()
        auth={'hits':q[0]if q else 0,'window_seconds_remaining':q[1]if q else 0,'limit':120}
        auth['blocked']=auth['hits']>120 and auth['window_seconds_remaining']>0
        docker=subprocess.run(['docker','info','--format','{{.ServerVersion}}'],capture_output=True,text=True,timeout=20)
        report={'measured_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'url':f.cfg['BASE_URL'],'health_status':public.status_code,'qwen_gpu':{k:gpu.get(k)for k in('name','size','size_vram')},'review_model_installed':any(m['name']==f.cfg['CODE_REVIEW_MODEL']for m in review),'review_model':f.cfg['CODE_REVIEW_MODEL'],'docker_version':docker.stdout.strip(),'auth_perimeter':auth,'passed':public.status_code==200 and bool(gpu) and gpu.get('size_vram',0)>=gpu.get('size',1) and docker.returncode==0 and not auth['blocked']}
        (ROOT/'validation/reports/current/runtime-ready.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False))
        return 0 if report['passed'] else 1
    finally:f.close()

if __name__=='__main__':raise SystemExit(main())
