"""Real HTTP latency, fixed closed-loop workload, both roles and new read paths.

Runs against the current gateway; no model inference or fake responses in load.
LLM and executable sandbox timings are measured separately by the e2e script.
"""
import asyncio, collections, json, math, platform, statistics, time, uuid
from pathlib import Path
import httpx, psutil
from scripts.workbench_test_fixture import Fixture
from tests.test_workbench import VACANCY
ROOT = Path(__file__).resolve().parents[1]

def percentile(values, p):
    return round(sorted(values)[max(0, math.ceil(len(values)*p)-1)], 2)

async def run(clients, options, requests=2000, concurrency=50):
    queue = asyncio.Queue()
    for i in range(requests): queue.put_nowait(i)
    samples=[]; errors=[]; by=collections.defaultdict(list)
    started=time.perf_counter()
    async def consumer():
        while not queue.empty():
            i=queue.get_nowait();role,path=options[i%len(options)];t=time.perf_counter()
            try:
                r=await clients[role].get(path);elapsed=(time.perf_counter()-t)*1000
                samples.append(elapsed);by[role+':'+path].append(elapsed)
                if r.status_code!=200:errors.append({'index':i,'role':role,'status':r.status_code,'path':path})
            except Exception as exc:errors.append({'index':i,'role':role,'error':type(exc).__name__})
    await asyncio.gather(*(consumer() for _ in range(concurrency)))
    elapsed=time.perf_counter()-started
    return {'requests':requests,'concurrency':concurrency,'errors':len(errors),'p50_ms':percentile(samples,.5),'p95_ms':percentile(samples,.95),'p99_ms':percentile(samples,.99),'elapsed_seconds':round(elapsed,3),'requests_per_second':round(requests/elapsed,2),'by_endpoint':{p:{'requests':len(v),'p50_ms':percentile(v,.5),'p95_ms':percentile(v,.95),'p99_ms':percentile(v,.99)} for p,v in by.items()},'error_details':errors,'workload':'2000 real authenticated gateway GET requests; 50 closed-loop clients; ranking, recommendations, market analytics, both forecasts, dashboards and notifications; same laptop load generator; no LLM/OCR in this load series.'}

def main():
    f=Fixture()
    try:
        c,cu=f.register('candidate');e,eu=f.register('employer');v=e.post('/vacancies',json=VACANCY);v.raise_for_status();vid=v.json()['vacancy']['id'];rid='PF'+uuid.uuid4().hex
        f.db.execute("INSERT INTO resume_profiles(id,candidate_id,target_position,specialization,declared_grade,experience_years,skills,about,expected_salary,visibility,status) VALUES(%s,%s,'Python developer','backend_python','middle',3,ARRAY['Python','PostgreSQL'],'Профиль нагрузочной проверки',200000,'private','draft')",(rid,cu['subject_id']))
        options=[('employer','/candidates?specialization=backend_python&limit=20'),('employer','/candidates?limit=12'),('employer','/vacancies?limit=30'),('employer','/dashboard'),('candidate','/dashboard'),('candidate','/notifications'),('candidate','/vacancies/recommended?resume_id='+rid+'&limit=5'),('employer','/vacancies/'+vid+'/market'),('employer','/forecasts/vacancy/'+vid),('candidate','/forecasts/job-search/'+rid)]
        async def workload():
            async with httpx.AsyncClient(base_url=f.cfg['BASE_URL']+'/api',headers=e.headers,trust_env=False,timeout=30,limits=httpx.Limits(max_connections=50,max_keepalive_connections=50)) as ae, httpx.AsyncClient(base_url=f.cfg['BASE_URL']+'/api',headers=c.headers,trust_env=False,timeout=30,limits=httpx.Limits(max_connections=50,max_keepalive_connections=50)) as ac:
                clients={'candidate':ac,'employer':ae};cold=[]
                for role,path in options:
                    t=time.perf_counter();r=await clients[role].get(path);r.raise_for_status();cold.append({'role':role,'endpoint':path,'first_request_ms':round((time.perf_counter()-t)*1000,2)})
                result=await run(clients,options);result['first_requests']=cold;return result
        report=asyncio.run(workload());report['measured_at']=time.strftime('%Y-%m-%dT%H:%M:%S%z');report['hardware']={'system':platform.platform(),'cpu':platform.processor(),'ram_gib':round(psutil.virtual_memory().total/1024**3,1),'gpu':'NVIDIA GeForce GTX 1070, 8 GiB'}
        report['service_rss_mb']={}
        for path in (ROOT/'runtime').glob('api-*.pid'):
            try:report['service_rss_mb'][path.stem]=round(psutil.Process(int(path.read_text())).memory_info().rss/1024**2,2)
            except psutil.Error:pass
        (ROOT/'validation/reports/current/performance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        (ROOT/'validation/reports/current/load-native-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k not in ('by_endpoint','first_requests','error_details')},ensure_ascii=False))
        assert report['errors']==0,report['error_details'][:5]
    finally:f.close()

if __name__=='__main__':main()
