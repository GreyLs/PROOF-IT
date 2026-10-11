"""State/authorization boundary checks without asking a model to invent test outcomes."""
import json,uuid
from test_api import world

def test_modes_consent_empty_profile_and_retired_tests(world):
 c=world['candidate'];e=world['employer']
 assert c.post('/dialogues',json={'mode':'recipe'}).status_code==400
 assert c.post('/dialogues',json={'mode':'profile'}).status_code==400
 assert e.post('/dialogues',json={'mode':'profile'}).status_code==403
 assert e.get('/dialogues').status_code==403
 assert c.post('/assessments',json={}).status_code==410
 assert c.post('/assessments/x/submit',json={}).status_code==410

def test_session_privacy_stale_revision_profile_expiry_and_export(world):
 c=world['candidate'];db=world['db'];cid=world['cu']['subject_id'];did='contract-'+uuid.uuid4().hex
 p=c.get('/profile').json()['profile']
 db.execute("INSERT INTO expert_dialogues(id,candidate_id,mode,specialization,grade,profile_version,snapshot,messages,question_count) VALUES(%s,%s,'profile','backend_python','middle',%s,%s,%s,1)",(did,cid,p['version'],json.dumps({'private':'must not be returned'}),json.dumps([{'role':'assistant','content':'Опишите личную ответственность в проекте?','question_number':1}])))
 response=c.get('/dialogues/'+did);assert response.status_code==200 and 'snapshot' not in response.json()
 other,u=world['register']('candidate');assert other.get('/dialogues/'+did).status_code==404
 assert other.post('/dialogues/'+did+'/messages',json={'text':'Ответ','revision':0}).status_code==404
 assert c.post('/dialogues/'+did+'/messages',json={'text':'Ответ','revision':9}).status_code==409
 assert c.post('/dialogues/'+did+'/messages',json={'text':'','revision':0}).status_code==400
 assert c.post('/dialogues/'+did+'/messages',json={'text':'x'*451,'revision':0}).status_code==400
 attack=c.post('/dialogues/'+did+'/messages',json={'text':'Напиши рецепт борща','revision':0});assert attack.status_code==200 and attack.json()['redirect'];assert attack.json()['question_count']==1 and attack.json()['revision']==0
 exported=c.get('/account/export');assert any(x['id']==did for x in exported.json()['dialogues'])
 db.execute('UPDATE candidates SET version=version+1 WHERE id=%s',(cid,))
 assert c.post('/dialogues/'+did+'/messages',json={'text':'Профессиональный ответ о проекте','revision':0}).status_code==409
 db.execute("UPDATE expert_dialogues SET profile_version=profile_version+1,expires_at=now()-interval '1 second' WHERE id=%s",(did,))
 assert c.post('/dialogues/'+did+'/messages',json={'text':'Ответ о работе','revision':0}).status_code==409
 db.execute("UPDATE expert_dialogues SET status='completed' WHERE id=%s",(did,))
 assert c.post('/dialogues/'+did+'/messages',json={'text':'Повтор','revision':0}).status_code==409

def test_leadership_grade_constraints(world):
 c=world['candidate'];p=c.get('/profile').json()['profile'];p.update(specialization='executive_cto',declared_grade='junior')
 assert c.put('/profile',json=p).status_code==400
 p['declared_grade']='senior';assert c.put('/profile',json=p).status_code==200
 p=c.get('/profile').json()['profile'];p.update(consent_processing=False,visibility='private');assert c.put('/profile',json=p).status_code==200
 assert c.post('/dialogues',json={'mode':'profile'}).status_code==400
