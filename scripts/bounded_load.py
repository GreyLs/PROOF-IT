"""Actual bounded closed-loop HTTP concurrency; no LLM/OCR/model review jobs."""
from pathlib import Path
import concurrent.futures,json,math,platform,statistics,threading,time
import psutil
from scripts.workbench_test_fixture import Fixture
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'validation/reports/current'
def percentile(values,p):return sorted(values)[max(0,math.ceil(len(values)*p)-1)]
def main():
 f=Fixture(local_transport=True);sessions=30;iterations=1000;duration=30;clients=[];samples=[];barrier=threading.Barrier(sessions);lock=threading.Lock()
 try:
  for i in range(sessions):
   client,u=f.register('employer' if i%2 else 'candidate');client.timeout=30;clients.append((client,u))
  def run(pair):
   c,u=pair;paths=['/dashboard','/vacancies?limit=10','/notifications','/intelligence/assessment/catalog']
   if u['role']=='employer':paths[1]='/candidates?specialization=backend_python&limit=10'
   local=[];barrier.wait();deadline=time.perf_counter()+duration;tick=time.perf_counter()
   for i in range(iterations):
    if time.perf_counter()>=deadline:break
    pause=tick-time.perf_counter()
    if pause>0:time.sleep(pause)
    if time.perf_counter()>=deadline:break
    start=time.perf_counter();tick=start+.2
    try:r=c.get(paths[i%len(paths)]);code=r.status_code
    except Exception:code=0
    local.append({'endpoint':paths[i%len(paths)].split('?')[0],'status':code,'ms':(time.perf_counter()-start)*1000})
   with lock:samples.extend(local)
  start=time.perf_counter()
  with concurrent.futures.ThreadPoolExecutor(max_workers=sessions) as pool:list(pool.map(run,clients))
  elapsed=time.perf_counter()-start;times=[r['ms'] for r in samples];errors=sum(r['status']!=200 for r in samples)
  report={'measured_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'method':'paced closed-loop, 30 distinct authenticated sessions, 30 seconds, at most 5 requests/sec/session (offered ceiling 150 req/sec), synchronized start; local Rust gateway + actual PostgreSQL + CPU CAT catalog; no LLM/OCR requests; preserves real shared-IP perimeter limits','offered_ceiling_rps':150,'concurrent_sessions':sessions,'duration_budget_seconds':duration,'requests':len(samples),'errors':errors,'error_rate':errors/len(samples),'elapsed_seconds':round(elapsed,4),'throughput_rps':round(len(samples)/elapsed,2),'median_ms':round(statistics.median(times),3),'p95_ms':round(percentile(times,.95),3),'p99_ms':round(percentile(times,.99),3),'min_ms':round(min(times),3),'max_ms':round(max(times),3),'llm_calls':0,'capacity_extrapolated':False,'hardware':{'system':platform.platform(),'cpu':platform.processor(),'logical_cpus':psutil.cpu_count(),'ram_gib':round(psutil.virtual_memory().total/1024**3,1)},'by_endpoint':{}}
  for path in sorted({r['endpoint'] for r in samples}):
   subset=[r['ms'] for r in samples if r['endpoint']==path];report['by_endpoint'][path]={'requests':len(subset),'p95_ms':round(percentile(subset,.95),3),'median_ms':round(statistics.median(subset),3),'errors':sum(r['status']!=200 and r['endpoint']==path for r in samples)}
  OUT.mkdir(parents=True,exist_ok=True);(OUT/'bounded-load.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2));assert errors==0
 finally:f.close()
if __name__=='__main__':main()
