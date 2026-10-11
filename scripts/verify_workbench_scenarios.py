"""End-to-end real Qwen/GPT-OSS flow, sandbox abuse cases, and source-bound evidence.
Creates disposable identities and removes only their exact IDs in finally.
"""
from pathlib import Path
import asyncio,hashlib,json,os,time,uuid
import httpx,psycopg
from dotenv import dotenv_values
from psycopg.types.json import Jsonb
from worker.workbench import sandbox,redact
from scripts.workbench_test_fixture import Fixture

ROOT=Path(__file__).resolve().parents[1]

def main():
 fixture=Fixture();cfg=fixture.cfg;origin=cfg['BASE_URL'];db=fixture.db;users=fixture.users;clients=fixture.clients
 report={'checks':[],'latencies_ms':{},'models':{},'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'worker/workbench.py',ROOT/'src/workbench.rs']}}
 report['completed']=False
 def check(name,condition,details=None):
  report['checks'].append({'name':name,'passed':bool(condition),'details':details});print(name,'PASS' if condition else 'FAIL',flush=True)
  if not condition:raise AssertionError(name)
 def register(role):
  return fixture.register(role)
 def timed(name,client,path,payload=None,method='POST'):
  started=time.perf_counter();r=client.request(method,path,json=payload) if payload is not None else client.get(path);report['latencies_ms'][name]=round((time.perf_counter()-started)*1000,2);r.raise_for_status();return r.json()
 try:
  c,cu=register('candidate');e,eu=register('employer')
  reply=timed('career_newcomer',c,'/career-consultant',{'text':'Я новичок: прошёл основы Python, люблю анализировать данные. Выбери два направления, объясни различия и дай план на две недели.'})
  check('career_advice_real_qwen',len(reply.get('reply',''))>200)
  check('career_history_owner',len(c.get('/career-consultant').json()['items'])==2)
  check('career_employer_denied',e.get('/career-consultant').status_code==403)
  draft=timed('vacancy_generation',e,'/vacancies/generate',{'text':'Middle Python-разработчик: обработка событий и API на FastAPI/PostgreSQL. Удалённо, 180000–250000 рублей. Тесты и ревью обязательны.'})['draft']
  check('vacancy_generator_valid',draft['specialization']=='backend_python' and draft['salary_to']>=draft['salary_from']>0)
  draft['status']='published';v=e.post('/vacancies',json=draft);v.raise_for_status();vacancy=v.json()['vacancy']
  resume_id='VR-'+uuid.uuid4().hex
  db.execute("INSERT INTO resume_profiles(id,candidate_id,target_position,specialization,declared_grade,experience_years,skills,about,expected_salary,work_format,visibility,status) VALUES(%s,%s,'Python-разработчик','backend_python','middle',3,ARRAY['Python','PostgreSQL','FastAPI'],'Разрабатываю API и обработку событий, поддерживаю автоматизированные проверки и качество кода.',200000,'удалённо','private','draft')",(resume_id,cu['subject_id']))
  app=c.post('/vacancies/'+vacancy['id']+'/apply',json={'message':'Готов обсудить задачи и выполнить короткое тестовое.','resume_id':resume_id});app.raise_for_status()
  recipients=e.get('/vacancies/'+vacancy['id']+'/task-recipients').json()['items'];check('interested_recipients_only',len(recipients)==1 and recipients[0]['candidate_id']==cu['subject_id'])
  d=timed('task_generation_and_reference_validation',e,'/tasks/generate',{'vacancy_id':vacancy['id'],'instruction':'Проверь обработку списка событий и группировку по типу; обязательны пустой список, повторяющиеся события и граничные случаи. Вход только JSON.'})
  check('task_reference_validated',d['task']['validation']['reference_tests_passed']>=5 and 'hidden_tests' not in d['task'] and 'reference_solution' not in d['task'])
  dispatch=e.post('/tasks/dispatch',json={'draft_id':d['draft_id'],'candidate_ids':[cu['subject_id']]});dispatch.raise_for_status();tid=dispatch.json()['task_ids'][0]
  check('candidate_notified',c.get('/notifications').json()['unread']>=1)
  check('accept_task',c.put('/tasks/'+tid+'/decision',json={'status':'accepted'}).status_code==200)
  text=c.get('/tasks').text;check('hidden_contract_not_exposed','hidden_tests'not in text and 'reference_solution'not in text)
  contract=db.execute('SELECT contract FROM micro_tasks WHERE id=%s',(tid,)).fetchone()[0]
  wrong=timed('sandbox_incorrect',c,'/tasks/'+tid+'/run',{'code':'def solve(data):\n    return None'})
  check('incorrect_solution_detected',wrong['passed']<wrong['total'])
  correct=timed('sandbox_correct',c,'/tasks/'+tid+'/run',{'code':contract['reference_solution']})
  check('correct_solution_passes',correct['passed']==correct['total'])
  reviewed=timed('gpt_oss_review_and_delivery',c,'/tasks/'+tid+'/submit',{'code':contract['reference_solution']})
  check('all_public_and_hidden_tests_pass',reviewed['passed']==reviewed['total'])
  check('actual_gpt_oss_review',reviewed['review']['execution']['model']=='gpt-oss:20b' and len(reviewed['review']['feedback'])>30)
  report['models']['review']=reviewed['review']['execution'];report['review_score']=reviewed['score'];report['generated_task_tests']=reviewed['total']
  check('employer_received_review',e.get('/tasks').json()['items'][0]['score']==reviewed['score'] and any(n['kind']=='task.reviewed'for n in e.get('/notifications').json()['items']))
  check('duplicate_submit_denied',c.post('/tasks/'+tid+'/submit',json={'code':'pass'}).status_code==404)
  market=timed('market_analytics',e,'/vacancies/'+vacancy['id']+'/market',method='GET');check('market_aggregate_private','candidate_id'not in json.dumps(market) and c.get('/vacancies/'+vacancy['id']+'/market').status_code==403)
  f=timed('vacancy_forecast',e,'/forecasts/vacancy/'+vacancy['id'],method='GET')['forecast'];check('vacancy_forecast_nonworsening',f['recommended_days']<=f['forecast_days'])
  f=timed('candidate_forecast',c,'/forecasts/job-search/'+resume_id,method='GET')['forecast'];check('candidate_forecast_nonworsening',f['recommended_days']<=f['forecast_days'])
  check('pii_redaction','example.test'not in redact('Иванов Иван Иванович test@example.test +7 (999) 111-22-33') and '999'not in redact('+7 (999) 111-22-33'))
  async def adversarial():
   timeout=await sandbox('def solve(data):\n while True: pass',[{'input':0,'expected':0}]);check('infinite_loop_bounded',timeout.get('error')=='time_or_output_limit')
   network=await sandbox('def solve(data):\n import socket\n try: socket.create_connection((\"1.1.1.1\",443),timeout=1); return False\n except OSError: return True',[{'input':0,'expected':True}]);check('network_unavailable',network['passed']==1)
   secret=await sandbox('def solve(data):\n import os\n return os.getuid()!=0 and not os.path.exists(\"/app/.env\") and \"DATABASE_URL\" not in os.environ',[{'input':0,'expected':True}]);check('nonroot_no_secrets_mounts',secret['passed']==1)
   forged=await sandbox('def solve(data):\n print(\"PROOFIT_RESULT={\\\"tests\\\":[{\\\"actual\\\":999}]}\")\n return 0',[{'input':1,'expected':2}]);check('untrusted_verdict_not_accepted',forged['passed']==0)
  asyncio.run(adversarial())
  report['completed']=True
 except Exception as exc:
  report['failure_type']=type(exc).__name__
  raise
 finally:
  fixture.close();report['passed']=report['completed'] and all(x['passed']for x in report['checks']);out=ROOT/'validation/reports/current';out.mkdir(exist_ok=True);(out/'workbench-e2e.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
