"""Live persisted proof graph, independent review and lifecycle contracts; no LLM."""
import json,time,uuid
from datetime import datetime,timezone
import pytest
from psycopg.types.json import Jsonb
from tests.test_resume_qualification import world,create_resume,complete
BASE='/intelligence/evidence-lab'

def test_private_certificate_cannot_leak_into_public_graph(world):
 c,e,db=world['candidate'],world['employer'],world['db'];cid=world['cu']['subject_id']
 private=create_resume(c,1).json()['resume'];complete(c,db,private['id'])
 db.execute("UPDATE candidates SET consent_publication=true WHERE id=%s",(cid,))
 response=create_resume(c,2,visibility='employer_searchable',spec='frontend_development');response.raise_for_status();public=response.json()['resume']
 db.execute("UPDATE resume_profiles SET status='published' WHERE id=%s",(public['id'],))
 assert e.get('/intelligence/graph/candidate/'+cid).status_code==404
 assert db.execute('SELECT count(*) n FROM intelligence.skill_support WHERE candidate_id=%s',(cid,)).fetchone()['n']==0
 assert any(x['source']=='qualification' for x in c.get('/intelligence/graph').json()['evidence'])
 complete(c,db,public['id'])
 r=e.get('/intelligence/graph/candidate/'+cid);r.raise_for_status()
 assert sum(x['source']=='qualification' for x in r.json()['evidence'])==1

def test_certificate_hidden_or_revoked_invalidates_live_passport(world):
 c,db=world['candidate'],world['db'];r=create_resume(c,1).json()['resume'];complete(c,db,r['id'])
 p=c.post(BASE+'/passport').json();token=p['credential']['token']
 cert=db.execute('SELECT id FROM qualification_certificates WHERE resume_id=%s',(r['id'],)).fetchone()['id']
 control='/intelligence/evidence/cert:'+cert
 x=c.put(control,json={'hidden':True,'reason':'Управление видимостью доказательства'});x.raise_for_status()
 assert not c.post(BASE+'/passport/verify',json={'token':token}).json()['valid']
 c.put(control,json={'hidden':False,'disputed':False}).raise_for_status()
 assert c.post(BASE+'/passport/verify',json={'token':token}).json()['valid']
 db.execute('UPDATE qualification_certificates SET revoked_at=now() WHERE id=%s',(cert,))
 assert not c.post(BASE+'/passport/verify',json={'token':token}).json()['valid']

def test_review_requires_approved_independent_expert_and_reason(world):
 c,e,o,db=world['candidate'],world['employer'],world['other'],world['db'];uid=world['cu']['id'];eid=world['eu']['id'];rid='RV'+uuid.uuid4().hex
 arena=c.post('/intelligence/arena',json={'kind':'python','seed':9});arena.raise_for_status();aid=arena.json()['id']
 db.execute("UPDATE intelligence.arena_attempts SET status='completed',result=%s WHERE id=%s",(Jsonb({'score':100}),aid))
 db.execute("INSERT INTO intelligence.review_cases(id,user_id,artifact_id,task_key,evidence) VALUES(%s,%s,%s,'python:one',%s)",(rid,uid,aid,Jsonb({'signal':'controlled-copy'})))
 assert any(x['id']=='arena:'+aid for x in c.get('/intelligence/graph').json()['evidence'])
 assert not e.get(BASE+'/reviews').json()['can_review']
 db.execute('INSERT INTO intelligence.assessment_experts(user_id,approved) VALUES(%s,false)',(eid,))
 assert e.post(BASE+'/reviews/'+rid+'/resolve',json={'status':'confirmed','reason':'Проверка исполненного кода и независимое заключение'}).status_code==403
 db.execute('UPDATE intelligence.assessment_experts SET approved=true WHERE user_id=%s',(eid,))
 db.execute('INSERT INTO intelligence.assessment_experts(user_id,approved) VALUES(%s,true)',(uid,))
 assert c.post(BASE+'/reviews/'+rid+'/resolve',json={'status':'confirmed','reason':'Самопроверка недопустима, требуется независимый эксперт'}).status_code==409
 assert o.get(BASE+'/reviews').json()['items']==[]
 e.post(BASE+'/reviews/'+rid+'/resolve',json={'status':'confirmed','reason':'Совпадение проверено по контексту задачи и самостоятельной реализации'}).raise_for_status()
 assert not any(x['id']=='arena:'+aid for x in c.get('/intelligence/graph').json()['evidence'])
 c.post(BASE+'/reviews/'+rid+'/challenge',json={'reason':'Представляю собственное объяснение алгоритма и историю изменений'}).raise_for_status()
 assert c.get(BASE+'/reviews').json()['items'][0]['status']=='challenged'
 assert c.get(BASE+'/reviews').json()['items'][0]['established_violation']
 assert not any(x['id']=='arena:'+aid for x in c.get('/intelligence/graph').json()['evidence'])
 e.post(BASE+'/reviews/'+rid+'/resolve',json={'status':'dismissed','reason':'Независимая повторная проверка приняла объяснение автора и историю изменений'}).raise_for_status()
 assert any(x['id']=='arena:'+aid for x in c.get('/intelligence/graph').json()['evidence'])

