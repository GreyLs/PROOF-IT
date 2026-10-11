"""Sequential authenticated HTTP/module latency samples, not a capacity test."""
import json, math, platform, statistics, time, uuid
from pathlib import Path
import psutil
from scripts.workbench_test_fixture import Fixture
from tests.test_workbench import VACANCY
from intelligence import professional,needs,integrity

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'validation/reports/current'

def summary(values):
    v=sorted(values);return {'samples':len(v),'min_ms':round(min(v),4),'median_ms':round(statistics.median(v),4),'p95_ms':round(v[max(0,math.ceil(len(v)*.95)-1)],4),'p99_ms':round(v[max(0,math.ceil(len(v)*.99)-1)],4),'max_ms':round(max(v),4)}

def main():
    f=Fixture(local_transport=True);report={'measured_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'concurrency':1,'capacity_test_run':False,'method':'15 sequential requests per authenticated endpoint after one explicitly reported first request; no parallel session load, no peak throughput claim. Module tests are direct local CPU calls, not HTTP or GPU latency.','hardware':{'system':platform.platform(),'cpu':platform.processor(),'logical_cpus':psutil.cpu_count(),'ram_gib':round(psutil.virtual_memory().total/1024**3,1)},'by_endpoint':{},'modules':{},'requests':0,'errors':0}
    try:
        c,cu=f.register('candidate');e,eu=f.register('employer');v=e.post('/vacancies',json=VACANCY);v.raise_for_status();vid=v.json()['vacancy']['id'];rid='LT'+uuid.uuid4().hex
        f.db.execute("INSERT INTO resume_profiles(id,candidate_id,target_position,specialization,declared_grade,experience_years,skills,about,expected_salary,work_format,visibility,status) VALUES(%s,%s,'Python Backend','backend_python','middle',3,ARRAY['Python','PostgreSQL'],'Контроль времени API',180000,'удалённо','private','draft')",(rid,cu['subject_id']))
        paths=[(e,'search','/candidates?specialization=backend_python&limit=20'),(e,'vacancies','/vacancies?limit=30'),(e,'employer_dashboard','/dashboard'),(c,'candidate_dashboard','/dashboard'),(c,'notifications','/notifications'),(c,'recommendations','/vacancies/recommended?resume_id='+rid+'&limit=5'),(e,'market','/vacancies/'+vid+'/market'),(e,'vacancy_forecast','/forecasts/vacancy/'+vid),(c,'job_search_forecast','/forecasts/job-search/'+rid),(c,'professional_catalog','/intelligence/assessment/catalog')]
        all_samples=[]
        for client,name,path in paths:
            first=time.perf_counter();r=client.get(path);r.raise_for_status();cold=(time.perf_counter()-first)*1000;values=[]
            for _ in range(15):
                start=time.perf_counter();r=client.get(path);values.append((time.perf_counter()-start)*1000);report['requests']+=1
                if r.status_code!=200:report['errors']+=1
            report['by_endpoint'][name]={**summary(values),'first_request_ms':round(cold,4)};all_samples.extend(values)
        report.update(summary(all_samples))
        contract=professional.create({'seed':1729,'specialization':'backend_python','mode':'express'})
        full=professional.create({'seed':1730,'specialization':'backend_python','mode':'full'})
        while (question:=professional.next_item(full)) is not None:
            full=professional.step({'contract':full,'question_id':question['id'],'answer':question['correct'],'elapsed_ms':8000})['contract']
        report['module_contracts']={'cat_eap_start_answers':0,'cat_eap_completed_answers':len(full['answers']),'cat_next_item_start_answers':0,'fingerprint':'four source lines; small function, not a 20 KB worst-case'}
        calls={'cat_eap_start':lambda:professional.estimate(contract),'cat_eap_completed':lambda:professional.estimate(full),'cat_next_item_start':lambda:professional.next_item(contract),'need_parse':lambda:needs.parse({'text':'Нужен Python / Backend Middle, PostgreSQL, 180–250 тыс руб, удалённо'}),'structural_fingerprint':lambda:integrity.fingerprint({'code':'def solve(data):\n    return sorted(set(data))\n'})}
        for name,fn in calls.items():
            values=[];fn()
            for _ in range(100):
                start=time.perf_counter();fn();values.append((time.perf_counter()-start)*1000)
            report['modules'][name]=summary(values)
        report['passed']=report['errors']==0
    finally:
        f.close();(OUT/'performance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
    assert report['passed']

if __name__=='__main__':main()
