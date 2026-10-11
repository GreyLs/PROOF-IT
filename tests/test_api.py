from scripts.private_runtime import private_file
"""Integration tests against the real Rust API and isolated project database.
All created identities are synthetic and cleaned up by exact IDs after the suite.
"""
from pathlib import Path
import os,uuid,json,time
import pytest,httpx,psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv, dotenv_values
ROOT=Path(__file__).resolve().parents[1]
load_dotenv(ROOT/'.env')
ORIGIN=(os.environ.get('FSP_TEST_BASE_URL') or dotenv_values(ROOT/'.env').get('BASE_URL') or 'http://localhost:1414').rstrip('/')
if not os.environ.get('FSP_TEST_BASE_URL') and (private_file('public-settings.json')).exists():
    ORIGIN=json.loads((private_file('public-settings.json')).read_text(encoding='utf-8'))['BASE_URL']
BASE=ORIGIN+'/api'

class LiveClient(httpx.Client):
    """Real identity requests with a disposable proxy IP, not relaxed limits.

    The private identity listener trusts only loopback forwarding. All business
    requests still traverse the public gateway. This prevents repeated suites
    consuming the operator's shared localhost authentication IP quota.
    """
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        seed=uuid.uuid4().int
        self.test_ip=f'198.18.{(seed>>8)%254+1}.{seed%254+1}'
    def request(self,method,url,*args,**kwargs):
        local = os.environ.get('FSP_TEST_LOCAL_TRANSPORT') == '1'
        if local and str(url).startswith('/'):
            # Secure cookies stay Secure; this test-only private loopback hop
            # forwards the jar with the actual external Host/Origin. Server
            # authentication, CSRF, expiry and logout guards are unchanged.
            headers=dict(kwargs.pop('headers',{}) or {})
            cookies='; '.join(cookie.name+'='+cookie.value for cookie in self.cookies.jar)
            if cookies and 'Cookie' not in headers:headers['Cookie']=cookies
            kwargs['headers']=headers
        if str(url).startswith('/auth/') and (local or not ORIGIN.startswith('https://')):
            from urllib.parse import urlsplit
            headers=dict(kwargs.pop('headers',{}) or {})
            headers.update({'Host':urlsplit(ORIGIN).netloc,'X-Forwarded-For':self.test_ip})
            kwargs['headers']=headers
            url='http://127.0.0.1:8082/api'+str(url)
        elif local and str(url).startswith('/'):
            from urllib.parse import urlsplit
            headers=dict(kwargs.pop('headers',{}) or {})
            headers['Host']=urlsplit(ORIGIN).netloc
            kwargs['headers']=headers
            bind=dotenv_values(ROOT/'.env').get('BIND_ADDR','127.0.0.1:1717')
            if private_file('public-settings.json').exists():
                bind=json.loads(private_file('public-settings.json').read_text(encoding='utf-8')).get('BIND_ADDR',bind)
            url='http://'+bind+'/api'+str(url)
        return super().request(method,url,*args,**kwargs)

@pytest.fixture(scope='module')
def world():
    conn=psycopg.connect(os.environ['DATABASE_URL'],autocommit=True,row_factory=dict_row)
    users=[];clients=[];names={}
    def register(role):
        c=LiveClient(headers={"Origin":ORIGIN},base_url=BASE,timeout=30,trust_env=False);clients.append(c);email=f'qa-{uuid.uuid4().hex}@example.test';name=f"Синтетический {'кандидат' if role=='candidate' else 'работодатель'} {uuid.uuid4().hex}"
        r=c.post('/auth/register',json={'email':email,'password':'TestingOnly-2026-Long','role':role,'name':name,'consent_processing':True});assert r.status_code==200,r.text
        token=r.json()['development_mail']['token']
        assert c.post('/auth/login',json={'email':email,'password':'TestingOnly-2026-Long'}).status_code==403
        r=c.post('/auth/verify',json={'token':token});assert r.status_code==200,r.text
        u=r.json()['user'];users.append(u);names[u['id']]=name
        assert c.post('/auth/verify',json={'token':token}).status_code==400
        return c,u
    candidate,cu=register('candidate');employer,eu=register('employer');other,ou=register('employer')
    w={'db':conn,'candidate':candidate,'cu':cu,'employer':employer,'eu':eu,'other':other,'ou':ou,'names':names,'register':register}
    yield w
    for c in clients:c.close()
    # Delete only records belonging to IDs created by this suite.
    subjects=[u['subject_id'] for u in users];uids=[u['id'] for u in users]
    with conn.transaction():
        conn.execute('DELETE FROM audit_events WHERE actor_id=ANY(%s)',(uids,))
        conn.execute('DELETE FROM documents WHERE user_id=ANY(%s)',(uids,))
        conn.execute('DELETE FROM saved_searches WHERE company_id=ANY(%s)',(subjects,))
        conn.execute('DELETE FROM micro_tasks WHERE company_id=ANY(%s) OR candidate_id=ANY(%s)',(subjects,subjects))
        conn.execute('DELETE FROM private_conversations WHERE company_id=ANY(%s) OR candidate_id=ANY(%s)',(subjects,subjects))
        conn.execute('DELETE FROM invitations WHERE company_id=ANY(%s) OR candidate_id=ANY(%s)',(subjects,subjects))
        conn.execute('DELETE FROM applications WHERE candidate_id=ANY(%s) OR vacancy_id IN(SELECT id FROM vacancies WHERE company_id=ANY(%s))',(subjects,subjects))
        conn.execute('DELETE FROM assessments WHERE candidate_id=ANY(%s)',(subjects,))
        conn.execute('DELETE FROM vacancies WHERE company_id=ANY(%s)',(subjects,))
        conn.execute('DELETE FROM users WHERE id=ANY(%s)',(uids,))
        conn.execute('DELETE FROM candidates WHERE id=ANY(%s)',(subjects,))
        conn.execute('DELETE FROM companies WHERE id=ANY(%s)',(subjects,))
    conn.close()