def accepted_offer(world):
 e,c=world['employer'],world['candidate'];cid=world['cu']['subject_id']
 world['db'].execute('UPDATE candidates SET consent_publication=true WHERE id=%s',(cid,))
 r=create_resume(c,1,visibility='employer_searchable').json()['resume']
 complete(c,world['db'],r['id'])
 world['db'].execute("UPDATE resume_profiles SET status='published' WHERE id=%s",(r['id'],))
 v=e.post('/vacancies',json={'title':'Инженер Python API','description':'Разработка и тестирование Python API, SQL и транзакций.','specialization':'backend_python','grade':'middle','skills':['Python','SQL'],'salary_from':180000,'salary_to':250000,'work_format':'удалённо','status':'published'});v.raise_for_status();vid=v.json()['vacancy']['id']
 offer=e.post('/invitations',json={'candidate_id':cid,'vacancy_id':vid,'title':'Совместная разработка API','description':'Приглашение обсудить профессиональные задачи и условия','salary_from':180000,'salary_to':250000,'idempotency_key':uuid.uuid4().hex});offer.raise_for_status();oid=offer.json()['invitation']['id']
 x=c.put('/invitations/'+oid,json={'status':'accepted'});x.raise_for_status()
 return oid,vid

def test_followups_are_bilateral_idempotent_and_private(world):
 c,e,o=world['candidate'],world['employer'],world['other'];oid,_=accepted_offer(world)
 payload={'invitation_id':oid,'started_at':datetime.now(timezone.utc).isoformat()}
 assert o.post(BASE+'/followups',json=payload).status_code==404
 c.post(BASE+'/followups',json=payload).raise_for_status();e.post(BASE+'/followups',json=payload).raise_for_status()
 rows=c.get(BASE+'/followups').json()['items'];assert sorted(x['day'] for x in rows)==[30,60,90]
 fid=rows[0]['id'];assert o.put(BASE+'/followups/'+fid,json={'result':{'quality':5}}).status_code==404
 c.put(BASE+'/followups/'+fid,json={'result':{'tasks_completed':3}}).raise_for_status();e.put(BASE+'/followups/'+fid,json={'result':{'review':'Приняты результаты'}}).raise_for_status()
 x=c.get(BASE+'/followups').json()['items'][0];assert x['confirmed_by_candidate'] and x['confirmed_by_employer']
 assert set(x['result'])=={'candidate','employer'}

def test_weekly_campaign_produces_one_gap_task_and_no_duplicate(world):
 c,e,o,db=world['candidate'],world['employer'],world['other'],world['db'];_,vid=accepted_offer(world)
 # Knowledge is now actually certified in accepted_offer. Give the campaign
 # an unverified requirement; it must not retest already-proven Python/SQL.
 db.execute("UPDATE vacancies SET skills=ARRAY['Python','SQL','TypeScript'] WHERE id=%s",(vid,))
 assert o.post(BASE+'/weekly-campaigns',json={'vacancy_id':vid,'enabled':True}).status_code==404
 e.post(BASE+'/weekly-campaigns',json={'vacancy_id':vid,'enabled':True}).raise_for_status()
 for _ in range(70):
  tasks=c.get('/tasks').json()['items']
  if tasks:break
  time.sleep(.5)
 else:raise AssertionError('The actual weekly dispatcher did not offer a task within 35s')
 assert len(tasks)==1 and 'reference_solution' not in json.dumps(tasks)
 row=db.execute('SELECT contract FROM micro_tasks WHERE id=%s',(tasks[0]['id'],)).fetchone();assert 'TypeScript' in row['contract']['skills']
 db.execute("UPDATE intelligence.weekly_campaigns SET next_run_at=now() WHERE vacancy_id=%s",(vid,))
 # Dispatch cycle is 30s; bounded wait checks the persisted seven-day dedup.
 time.sleep(31)
 assert len(c.get('/tasks').json()['items'])==1
