"""Evaluate live Rust HTTP ranking against the supplied, separately stored oracle."""
from pathlib import Path
import csv,json,math,time,statistics,collections,concurrent.futures,gzip
import httpx
from dotenv import dotenv_values
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.workbench_test_fixture import Fixture
from scripts.ranking_metrics import measures,aggregate
def read(name):
    with (ROOT/'data'/name).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def main(report_path=None):
    start=time.perf_counter();vacancies=read('vacancies.csv');expected=collections.defaultdict(list)
    for r in read('expected_top5.csv'):expected[r['vacancy_id']].append(r['candidate_id'])
    labels=collections.defaultdict(dict)
    eligible={c['candidate_id'] for c in read('candidates.csv') if c['profile_visibility']=='employer_searchable'}
    labelpath=ROOT/'data/relevance_labels.csv'
    with (labelpath.open(encoding='utf-8-sig',newline='') if labelpath.exists() else gzip.open(str(labelpath)+'.gz','rt',encoding='utf-8-sig',newline='')) as f:
        for r in csv.DictReader(f):labels[r['vacancy_id']][r['candidate_id']]=int(r['expected_relevance'])
    origin=(dotenv_values(ROOT/'.env').get('BASE_URL') or 'http://127.0.0.1:80').rstrip('/')
    fixture=Fixture(local_transport=True); client,_=fixture.register('employer')
    def evaluate(v):
        t=time.perf_counter();res=client.get('/candidates',params={'vacancy_id':v['vacancy_id'],'limit':10});res.raise_for_status();items=res.json()['items'];all_ids=[x['id'] for x in items];ids=all_ids[:5];l=labels[v['vacancy_id']];all_gains=[l.get(x,0) for x in all_ids];gains=all_gains[:5]
        assert all(cid in eligible for cid in ids), 'A private source fixture leaked into search'
        available=[gain for cid,gain in l.items() if cid in eligible]
        dcg=sum((2**x-1)/math.log2(i+2) for i,x in enumerate(gains));ideal=sum((2**x-1)/math.log2(i+2) for i,x in enumerate(sorted(available,reverse=True)[:5]));relevant=sum(x>=2 for x in available)
        return {'vacancy_id':v['vacancy_id'],'specialization':v['specialization'],'precision':sum(x>=2 for x in gains)/5,'recall':sum(x>=2 for x in gains)/max(1,relevant),'ndcg':dcg/ideal if ideal else 1.,'exact':ids==expected[v['vacancy_id']],'latency_ms':(time.perf_counter()-t)*1000,'actual':ids,'expected':expected[v['vacancy_id']],'extended':measures(all_gains,available)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(evaluate,vacancies))
    report={'queries':len(results),'pairs':sum(len(x) for x in labels.values()),'precision_at_5':statistics.mean(x['precision'] for x in results),'recall_at_5':statistics.mean(x['recall'] for x in results),'ndcg_at_5':statistics.mean(x['ndcg'] for x in results),'exact_top5_rate':statistics.mean(x['exact'] for x in results),'elapsed_seconds':round(time.perf_counter()-start,2),'p95_ms':round(sorted(x['latency_ms'] for x in results)[int(.95*len(results))-1],2),'by_specialization':{},'mismatches':[x for x in results if not x['exact']][:20],'limitation':'Controlled synthetic oracle; validates the declared product policy, not independent market hiring quality. No labels are used by the API.'}
    for spec in sorted({x['specialization'] for x in results}):
        values=[x for x in results if x['specialization']==spec];report['by_specialization'][spec]={'queries':len(values),'precision_at_5':statistics.mean(x['precision'] for x in values),'ndcg_at_5':statistics.mean(x['ndcg'] for x in values)}
    report['extended']=aggregate([r['extended'] for r in results]);report['per_query_metrics']=[{'vacancy_id':r['vacancy_id'],**r['extended']} for r in results]
    Path(report_path or ROOT/'validation/reports/current/employer-ranking.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in report.items() if k not in ['by_specialization','mismatches','per_query_metrics']},ensure_ascii=False,indent=2));print('Mismatches:',len(report['mismatches']))
    fixture.close()
if __name__=='__main__':main()
