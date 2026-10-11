"""Bidirectional gold labels: transpose supplied relevance pairs for career search.

Source candidate profiles are copied into disposable private resumes; benchmark
answers are never passed to the API. Measures ranking against supplied labels,
and separately records coverage and salary compatibility of actual suggestions.
"""
import csv,gzip,json,math,re,statistics,subprocess,time,uuid
from pathlib import Path
from scripts.workbench_test_fixture import Fixture
from scripts.ranking_metrics import measures,aggregate
ROOT=Path(__file__).resolve().parents[1]

def main(report_path=None):
 candidates=list(csv.DictReader((ROOT/'data/candidates.csv').open(encoding='utf-8-sig')))
 selected={}
 for row in candidates:
  key=(row['specialization'],row['current_grade'])
  if row['profile_visibility']=='employer_searchable' and key not in selected:selected[key]=row
 lookup={x['candidate_id']:{}for x in selected.values()}
 with gzip.open(ROOT/'data/relevance_labels.csv.gz','rt',encoding='utf-8-sig')as f:
  for row in csv.DictReader(f):
   if row['candidate_id']in lookup:lookup[row['candidate_id']][row['vacancy_id']]=int(row['expected_relevance'])
 fixture=Fixture(local_transport=True);c,u=fixture.register('candidate');reports=[]
 try:
  for row in selected.values():
   rid='BR'+uuid.uuid4().hex;grade=row['current_grade']if row['current_grade']in('junior','middle','senior')else'senior';skills=[s.strip()for s in row['skills'].split(';')if s.strip()];salary=int(row['expected_salary_from_rub'])
   fixture.db.execute("INSERT INTO resume_profiles(id,candidate_id,target_position,specialization,declared_grade,experience_years,skills,about,expected_salary,visibility,status) VALUES(%s,%s,%s,%s,%s,%s,%s,'Изолированный профиль проверки',%s,'private','draft')",(rid,u['subject_id'],row['specialization'],row['specialization'],grade,float(row['experience_years']),skills,salary))
   start=time.perf_counter();r=c.get('/vacancies/recommended',params={'resume_id':rid,'limit':10});r.raise_for_status();all_items=r.json()['items'];items=all_items[:5];elapsed=(time.perf_counter()-start)*1000
   gold=lookup[row['candidate_id']];gains=[gold.get(x['vacancy']['id'],0)for x in items];ideal=sorted(gold.values(),reverse=True)[:5]
   dcg=lambda values:sum((2**v-1)/math.log2(i+2)for i,v in enumerate(values))
   reports.append({'specialization':row['specialization'],'grade':grade,'ndcg_at_5':dcg(gains)/dcg(ideal)if dcg(ideal)else 1,'precision_at_5':sum(v>=2 for v in gains)/5,'salary_compatible_top5':sum(x['vacancy']['salary_to']>=salary for x in items)/max(1,len(items)),'latency_ms':round(elapsed,2),'gold_pairs':len(gold),'extended':measures([gold.get(x['vacancy']['id'],0) for x in all_items],list(gold.values()))})
   fixture.db.execute('DELETE FROM resume_profiles WHERE id=%s',(rid,))
 finally:fixture.close()
 report={'queries':len(reports),'provided_gold_pairs':sum(r['gold_pairs']for r in reports),'precision_at_5':statistics.mean(r['precision_at_5']for r in reports),'ndcg_at_5':statistics.mean(r['ndcg_at_5']for r in reports),'salary_compatible_top5':statistics.mean(r['salary_compatible_top5']for r in reports),'p95_ms':sorted(r['latency_ms']for r in reports)[max(0,math.ceil(len(reports)*.95)-1)],'by_role_grade':reports,'method':'Supplied labels transposed; no labels given to API. Directional salary/grade preference may differ; this is measured rather than redefined.'}
 report['extended']=aggregate([r['extended'] for r in reports])
 Path(report_path or ROOT/'validation/reports/current/candidate-ranking.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in report.items()if k!='by_role_grade'}))
if __name__=='__main__':main()
