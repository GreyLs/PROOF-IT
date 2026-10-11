"""Bounded new-feature local gateway load; 8 sessions, no external API or LLM."""
import concurrent.futures,json,math,threading,time
from pathlib import Path
from scripts.workbench_test_fixture import Fixture
from tests.test_workbench import VACANCY
ROOT=Path(__file__).resolve().parents[1]
def main():
    f=Fixture(local_transport=True);clients=[];barrier=threading.Barrier(8)
    try:
        for i in range(8):
            role='employer' if i%2 else 'candidate';c,u=f.register(role)
            if role=='employer':
                r=c.post('/vacancies',json=VACANCY);r.raise_for_status();vid=r.json()['vacancy']['id']
                paths=['/intelligence/research-lab/workspace','/intelligence/research-lab/market/'+vid,'/intelligence/research-lab/bilateral/'+vid,'/intelligence/research-lab/reliability/'+u['subject_id']]
            else:paths=['/intelligence/research-lab/workspace','/intelligence/research-lab/matrix/backend_python','/intelligence/graph','/intelligence/evidence-lab/workspace']
            for path in paths:c.get(path).raise_for_status()
            clients.append((c,paths))
        def run(pair):
            c,paths=pair;out=[];barrier.wait();deadline=time.perf_counter()+10;tick=time.perf_counter();i=0
            while time.perf_counter()<deadline:
                pause=tick-time.perf_counter()
                if pause>0:time.sleep(pause)
                if time.perf_counter()>=deadline:break
                start=time.perf_counter();tick=start+.2
                try:r=c.get(paths[i%4]);status=r.status_code
                except Exception:status=0
                out.append({'status':status,'ms':(time.perf_counter()-start)*1000,'route':i%4});i+=1
            return out
        start=time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:rows=[row for group in pool.map(run,clients) for row in group]
        elapsed=time.perf_counter()-start;latencies=sorted(r['ms'] for r in rows);errors=sum(r['status']!=200 for r in rows)
        report={'passed':errors==0,'measured_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'scope':'8 disposable authenticated sessions; real local gateway + DB + numerical engine; paced ceiling40req/s; warm-up; 10 seconds; no external API, OCR, Docker jobs or LLM','concurrent_sessions':8,'duration_seconds':elapsed,'requests':len(rows),'errors':errors,'throughput_rps':len(rows)/elapsed,'p95_ms':latencies[math.ceil(.95*len(rows))-1],'p99_ms':latencies[math.ceil(.99*len(rows))-1],'llm_calls':0,'capacity_extrapolated':False}
        (ROOT/'validation/reports/current/research-load.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report));assert errors==0
    finally:f.close()
if __name__=='__main__':main()