def test_01_authentication_and_roles(world):
    with LiveClient(base_url=BASE,headers={'Origin':ORIGIN}) as anonymous:
        for role in ['candidate','employer']:
            assert anonymous.post('/auth/demo',json={'role':role}).status_code in (404,405)
            assert anonymous.get('/auth/me').status_code==401
        for endpoint in ['/dashboard','/profile','/candidates','/documents','/invitations','/vacancies','/applications','/tasks','/saved-searches']:
            assert anonymous.get(endpoint).status_code==401,endpoint
        upload=anonymous.build_request('POST','/documents?kind=resume',files={'file':('empty.pdf',b'%PDF-','application/pdf')})
        upload.read()  # Browser FormData is already buffered; avoid streaming after early 401.
        assert anonymous.send(upload).status_code==401
    assert LiveClient(base_url=BASE).post('/auth/register',json={'email':f'short-{uuid.uuid4().hex}@example.test','password':'я'*5,'role':'candidate','name':'Тестовый пользователь','consent_processing':True}).status_code==400
    assert httpx.get(BASE+'/profile').status_code==401
    assert world['candidate'].get('/candidates').status_code==403
    assert world['employer'].post('/assessments',json={'specialization':'backend_python','grade':'junior','industry':'ИТ'}).status_code==403
    assert world['candidate'].put('/company',json={'name':'test','description':'test','industry':'IT','contact':'test'}).status_code==403
    assert world['candidate'].get('/auth/me').json()['user']['subject_id']==world['cu']['subject_id']


def test_registered_password_login_keeps_role_and_ends_on_logout(world):
    email=world['cu']['email']
    with LiveClient(base_url=BASE,headers={'Origin':ORIGIN}) as client:
        assert client.post('/auth/login',json={'email':email,'password':'wrong-password'}).status_code==401
        response=client.post('/auth/login',json={'email':email,'password':'TestingOnly-2026-Long','role':'employer'})
        assert response.status_code==200
        assert response.json()['user']['role']=='candidate'
        assert client.get('/profile').json()['profile']['id']==world['cu']['subject_id']
        assert client.post('/auth/demo',json={'role':'employer'}).status_code in (404,405)
        assert client.get('/auth/me').json()['user']['role']=='candidate'
        assert client.post('/auth/logout').status_code==200
        assert client.get('/profile').status_code==401

def test_login_by_registered_display_name_keeps_each_role(world):
    with LiveClient(base_url=BASE,headers={'Origin':ORIGIN}) as client:
        for user in (world['cu'],world['eu']):
            response=client.post('/auth/login',json={'identifier':world['names'][user['id']],'password':'TestingOnly-2026-Long'})
            assert response.status_code==200,response.text
            assert response.json()['user']['role']==user['role']
            assert client.post('/auth/logout').status_code==200
            assert client.get('/auth/me').status_code==401

