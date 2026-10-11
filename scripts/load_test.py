"""Closed-loop HTTP workload. Reports measured limits, never extrapolated capacity."""
from pathlib import Path
import asyncio,time,json,statistics,random
import httpx,psutil
ROOT=Path(__file__).resolve().parents[1]
async def main():
    concurrency=50;requests=1000;latencies=[];errors=[];paths={};started=time.perf_counter()
    process=psutil.Process(int((ROOT/'runtime/api.pid').read_text()));rss_start=process.memory_info().rss
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8080/api',timeout=30,limits=httpx.Limits(max_connections=60,max_keepalive_connections=60)) as c:
        (await c.post('/auth/demo',json={'role':'employer'})).raise_for_status()
        sem=asyncio.Semaphore(concurrency)
        options=['/candidates?specialization=backend_python&limit=20','/candidates?specialization=devops&grade=middle&limit=20','/candidates?vacancy_id=RV0001&limit=5','/candidates/PC00057','/invitations','/vacancies?limit=30','/candidates?limit=12']
        async def one(index):
            async with sem:
                path=options[index%len(options)];t=time.perf_counter()
                try:
                    r=await c.get(path);elapsed=(time.perf_counter()-t)*1000;latencies.append(elapsed);paths.setdefault(path,[]).append(elapsed)
                    if r.status_code!=200:errors.append({'status':r.status_code,'path':path})
                except Exception as e:errors.append({'error':type(e).__name__,'path':path})
        await asyncio.gather(*(one(i) for i in range(requests)))
    elapsed=time.perf_counter()-started
    def percentile(values,p):return round(sorted(values)[min(len(values)-1,int(len(values)*p))],2)
    report={'concurrency':concurrency,'requests':requests,'errors':len(errors),'p50_ms':percentile(latencies,.50),'p95_ms':percentile(latencies,.95),'p99_ms':percentile(latencies,.99),'elapsed_seconds':round(elapsed,2),'requests_per_second':round(requests/elapsed,2),'rust_api_rss_mb':round(process.memory_info().rss/1024**2,2),'rss_start_mb':round(rss_start/1024**2,2),'workload':'50 closed-loop clients, 1000 authenticated requests: ranked category search, full-bank search, profile, invitations, vacancies. Localhost Windows i7-7700HQ/32 GB.','by_endpoint':{p:{'requests':len(v),'p95_ms':percentile(v,.95)} for p,v in paths.items()},'error_details':errors[:10]}
    (ROOT/'validation/reports/current/load-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':asyncio.run(main())
