"""Append authored leadership fixtures to the demo DB; do not touch user profiles."""
from pathlib import Path
import os,csv,json
import psycopg
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[1];load_dotenv(ROOT/'.env')
assert os.getenv('FSP_DEMO_MODE')=='true'
def read(name):
 with (ROOT/'data'/f'{name}.csv').open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
with psycopg.connect(os.environ['DATABASE_URL']) as db:
 for r in read('employers'):
  if not r['company_id'].startswith('LE'):continue
  db.execute("INSERT INTO companies(id,name,description,industry,contact,synthetic) VALUES(%s,%s,%s,%s,'demo@company.example',true) ON CONFLICT DO NOTHING",(r['company_id'],r['company_name'],r['company_description'],r['industry']))
 for r in read('candidates'):
  if not r['candidate_id'].startswith('LC'):continue
  db.execute("INSERT INTO candidates(id,display_name,specialization,declared_grade,confirmed_grade,experience_years,skills,expected_salary,work_format,visibility,consent_processing,consent_publication,test_score,test_valid_until,grade_changed_at,about,synthetic,assessment_method) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'employer_searchable',true,true,%s,'2027-01-03',now()-interval '91 days',%s,true,'synthetic_scenario') ON CONFLICT DO NOTHING",(r['candidate_id'],r['display_name'],r['specialization'],r['current_grade'],r['current_grade'],r['experience_years'],r['skills'].split('; '),r['expected_salary_from_rub'],r['work_format'],r['test_score_pct'],r['resume_text']))
  db.execute("UPDATE candidates SET visibility=%s WHERE id=%s AND synthetic AND NOT EXISTS(SELECT 1 FROM users WHERE subject_id=candidates.id)",(r['profile_visibility'],r['candidate_id']))
 for r in read('vacancies'):
  if not r['vacancy_id'].startswith('LV'):continue
  db.execute("INSERT INTO vacancies(id,company_id,title,description,specialization,grade,skills,salary_from,salary_to,origin,source_ref,synthetic,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'authored_scenario',%s,true,'2026-10-06') ON CONFLICT DO NOTHING",(r['vacancy_id'],r['company_id'],r['title'],r['description'],r['specialization'],r['target_grade'],r['matching_requirement_profile'].split('; '),r['salary_from_rub'],r['salary_to_rub'],r['source_ref']))
 for r in read('assessment_attempts'):
  if not r['candidate_id'].startswith('LC'):continue
  db.execute("INSERT INTO assessments(id,candidate_id,specialization,grade,blueprint_version,seed,items,status,score,finished_at,synthetic) VALUES(%s,%s,%s,%s,%s,%s,'[]','completed_seed',%s,now()-interval '91 days',true) ON CONFLICT DO NOTHING",(r['attempt_id'],r['candidate_id'],r['specialization'],r['result_grade'],r['blueprint_id'],r['unique_parameter_seed'],r['score_pct']))
 print(json.dumps({'leadership_candidates':db.execute("SELECT count(*) FROM candidates WHERE id LIKE 'LC%' AND synthetic").fetchone()[0],'leadership_vacancies':db.execute("SELECT count(*) FROM vacancies WHERE id LIKE 'LV%' AND synthetic").fetchone()[0]}))
