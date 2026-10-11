from scripts.private_runtime import private_file
"""Disposable authenticated fixture; authentication is tested in test_api.py.

Creates exact-ID demonstration identities/sessions directly in PostgreSQL to keep
feature verification independent of the 120/15min authentication perimeter quota.
Never alters throttles, existing users or production policy.
"""
import hashlib,secrets,uuid,os
import httpx,psycopg
from dotenv import dotenv_values
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class Fixture:
 def __init__(self,local_transport=False):
  self.cfg=dotenv_values(ROOT/'.env');assert self.cfg.get('FSP_DEMO_MODE')=='true'
  public=private_file('public-settings.json')
  if public.exists():
   import json
   self.cfg.update(json.loads(public.read_text(encoding='utf-8')))
  self.local_transport=(local_transport or os.environ.get('FSP_TEST_LOCAL_TRANSPORT')=='1') and public.exists()
  self.db=psycopg.connect(self.cfg['DATABASE_URL'],autocommit=True);self.users=[];self.clients=[]
 def register(self,role):
  suffix=uuid.uuid4().hex;subject='WV'+suffix;uid='WU'+suffix;email='fixture-'+suffix+'@example.test';token=secrets.token_hex(32)
  with self.db.transaction():
   if role=='candidate':self.db.execute("INSERT INTO candidates(id,display_name,consent_processing,synthetic) VALUES(%s,%s,true,true)",(subject,'Проверочный кандидат '+suffix[:6]))
   else:self.db.execute("INSERT INTO companies(id,name,contact,verification_status,synthetic) VALUES(%s,%s,'Демонстрационная связь','verified',true)",(subject,'Проверочная компания '+suffix[:6]))
   self.db.execute("INSERT INTO users(id,email,password_hash,role,email_verified,subject_id,synthetic) VALUES(%s,%s,'fixture-no-password',%s,true,%s,true)",(uid,email,role,subject))
   self.db.execute("INSERT INTO sessions(token_hash,user_id,expires_at,auth_epoch) SELECT %s,id,now()+interval '1 hour',auth_epoch FROM users WHERE id=%s",(hashlib.sha256(token.encode()).hexdigest(),uid))
  user={'id':uid,'subject_id':subject,'role':role};self.users.append(user)
  from urllib.parse import urlsplit
  origin=self.cfg['BASE_URL'];headers={'Origin':origin,'Authorization':'Bearer '+token}
  transport='http://'+self.cfg['BIND_ADDR'] if self.local_transport else origin
  if self.local_transport:headers['Host']=urlsplit(origin).netloc
  client=httpx.Client(base_url=transport+'/api',headers=headers,timeout=320,trust_env=False);self.clients.append(client);return client,user
 def close(self):
  subjects=[u['subject_id']for u in self.users];uids=[u['id']for u in self.users]
  with self.db.transaction():
   for query,args in [('DELETE FROM audit_events WHERE actor_id=ANY(%s)',(uids,)),('DELETE FROM private_conversations WHERE candidate_id=ANY(%s) OR company_id=ANY(%s)',(subjects,subjects)),('DELETE FROM micro_tasks WHERE candidate_id=ANY(%s) OR company_id=ANY(%s)',(subjects,subjects)),('DELETE FROM applications WHERE candidate_id=ANY(%s) OR vacancy_id IN(SELECT id FROM vacancies WHERE company_id=ANY(%s))',(subjects,subjects)),('DELETE FROM invitations WHERE candidate_id=ANY(%s) OR company_id=ANY(%s)',(subjects,subjects)),('DELETE FROM vacancies WHERE company_id=ANY(%s)',(subjects,)),('DELETE FROM users WHERE id=ANY(%s)',(uids,)),('DELETE FROM assessments WHERE candidate_id=ANY(%s)',(subjects,)),('DELETE FROM candidates WHERE id=ANY(%s)',(subjects,)),('DELETE FROM companies WHERE id=ANY(%s)',(subjects,))]:self.db.execute(query,args)
  for c in self.clients:c.close()
  self.db.close()
