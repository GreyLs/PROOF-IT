"""Live adaptive qualification, immutable grade, replay and cooldown contracts."""
import json,uuid
from pathlib import Path
import pytest
from psycopg.rows import dict_row
from scripts.workbench_test_fixture import Fixture
from intelligence import professional

@pytest.fixture
def world():
 f=Fixture();f.db.row_factory=dict_row;c,cu=f.register('candidate');e,eu=f.register('employer');o,ou=f.register('employer')
 yield {'candidate':c,'cu':cu,'employer':e,'eu':eu,'other':o,'ou':ou,'db':f.db}
 f.close()

def create_resume(c,idx,visibility='private',grade='middle',spec='backend_python'):
 return c.post('/resumes',json={'target_position':f'Backend Engineer {idx}','specialization':spec,'declared_grade':grade,'experience_years':4,'skills':['Python','PostgreSQL','SQL'],'about':'Проектировал API и проверял качество результата в команде разработки.','expected_salary':180000,'work_format':'удалённо','visibility':visibility})
def complete(c,db,id,correct=True):
 state=c.post(f'/resumes/{id}/test/start');state.raise_for_status();last=None
 while state.json()['status']=='in_progress':
  row=db.execute('SELECT contract FROM qualification_tests WHERE resume_id=%s',(id,)).fetchone();q=professional.next_item(row['contract']);body=state.json()
  assert len(body['questions'])==1 and q['id']==body['question_id']
  assert 'correct' not in json.dumps(body['questions']) and 'bank' not in body
  # Vary the controlled server-owned duration: constant millisecond timing is
  # deliberately routed to review by response_patterns. This fixture tests
  # normal issuance; suspicious timing has independent screening tests.
  # No elapsed time is accepted from a candidate HTTP request.
  index=len(row['contract']['answers'])
  elapsed_ms=10000+1700*(index%5)+2300*(index%3)
  db.execute("UPDATE qualification_tests SET item_started_at=now()-(%s*interval '1 millisecond') WHERE resume_id=%s",(elapsed_ms,id))
  last={'question_id':q['id'],'revision':body['revision'],'answers':[[q['correct'] if correct else (q['correct']+1)%4]]}
  state=c.post(f'/resumes/{id}/test/submit',json=last);state.raise_for_status()
 return state.json(),last

def test_three_resume_limit_single_item_and_hidden_key(world):
 c,db=world['candidate'],world['db'];rows=[]
 for index in range(3):r=create_resume(c,index);r.raise_for_status();rows.append(r.json()['resume'])
 assert create_resume(c,4).status_code==409
 body,last=complete(c,db,rows[0]['id']);assert body['passed'] and body['score']==100 and 20<=len(body['review']['questions'])<=32
 assert c.post(f"/resumes/{rows[0]['id']}/test/submit",json=last).status_code==409

def test_failed_attempt_cooldown_survives_resume_edits_and_new_resume(world):
 c,db=world['candidate'],world['db'];r=create_resume(c,1).json()['resume'];body,_=complete(c,db,r['id'],False)
 assert not body['passed'] and body['score']==0 and body['status']=='cooldown'
 r['expected_salary']=190000;c.put('/resumes/'+r['id'],json=r).raise_for_status()
 assert c.post('/resumes/'+r['id']+'/test/start').status_code==409
 other=create_resume(c,2).json()['resume'];assert c.post('/resumes/'+other['id']+'/test/start').status_code==409
 assert world['other'].get('/resumes/'+r['id']+'/test').status_code==403

def test_completed_review_and_expert_appeal(world):
 c,db=world['candidate'],world['db'];r=create_resume(c,1).json()['resume'];body,_=complete(c,db,r['id'])
 assert all(q['is_correct'] and q['answer']==q['correct'] for q in body['review']['questions'])
 reply=c.post('/resumes/'+r['id']+'/test/expert-review');reply.raise_for_status();assert reply.json()['review_requested']
 row=db.execute('SELECT folder_key FROM qualification_expert_reviews WHERE resume_id=%s',(r['id'],)).fetchone();assert row and Path('runtime/storage',row['folder_key']).is_file()

def test_verified_grade_cannot_be_promoted_by_editing(world):
 c,db=world['candidate'],world['db'];r=create_resume(c,1).json()['resume'];complete(c,db,r['id'])
 r['declared_grade']='senior';assert c.put('/resumes/'+r['id'],json=r).status_code==409
 duplicate=create_resume(c,2,grade='senior').json()['resume'];assert c.post('/resumes/'+duplicate['id']+'/test/start').status_code==409
 row=db.execute('SELECT grade,skills FROM qualification_certificates WHERE resume_id=%s',(r['id'],)).fetchone();assert row['grade']=='middle' and set(row['skills'])=={'Python','SQL'}

def test_passport_signature_ownership_revocation_and_visibility(world):
 c,e,db=world['candidate'],world['employer'],world['db'];r=create_resume(c,1).json()['resume'];complete(c,db,r['id']);base='/intelligence/evidence-lab'
 out=c.post(base+'/passport');out.raise_for_status();p=out.json();token=p['credential']['token']
 assert e.post(base+'/passport/verify',json={'token':token}).json()['valid']
 assert e.post(base+'/passport/'+p['id']+'/revoke').status_code==404
 c.post(base+'/passport/'+p['id']+'/revoke').raise_for_status();assert not e.post(base+'/passport/verify',json={'token':token}).json()['valid']

def test_no_external_achievement_or_rating_is_invented(world):
 c,e=world['candidate'],world['employer'];x=c.post('/fsp/participations',json={'event_name':'Кубок ФСП','discipline':'спортивное программирование','event_date':'2026-09-20','result':'финал','source_url':'https://example.test/protocol'});x.raise_for_status();assert x.json()['participation']['status']=='declared'
 e.put('/intelligence/providers/dreamjob',json={'employer_id':'1234'}).raise_for_status();r=e.post('/intelligence/providers/sync/dreamjob');r.raise_for_status();assert r.json()['status']=='not_connected' and r.json()['ranking_effect']==0
 assert e.put('/intelligence/providers/dreamjob',json={'employer_id':'https://attacker.test'}).status_code==400

def test_company_twin_allocation_and_prohibited_features(world):
 e,c=world['employer'],world['candidate'];base='/intelligence/evidence-lab'
 assert c.put(base+'/company-twin',json={'pace':'stable'}).status_code==403
 assert e.put(base+'/company-twin',json={'gender':'male'}).status_code==400
 r=e.put(base+'/company-twin',json={'pace':'stable','collaboration':'team','growth':'expert','response_days':1,'interview_stages':2});r.raise_for_status();assert r.json()['twin']['version']==1
 r=e.post(base+'/allocation');r.raise_for_status();assert r.json()['assignments']==[]

def test_leadership_vacancy_has_no_grade(world):
 e=world['employer'];base={'title':'Тимлид платформы','description':'Развитие платформы и управление инженерной командой.','specialization':'lead_engineering','skills':['Python','Architecture'],'salary_from':250000,'salary_to':400000,'work_format':'гибрид','status':'published'}
 assert e.post('/vacancies',json={**base,'grade':'senior'}).status_code==400
 r=e.post('/vacancies',json={**base,'grade':''});r.raise_for_status();assert r.json()['vacancy']['grade']==''
