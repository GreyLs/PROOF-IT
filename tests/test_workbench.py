"""Ownership, quotas and atomicity against the running Rust/PostgreSQL services."""
import pytest
from scripts.workbench_test_fixture import Fixture

@pytest.fixture(scope='module')
def world():
    fixture=Fixture()
    try:
        c,cu=fixture.register('candidate');e,eu=fixture.register('employer');o,ou=fixture.register('employer')
        yield {'candidate':c,'cu':cu,'employer':e,'eu':eu,'other':o,'ou':ou,'db':fixture.db}
    finally:
        fixture.close()

VACANCY = {'title':'Проверка Python API','description':'Разработка API на Python и PostgreSQL, тесты и ревью.','specialization':'backend_python','grade':'middle','skills':['Python','PostgreSQL'],'salary_from':180000,'salary_to':250000,'work_format':'удалённо','status':'published'}

def test_workbench_role_boundaries(world):
    candidate, employer = world['candidate'], world['employer']
    assert employer.get('/career-consultant').status_code == 403
    assert candidate.post('/vacancies/generate',json={'text':'Python backend developer'}).status_code == 403
    assert candidate.post('/vacancies/bulk',json={'items':[VACANCY]}).status_code == 403
    assert candidate.post('/tasks/generate',json={'vacancy_id':'missing'}).status_code == 403
    assert candidate.get('/notifications').status_code == 200
    assert candidate.get('/career-consultant').json()['items'] == []
    assert candidate.post('/career-consultant',json={'text':'x'*2001}).status_code == 400

def test_bulk_atomicity_and_50_limit(world):
    e=world['employer']; old=e.get('/vacancies?mine=true&limit=100').json()['items']; assert not old
    invalid={**VACANCY,'salary_to':1}
    assert e.post('/vacancies/bulk',json={'items':[VACANCY,invalid]}).status_code==400
    assert not e.get('/vacancies?mine=true&limit=100').json()['items']
    r=e.post('/vacancies/bulk',json={'items':[{**VACANCY,'title':f'Python backend {i}'} for i in range(50)]});assert r.status_code==200,r.text
    assert r.json()['imported']==50
    assert e.post('/vacancies',json=VACANCY).status_code==409
    assert e.post('/vacancies/bulk',json={'items':[VACANCY]}).status_code==409
    assert e.post('/vacancies/bulk',json={'items':[VACANCY]*51}).status_code==400
    ids=[v['id'] for v in r.json()['items']]; world['bulk_ids']=ids
    assert e.put('/vacancies/'+ids[0],json={**VACANCY,'status':'closed'}).status_code==200
    assert e.post('/vacancies',json=VACANCY).status_code==200
    assert e.put('/vacancies/'+ids[0],json=VACANCY).status_code==409

def test_market_and_forecast_privacy(world):
    e=world['employer'];v=e.get('/vacancies?mine=true&limit=100').json()['items'][0]
    market=e.get('/vacancies/'+v['id']+'/market');assert market.status_code==200,market.text
    m=market.json();assert m['relevant_candidates']>=0
    assert 'candidate_id' not in market.text and '@' not in market.text
    assert m['recommended_salary'] is None or m['recommended_salary']>(v['salary_from']+v['salary_to'])/2
    if m['candidate_salary']['sample']<5:assert m['candidate_salary']['median'] is None
    assert world['other'].get('/vacancies/'+v['id']+'/market').status_code==404
    assert world['candidate'].get('/vacancies/'+v['id']+'/market').status_code==403
    f=e.get('/forecasts/vacancy/'+v['id']);assert f.status_code==200,f.text
    assert f.json()['forecast']['forecast_days']>0
    assert world['other'].get('/forecasts/vacancy/'+v['id']).status_code==403

def test_task_transition_and_hidden_data(world):
    c,e,db=world['candidate'],world['employer'],world['db'];v=e.get('/vacancies?mine=true&limit=100').json()['items'][0]
    cid=world['cu']['subject_id'];eid=world['eu']['subject_id']
    contract={'title':'Сумма чисел','prompt':'Верните сумму элементов массива; пустой массив даёт ноль.','starter_code':'def solve(data):\n    pass','reference_solution':'def solve(data): return sum(data)','public_tests':[{'input':[1,2],'expected':3},{'input':[],'expected':0}],'hidden_tests':[{'input':[-3,4],'expected':1},{'input':[1,1],'expected':2},{'input':[9],'expected':9}]}
    from psycopg.types.json import Jsonb
    task='WT-'+world['cu']['id'];db.execute("INSERT INTO micro_tasks(id,company_id,candidate_id,vacancy_id,title,prompt,contract) VALUES(%s,%s,%s,%s,%s,%s,%s)",(task,eid,cid,v['id'],contract['title'],contract['prompt'],Jsonb(contract)))
    text=c.get('/tasks').text;assert 'reference_solution' not in text and 'hidden_tests' not in text
    assert c.put('/tasks/'+task,json={'response':'Попытка обойти песочницу и автоматическое ревью'}).status_code==404
    assert c.post('/tasks/'+task+'/run',json={'code':'def solve(data): return sum(data)'}).status_code==404
    assert world['other'].put('/tasks/'+task+'/decision',json={'status':'accepted'}).status_code==403
    assert c.put('/tasks/'+task+'/decision',json={'status':'accepted'}).status_code==200
    assert c.put('/tasks/'+task+'/decision',json={'status':'declined'}).status_code==409
    assert c.post('/tasks/'+task+'/run',json={'code':'def solve(data): return sum(data)'}).json()['passed']==2
    assert c.post('/tasks/'+task+'/run',json={'code':'def solve(data): return 0'}).json()['passed']==1
    assert world['other'].post('/tasks/'+task+'/run',json={'code':'pass'}).status_code==403
    assert e.get('/notifications').json()['unread']>=1
    notice=e.get('/notifications').json()['items'][0]['id'];assert c.post('/notifications/'+notice+'/read',json={}).status_code==404
    assert e.post('/notifications/'+notice+'/read',json={}).status_code==200

def test_export_contains_all_owned_workbench_records_without_hidden_contract(world):
    c,db=world['candidate'],world['db'];uid=world['cu']['id'];cid=world['cu']['subject_id']
    db.execute("INSERT INTO career_messages(candidate_id,role,content) SELECT %s,'user','Controlled career history '||n FROM generate_series(1,25)n",(cid,))
    db.execute("INSERT INTO notifications(id,user_id,kind,title,entity_id) SELECT 'EX'||%s||n,%s,'test','Controlled notification','test' FROM generate_series(1,55)n",(uid,uid))
    exported=c.get('/account/export');assert exported.status_code==200,exported.text
    result=exported.json()
    assert len(result['career_consultant']['items'])==25
    assert len(result['notifications']['items'])==55
    assert len(result['practical_tasks']['items'])==1
    assert 'hidden_tests'not in exported.text and 'reference_solution'not in exported.text
    assert world['other'].get('/account/export').json()['practical_tasks']['items']==[]
    assert world['employer'].get('/account/export').json()['career_consultant']['items']==[]
