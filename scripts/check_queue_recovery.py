"""Fault injection against a synthetic user's documents on the local demo service."""
from pathlib import Path
import os,uuid,time,json
import httpx,psycopg
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[1];load_dotenv(ROOT/'.env')
checks=[];created=[];uid=cid=None
db=psycopg.connect(os.environ['DATABASE_URL'],autocommit=True)
origin=os.environ['BASE_URL'].rstrip('/')
c=httpx.Client(headers={"Origin":origin},base_url=origin+'/api',timeout=30,trust_env=False)
def wait(did,status,seconds):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        r=c.get('/documents/'+did);r.raise_for_status();d=r.json()['document']
        if d['status'] in status:return d
        time.sleep(1)
    raise AssertionError(f'Job did not reach {status}; last status={d["status"]}')
try:
    r=c.post('/auth/register',json={'email':f'queue-{uuid.uuid4().hex}@example.test','password':'SyntheticQueue-Test-2026','role':'candidate','name':'Синтетическая проверка очереди','consent_processing':True});r.raise_for_status()
    u=c.post('/auth/verify',json={'token':r.json()['development_mail']['token']}).json()['user'];uid=u['id'];cid=u['subject_id']
    r=c.post('/documents?kind=resume',files={'file':('corrupt.pdf',b'%PDF-1.7\nnot a valid PDF\n','application/pdf')});r.raise_for_status();bad=r.json()['document']['id'];created.append(bad)
    failed=wait(bad,{'failed'},80);assert failed['attempts']==3
    checks.append('Corrupt PDF reaches failed after three bounded attempts; API stays healthy')
    assert c.get('/health').status_code==200
    with (ROOT/'tests/fixtures/candidate-text.pdf').open('rb') as f:r=c.post('/documents?kind=resume',files={'file':('lease-recovery.pdf',f,'application/pdf')})
    r.raise_for_status();good=r.json()['document']['id'];created.append(good)
    db.execute("UPDATE documents SET status='processing',worker_id='synthetic-crashed-worker',lease_until=now()-interval '1 minute',attempts=1 WHERE id=%s AND user_id=%s",(good,uid))
    recovered=wait(good,{'review','completed','failed'},120)
    assert recovered['status'] in {'review','completed'} and recovered['attempts']>=2
    assert recovered['result']['fields']['email']=='alexey@example.test'
    checks.append('Expired worker lease is reclaimed and produces a valid reviewed draft')
    retried=c.post('/documents/'+bad+'/retry');assert retried.status_code==200
    checks.append('Owner can retry failed job through API')
finally:
    if uid:
        db.execute('DELETE FROM documents WHERE user_id=%s',(uid,));db.execute('DELETE FROM audit_events WHERE actor_id=%s',(uid,));db.execute('DELETE FROM users WHERE id=%s',(uid,));db.execute('DELETE FROM candidates WHERE id=%s',(cid,))
    c.close();db.close()
report={'passed':True,'checks':checks}
(ROOT/'validation/reports/current/queue-recovery-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