def test_02_profile_consent_and_unconfirmed_visibility(world):
    c=world['candidate'];p=c.get('/profile').json()['profile'];p.update(specialization='backend_python',declared_grade='junior',skills=['Python','FastAPI','PostgreSQL','Docker'],full_name='Тестовый Кандидат',phone='+7 000 000-00-00',expected_salary=150000,consent_publication=True,visibility='employer_searchable')
    r=c.put('/profile',json=p);assert r.status_code==200,r.text
    assert r.json()['profile']['confirmed_grade'] is None
    # Publication expresses intent; employer discovery requires actual,
    # unexpired evidence of the selected role/grade, not a self-report.
    search=world['employer'].get('/candidates',params={'q':world['cu']['subject_id']}).json();assert search['total']==0
    assert c.put('/profile',json=p).status_code==409
    p=r.json()['profile'];p['consent_publication']=False
    assert c.put('/profile',json=p).status_code==400

def test_03_published_resume_waits_for_its_own_assessment(world):
    c=world['candidate']
    assert c.post('/assessments',json={}).status_code==410
    assert c.post('/assessments/legacy/submit',json={'answers':{}}).status_code==410
    world['db'].execute("INSERT INTO assessments(id,candidate_id,specialization,grade,blueprint_version,seed,items,status,score,finished_at,synthetic) VALUES(%s,%s,'backend_python','junior','synthetic-fixture','fixture','[]','passed',83,now(),true)",('qa-'+uuid.uuid4().hex,world['cu']['subject_id']))
    resume={'target_position':'Python developer','specialization':'backend_python','declared_grade':'junior','experience_years':2,'skills':['Python','FastAPI','PostgreSQL','Docker'],'about':'Разрабатывал API на Python и FastAPI, отвечал за PostgreSQL и поставку изменений.','expected_salary':150000,'work_format':'удалённо','visibility':'employer_searchable'}
    created=c.post('/resumes',json=resume);assert created.status_code==200,created.text
    world['resume_id']=created.json()['resume']['id']
    search=world['employer'].get('/candidates',params={'q':world['cu']['subject_id']}).json()
    assert search['total']==0 and search['items']==[]

def test_04_dialogue_cooldown_and_profile_requirements(world):
    c=world['candidate'];p=c.get('/profile').json()['profile']
    p.update(declared_grade='middle',about='Синтетический профиль для проверки ограничений. Разрабатывал сервис на Python и PostgreSQL.')
    assert c.put('/profile',json=p).status_code==200
    assert c.post('/dialogues',json={'mode':'profile'}).status_code==409
    # Evidence is scoped to the selected resume; a profile-wide grade is not
    # manufactured from another assessment or employer action.
    assert c.get('/profile').json()['profile']['confirmed_grade'] is None
    p=c.get('/profile').json()['profile'];p['declared_grade']='junior';assert c.put('/profile',json=p).status_code==200

def test_05_contact_access_is_company_scoped_and_invite_idempotent(world):
    c,e,o=world['candidate'],world['employer'],world['other'];cid=world['cu']['subject_id']
    # A disposable certificate supplies the discovery precondition. This suite
    # tests contacts, not CAT quality; actual issuance has a separate live suite.
    world['db'].execute("INSERT INTO qualification_certificates(id,candidate_id,resume_id,specialization,grade,skills,assessment_version,attempt) VALUES(%s,%s,%s,'backend_python','junior','[\"Python\"]','contact-boundary-fixture','{\"score\":86}')", ('CERT'+uuid.uuid4().hex,cid,world['resume_id']))
    assert e.get('/candidates/'+cid).json()['contacts'] is None
    payload={'candidate_id':cid,'vacancy_id':None,'title':'Тестовое предложение','description':'Синтетическое предложение для проверки API','salary_from':150000,'salary_to':210000,'idempotency_key':str(uuid.uuid4())}
    invalid={**payload,'salary_from':0};assert e.post('/invitations',json=invalid).status_code==400
    invalid={**payload,'salary_to':100000};assert e.post('/invitations',json=invalid).status_code==400
    r=e.post('/invitations',json=payload);assert r.status_code==200,r.text;inv=r.json()['invitation'];world['invitation_id']=inv['id']
    assert e.post('/invitations',json=payload).json()['invitation']['id']==inv['id']
    assert e.post('/invitations',json={**payload,'salary_to':220000}).status_code==409
    assert o.get('/invitations').json()['items']==[]
    assert e.put('/invitations/'+inv['id'],json={'status':'accepted'}).status_code==403
    assert c.put('/invitations/'+inv['id'],json={'status':'viewed'}).status_code==200
    assert e.get('/candidates/'+cid).json()['contacts'] is None
    assert c.put('/invitations/'+inv['id'],json={'status':'accepted'}).status_code==200
    assert e.get('/candidates/'+cid).json()['contacts']['phone']=='+7 000 000-00-00'
    assert o.get('/candidates/'+cid).json()['contacts'] is None
    assert c.put('/invitations/'+inv['id'],json={'status':'declined'}).status_code==409

