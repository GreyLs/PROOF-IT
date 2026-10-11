"""Meaningful state/visibility security regressions; no mocked model outcomes."""
import json,uuid
from test_api import world

def test_case_phase_cannot_be_skipped_or_crossed(world):
    c,e,db=world['candidate'],world['employer'],world['db'];cid=world['cu']['subject_id']
    p=c.get('/profile').json()['profile'];did='cases-contract-'+uuid.uuid4().hex
    db.execute("INSERT INTO expert_dialogues(id,candidate_id,mode,specialization,grade,profile_version,snapshot,messages,question_count) VALUES(%s,%s,'profile','backend_python','middle',%s,'{}','[]',1)",(did,cid,p['version']))
    assert c.post('/dialogues/'+did+'/cases').status_code==409
    assert e.post('/dialogues/'+did+'/cases').status_code==403
    other,_=world['register']('candidate');assert other.post('/dialogues/'+did+'/cases').status_code==404
    db.execute("UPDATE expert_dialogues SET phase='cases',expires_at=now()-interval '1 second' WHERE id=%s",(did,))
    assert c.post('/dialogues/'+did+'/cases').status_code==409
    assert c.get('/profile').json()['profile']['confirmed_grade'] is None

def test_employment_block_is_server_owned_and_covers_search(world):
    c,e,db=world['candidate'],world['employer'],world['db'];cid=world['cu']['subject_id']
    p=c.get('/profile').json()['profile'];p.update(specialization='backend_python',declared_grade='middle',about='Реальный для теста синтетический профиль разработчика Python и PostgreSQL.',consent_publication=True,visibility='employer_searchable');c.put('/profile',json=p).raise_for_status()
    db.execute("UPDATE candidates SET confirmed_grade='middle',test_valid_until=now()+interval '1 day' WHERE id=%s",(cid,))
    assert e.get('/candidates/'+cid).status_code==200
    db.execute("UPDATE candidates SET employment_blocked=true,employment_check=%s WHERE id=%s",(json.dumps({'status':'mismatch','message':'Fixture mismatch'}),cid))
    assert e.get('/candidates/'+cid).status_code==404
    r=e.get('/candidates',params={'q':cid});r.raise_for_status();assert not any(x['id']==cid for x in r.json()['items'])
    p=c.get('/profile').json()['profile'];p.update(employment_blocked=False,employment_check={'status':'aligned'});c.put('/profile',json=p).raise_for_status()
    assert c.get('/profile').json()['profile']['employment_blocked'] is True
    assert e.post('/invitations',json={'candidate_id':cid,'title':'Test','description':'Synthetic offer','salary_from':100000,'salary_to':200000,'idempotency_key':uuid.uuid4().hex}).status_code in (400,404)
    db.execute('UPDATE candidates SET employment_blocked=false WHERE id=%s',(cid,))

def test_employment_upload_role_and_source_are_protected(world):
    c,e,db=world['candidate'],world['employer'],world['db'];uid=world['cu']['id'];cid=world['cu']['subject_id']
    assert e.post('/documents?kind=employment',files={'file':('x.pdf',b'%PDF-not-real','application/pdf')}).status_code==400
    did='employment-contract-'+uuid.uuid4().hex
    db.execute("INSERT INTO documents(id,user_id,kind,filename,sha256,storage_key,bytes,status,result) VALUES(%s,%s,'employment','fixture.pdf',%s,'synthetic-unused-object',0,'completed','{}')",(did,uid,uuid.uuid4().hex))
    assert c.put('/documents/'+did,json={'fields':{'position':'CTO'}}).status_code==404
    assert e.get('/documents/'+did).status_code==404
    db.execute("UPDATE candidates SET employment_document_id=%s,employment_blocked=true WHERE id=%s",(did,cid))
    assert c.delete('/documents/'+did).status_code==200
    p=c.get('/profile').json()['profile'];assert p['employment_blocked'] and p['employment_check']['status']=='source_removed'
    db.execute('UPDATE candidates SET employment_blocked=false WHERE id=%s',(cid,))
