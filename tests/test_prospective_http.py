"""Real Rust/DB boundaries; disposable synthetic fixtures, not a human pilot."""
import pytest
from tests.test_resume_qualification import world,create_resume
from tests.test_evidence_http import accepted_offer
BASE='/intelligence/research-lab'

def freeze(e,vid,cid,stage='vacancy'):
 return e.post(BASE+'/bilateral/'+vid+'/freeze',json={'candidate_id':cid,'stage':stage})

def test_freeze_ownership_stage_and_immutable_prediction(world):
 c,e,o,db=world['candidate'],world['employer'],world['other'],world['db'];_,vid=accepted_offer(world);cid=world['cu']['subject_id']
 assert freeze(c,vid,cid).status_code==403 and freeze(o,vid,cid).status_code==404
 assert freeze(e,vid,'unrelated').status_code==404 and freeze(e,vid,cid,'hire').status_code==400
 row=freeze(e,vid,cid);row.raise_for_status();value=row.json()
 assert value['prediction']['context']=={'role':'backend_python','grade':'middle'}
 assert value['synthetic'] and value['model_version']=='bilateral-market-1.0.0'
 assert freeze(e,vid,cid).status_code==409
 with pytest.raises(Exception):
  with db.transaction():db.execute("UPDATE intelligence.prospective_predictions SET prediction='{}' WHERE id=%s",(value['id'],))
 assert db.execute('SELECT prediction FROM intelligence.prospective_predictions WHERE id=%s',(value['id'],)).fetchone()['prediction']==value['prediction']
 assert freeze(e,vid,cid,'offer').status_code==200

def test_first_paired_outcome_is_sealed_and_account_export_is_scoped(world):
 c,e,o,db=world['candidate'],world['employer'],world['other'],world['db'];_,vid=accepted_offer(world);cid=world['cu']['subject_id']
 row=freeze(e,vid,cid).json();id=row['id']
 c.post(BASE+'/bilateral/'+vid+'/decision',json={'stage':'vacancy','accepts':True}).raise_for_status()
 assert db.execute('SELECT count(*) n FROM intelligence.prospective_outcomes WHERE prediction_id=%s',(id,)).fetchone()['n']==0
 e.post(BASE+'/bilateral/'+vid+'/decision',json={'stage':'vacancy','accepts':False,'candidate_id':cid}).raise_for_status()
 sealed=db.execute('SELECT * FROM intelligence.prospective_outcomes WHERE prediction_id=%s',(id,)).fetchone()
 assert sealed['candidate_accepts']and not sealed['employer_accepts']
 c.post(BASE+'/bilateral/'+vid+'/decision',json={'stage':'vacancy','accepts':False}).raise_for_status()
 e.post(BASE+'/bilateral/'+vid+'/decision',json={'stage':'vacancy','accepts':True,'candidate_id':cid}).raise_for_status()
 assert db.execute('SELECT * FROM intelligence.prospective_outcomes WHERE prediction_id=%s',(id,)).fetchone()==sealed
 with pytest.raises(Exception):
  with db.transaction():db.execute('UPDATE intelligence.prospective_outcomes SET candidate_accepts=false WHERE prediction_id=%s',(id,))
 report=e.get(BASE+'/validation/forecast');report.raise_for_status()
 assert report.json()['excluded']['synthetic']==1 and report.json()['complete_pairs']==0
 assert c.get(BASE+'/validation/export').status_code==403
 assert not o.get(BASE+'/validation/export').json()['records']
 export=e.get(BASE+'/validation/export').json();assert export['records'][0]['candidate_accepts']is True
 account=c.get('/account/export').json();assert account['research_lab']['prospective_predictions'][0]['id']==id
 assert not o.get('/account/export').json()['research_lab']['prospective_predictions']

def test_outcome_first_rejects_retrospective_prediction(world):
 c,e=world['candidate'],world['employer'];_,vid=accepted_offer(world);cid=world['cu']['subject_id']
 c.post(BASE+'/bilateral/'+vid+'/decision',json={'stage':'vacancy','accepts':True}).raise_for_status()
 assert freeze(e,vid,cid).status_code==409
 assert freeze(e,vid,cid,'offer').status_code==200
 assert not e.get(BASE+'/validation/export?stage=vacancy').json()['records']
 assert e.get(BASE+'/validation/export?stage=offer').json()['records'][0]['stage']=='offer'
 assert e.get(BASE+'/validation/export?stage=hire').status_code==400

def test_new_application_response_timestamp_not_invented_for_legacy(world):
 c,e,db=world['candidate'],world['employer'],world['db'];_,vid=accepted_offer(world)
 resume=db.execute('SELECT id FROM resume_profiles WHERE candidate_id=%s',(world['cu']['subject_id'],)).fetchone()['id']
 response=c.post('/vacancies/'+vid+'/apply',json={'resume_id':resume,'message':'Контрольный тест нового наблюдения'});response.raise_for_status();id=response.json()['application']['id']
 e.put('/applications/'+id,json={'status':'viewed'}).raise_for_status()
 first=db.execute('SELECT first_employer_response_at FROM applications WHERE id=%s',(id,)).fetchone()['first_employer_response_at'];assert first is not None
 e.put('/applications/'+id,json={'status':'interview'}).raise_for_status()
 assert db.execute('SELECT first_employer_response_at FROM applications WHERE id=%s',(id,)).fetchone()['first_employer_response_at']==first
 r=e.get(BASE+'/reliability/'+world['eu']['subject_id']).json();assert r['indicators']['response']['accepted']==1
 # Only this disposable fixture becomes an old status-only record. Unknown is censored.
 db.execute('UPDATE applications SET first_employer_response_at=NULL,created_at=now()-interval \'10 days\' WHERE id=%s',(id,))
 r=e.get(BASE+'/reliability/'+world['eu']['subject_id']).json();assert r['indicators']['response']['observed']==0 and r['indicators']['response']['censored_excluded']==1

def test_empty_report_never_claims_calibration(world):
 e=world['employer'];r=e.get(BASE+'/validation/forecast');r.raise_for_status()
 assert r.json()['status']=='awaiting_real_observations'
 assert not r.json()['production_calibration_authorized']and not r.json()['real_employment_validated']

def test_concurrent_freezes_reuse_bounded_pool_without_deadlock(world):
 from concurrent.futures import ThreadPoolExecutor
 from psycopg.types.json import Jsonb
 from scripts.workbench_test_fixture import Fixture
 f=Fixture()
 try:
  e=world['employer'];_,vid=accepted_offer(world);ids=[world['cu']['subject_id']]
  for _ in range(3):
   _,user=f.register('candidate');ids.append(user['subject_id'])
   # Owned synthetic existing-process fixtures, not client-provided qualifications.
   world['db'].execute("INSERT INTO applications(id,vacancy_id,candidate_id,status,message) VALUES(%s,%s,%s,'sent','controlled concurrency')",('AP'+user['id'],vid,user['subject_id']))
  with ThreadPoolExecutor(max_workers=4)as pool:
   results=list(pool.map(lambda cid:freeze(e,vid,cid),ids))
  assert all(r.status_code==200 for r in results),[r.status_code for r in results]
  assert len({r.json()['id']for r in results})==4
 finally:f.close()