def test_06_candidate_cannot_read_other_invitation(world):
    c,u=world['register']('candidate')
    assert c.get('/invitations').json()['items']==[]
    assert c.put('/invitations/'+world['invitation_id'],json={'status':'accepted'}).status_code==404

def test_07_vacancies_applications_and_ownership(world):
    e,o,c=world['employer'],world['other'],world['candidate']
    v={'title':'Python разработчик — тест API','description':'Тестовое описание задач и команды для проверки публикации','specialization':'backend_python','grade':'junior','skills':['Python','FastAPI'],'salary_from':160000,'salary_to':220000,'work_format':'удалённо','status':'published'}
    assert c.post('/vacancies',json=v).status_code==403
    r=o.post('/vacancies',json=v);assert r.status_code==200,r.text;vid=r.json()['vacancy']['id'];world['vacancy_id']=vid
    assert e.put('/vacancies/'+vid,json=v).status_code==404
    assert o.get('/candidates/'+world['cu']['subject_id']).json()['contacts'] is None
    r=c.post('/vacancies/'+vid+'/apply',json={'message':'Хочу обсудить роль'});assert r.status_code==200,r.text;aid=r.json()['application']['id']
    assert r.json()['application']['resume_id']==world['resume_id']
    applications=o.get('/applications').json()['items'];assert len(applications)==1
    application=applications[0]
    assert application['resume']['id']==world['resume_id'] and application['resume']['about']
    assert application['vacancy']['id']==vid and application['candidate']['id']==world['cu']['subject_id']
    assert application['match']['score']>0 and len(application['match']['components'])==4
    assert application['match']['components'][0]['key']=='resume'
    assert o.get('/candidates/'+world['cu']['subject_id']).json()['contacts_released']
    assert o.put('/applications/'+aid,json={'status':'interview'}).status_code==200
    assert e.put('/applications/'+aid,json={'status':'rejected'}).status_code==404
    assert c.put('/applications/'+aid,json={'status':'withdrawn'}).status_code==200
    assert not o.get('/candidates/'+world['cu']['subject_id']).json()['contacts_released']

def test_08_microtask_feedback_and_frequency(world):
    e,c=world['employer'],world['candidate'];p={'candidate_id':world['cu']['subject_id'],'title':'Обработчик повторов','prompt':'Опишите, как избежать повторной обработки события при retry.'}
    # A short employer task is available only when a public target resume has
    # its own confirmed qualification, rather than through a global grade flag.
    world['db'].execute("UPDATE qualification_tests SET status='passed',generation_status='ready',passed=true,score=86,finished_at=now() WHERE resume_id=%s",(world['resume_id'],))
    r=e.post('/tasks',json=p);assert r.status_code==200,r.text;tid=r.json()['task']['id']
    assert e.post('/tasks',json=p).status_code==409
    assert c.put('/tasks/'+tid,json={'response':'Сохранить уникальный ключ события в транзакции вместе с изменением.'}).status_code==200
    assert e.put('/tasks/'+tid,json={'score':90,'feedback':'Верно: атомарность устраняет частичное применение.'}).status_code==200
    assert c.get('/resumes/'+world['resume_id']+'/test').json()['passed'] is True

def test_09_upload_file_validation_and_ownership(world):
    c,o=world['candidate'],world['other']
    assert c.post('/documents?kind=resume',files={'file':('fake.pdf',b'<script>test</script>','application/pdf')}).status_code==400
    assert c.post('/documents?kind=vacancy',files={'file':('x.pdf',b'%PDF-fake','application/pdf')}).status_code==400
    with (ROOT/'tests/fixtures/candidate-text.pdf').open('rb') as f:r=c.post('/documents?kind=resume',files={'file':('resume.pdf',f,'application/pdf')})
    assert r.status_code==200,r.text;did=r.json()['document']['id'];world['document_id']=did
    # The candidate has explicitly enabled discovery in test_02.  A subsequent
    # upload must preserve that intent while extraction is in progress, rather
    # than silently creating a permanently hidden duplicate resume.
    uploaded=world['db'].execute("SELECT visibility FROM resume_profiles WHERE document_id=%s",(did,)).fetchone()
    assert uploaded and uploaded['visibility']=='employer_searchable'
    assert o.get('/documents/'+did).status_code==404
    assert o.get('/documents/'+did+'/file').status_code==404
    with (ROOT/'tests/fixtures/candidate-text.pdf').open('rb') as f:r=c.post('/documents?kind=resume',files={'file':('renamed.pdf',f,'application/pdf')})
    assert r.json()['duplicate'] and r.json()['document']['id']==did

def test_10_origin_csrf_and_session_logout(world):
    c,u=world['register']('candidate')
    assert c.post('/auth/logout',headers={'Origin':'https://attacker.example'}).status_code==403
    assert c.get('/profile').status_code==200
    assert c.post('/auth/logout').status_code==200
    assert c.get('/profile').status_code==401

def test_11_profile_change_cannot_bypass_grade_cooldown(world):
    c=world['candidate'];p=c.get('/profile').json()['profile'];p['specialization']='backend_java'
    assert c.put('/profile',json=p).status_code==200
    p=c.get('/profile').json()['profile'];p['declared_grade']='senior';assert c.put('/profile',json=p).status_code==200
    assert c.post('/dialogues',json={'mode':'profile'}).status_code==409

def test_12_saved_search_and_strict_skill_filter(world):
    e=world['employer'];r=e.get('/candidates',params={'specialization':'backend_python','skills':'Python,FastAPI','limit':30});assert r.status_code==200,r.text
    assert all({'python','fastapi'}<=set(s.lower() for s in x['skills']) for x in r.json()['items'])
    r=e.post('/saved-searches',json={'name':'Проверка сохранения','query':{'specialization':'backend_python'},'candidate_ids':[x['id'] for x in r.json()['items']]});assert r.status_code==200
    assert len(e.get('/saved-searches').json()['items'])==1
    assert world['other'].get('/saved-searches').json()['items']==[]

def test_13_login_throttle(world):
    email=f'nonexistent-{uuid.uuid4().hex}@example.test'
    with LiveClient(headers={"Origin":ORIGIN},base_url=BASE,timeout=30,trust_env=False) as c:
        for _ in range(20):assert c.post('/auth/login',json={'email':email,'password':'invalid-password'}).status_code==401
        assert c.post('/auth/login',json={'email':email,'password':'invalid-password'}).status_code==429

def test_14_cyrillic_casefold(world):
    e=world['employer'];upper=e.get('/candidates',params={'specialization':'one_c','skills':'1С:Предприятие','limit':100}).json()
    lower=e.get('/candidates',params={'specialization':'one_c','skills':'1с:предприятие','limit':100}).json()
    assert upper['total']>0 and upper['total']==lower['total']
    assert [(x['id'],x['relevance']) for x in upper['items']]==[(x['id'],x['relevance']) for x in lower['items']]


def test_15_bundle_review_requires_selection_and_preserves_other_people(world):
    doc_id='D'+uuid.uuid4().hex
    result={'fields':{},'requires_review':True,'profiles':[
        {'fields':{'full_name':'Первый тестовый кандидат','email':'first@example.test'},'page_from':1,'page_to':1},
        {'fields':{'full_name':'Второй тестовый кандидат','email':'second@example.test'},'page_from':2,'page_to':2},
    ]}
    world['db'].execute("INSERT INTO documents(id,user_id,kind,filename,sha256,storage_key,bytes,status,result) VALUES(%s,%s,'resume','synthetic-bundle.pdf',%s,%s,0,'review',%s::jsonb)",
        (doc_id,world['eu']['id'],uuid.uuid4().hex*2,doc_id+'.pdf',json.dumps(result)))
    employer=world['employer'];endpoint='/documents/'+doc_id
    assert employer.put(endpoint,json={'fields':{}}).status_code==400
    assert employer.put(endpoint,json={'fields':{},'profile_index':2}).status_code==400
    assert world['other'].put(endpoint,json={'fields':{},'profile_index':0}).status_code==404
    updated={'full_name':'Второй тестовый кандидат','email':'corrected@example.test'}
    response=employer.put(endpoint,json={'fields':updated,'profile_index':1})
    assert response.status_code==200,response.text
    doc=response.json()['document'];assert doc['status']=='review'
    assert doc['result']['fields']=={}
    assert 'reviewed_fields' not in doc['result']['profiles'][0]
    assert doc['result']['profiles'][1]['reviewed_fields']==updated
    assert doc['result']['reviewed_profile_index']==1
    response=employer.put(endpoint,json={'fields':result['profiles'][0]['fields'],'profile_index':0})
    assert response.status_code==200 and response.json()['document']['status']=='completed'
    assert response.json()['document']['result']['profiles'][1]['reviewed_fields']==updated


def test_16_legacy_passwordless_sessions_are_revoked(world):
    count=world['db'].execute("SELECT count(*) AS count FROM sessions WHERE user_id IN ('demo-candidate','demo-employer')").fetchone()['count']
    assert count==0
