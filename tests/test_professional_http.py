"""Live ownership, CAS, timer, reviewer and OIDC-state integration."""
import pytest
from scripts.workbench_test_fixture import Fixture
from intelligence import professional as cat


@pytest.fixture(scope="module")
def world():
    f=Fixture()
    try:
        c,cu=f.register("candidate");other,ou=f.register("candidate");e,eu=f.register("employer");reviewer,ru=f.register("employer")
        yield {"f":f,"c":c,"cu":cu,"other":other,"e":e,"reviewer":reviewer}
    finally:
        f.db.execute("DELETE FROM intelligence.item_drafts WHERE author_id=ANY(%s) OR reviewer_id=ANY(%s)",([u['id'] for u in f.users],[u['id'] for u in f.users]))
        f.close()


def test_private_start_resume_role_and_cas(world):
    c=world["c"];p={"mode":"express","specialization":"backend_python","extra_time":True}
    r=c.post('/intelligence/assessment/attempts',json=p);r.raise_for_status();a=r.json();world["attempt"]=a
    assert 'bank'not in a['contract'] and 'correct'not in a['contract']['question']
    assert c.post('/intelligence/assessment/attempts',json=p).json()['id']==a['id']
    assert world['e'].post('/intelligence/assessment/attempts',json=p).status_code==403
    q=a['contract']['question'];p={'question_id':q['id'],'answer':0,'revision':a['revision']}
    assert world['other'].post(f"/intelligence/assessment/attempts/{a['id']}/answer",json=p).status_code==404
    r=c.post(f"/intelligence/assessment/attempts/{a['id']}/answer",json=p);assert r.status_code==200,r.text
    assert c.post(f"/intelligence/assessment/attempts/{a['id']}/answer",json=p).status_code==409


def test_bounded_signals_complete_and_grade_unchanged(world):
    c=world['c'];aid=world['attempt']['id'];db=world['f'].db
    assert c.post(f'/intelligence/assessment/attempts/{aid}/signals',json={'kind':'paste','count':1}).json()['automatic_penalty'] is False
    assert c.post(f'/intelligence/assessment/attempts/{aid}/signals',json={'kind':'clipboard-content','count':1}).status_code==400
    old=db.execute('SELECT confirmed_grade FROM candidates WHERE id=%s',(world['cu']['subject_id'],)).fetchone()[0]
    for _ in range(10):
        row=c.get('/intelligence/assessment/attempts').json()['items'][0]
        if row['status']=='completed':break
        raw=db.execute('SELECT contract FROM intelligence.professional_attempts WHERE id=%s',(aid,)).fetchone()[0];q=cat.next_item(raw)
        response=c.post(f'/intelligence/assessment/attempts/{aid}/answer',json={'question_id':q['id'],'answer':q['correct'],'revision':row['revision']});response.raise_for_status()
    assert row['status']=='completed' and row['result']['scored_questions']==8
    assert db.execute('SELECT confirmed_grade FROM candidates WHERE id=%s',(world['cu']['subject_id'],)).fetchone()[0]==old
    exported=c.get('/account/export').json()['intelligence']['professional']
    assert len(exported['attempts'])==1 and len(exported['signals'])==1 and 'contract'not in exported['attempts'][0]


def test_cross_reviewer_and_pilot_activation_gates(world):
    e=world['e'];r=world['reviewer']
    content={'prompt':'Событие пришло повторно. Какой механизм предотвращает повторное списание?','options':['Уникальный ключ в транзакции','Повтор без ключа','Удаление журналов','Игнорирование ошибок'],'correct':0,'rationale':'Уникальность ключа и транзакционная запись сохраняют инвариант.'}
    created=e.post('/intelligence/assessment/drafts',json={'specialization':'backend_python','content':content});created.raise_for_status();did=created.json()['id']
    assert world['c'].get('/intelligence/assessment/bank').status_code==403
    p={'decision':'pilot','note':'Условие и однозначность ответов проверены экспертом.'}
    assert e.post(f'/intelligence/assessment/drafts/{did}/review',json=p).status_code==409
    response=r.post(f'/intelligence/assessment/drafts/{did}/review',json=p);assert response.status_code==200,response.text
    assert r.post(f'/intelligence/assessment/drafts/{did}/activate',json={}).status_code==409
    assert r.post(f'/intelligence/assessment/drafts/{did}/calibrate',json={}).status_code==400


def test_need_preview_and_oidc_state_ownership(world):
    e=world['e'];c=world['c']
    assert c.post('/intelligence/assessment/need-preview',json={'text':'Python developer'}).status_code==403
    p=e.post('/intelligence/assessment/need-preview',json={'text':'Middle Python / Backend PostgreSQL удалённо 180–250 тыс руб'});p.raise_for_status();assert p.json()['specialization']=='backend_python'
    start=c.post('/intelligence/assessment/oidc',json={});start.raise_for_status();assert 'code_challenge=' in start.json()['authorization_url']
    from urllib.parse import urlsplit,parse_qs
    params=parse_qs(urlsplit(start.json()['authorization_url']).query);state=params['state'][0]
    assert world['other'].get('/intelligence/assessment/oidc/callback',params={'state':state,'code':'invalid'}).status_code==400
    assert not c.get('/intelligence/assessment/oidc').json()['linked']


def test_oidc_signed_flow_and_callback_replay(world):
    import httpx
    c=world['c'];start=c.post('/intelligence/assessment/oidc',json={});start.raise_for_status()
    from pathlib import Path
    from playwright.sync_api import sync_playwright
    callbacks=[]
    with sync_playwright() as browser_tool:
        browser=browser_tool.chromium.launch(headless=True)
        context=browser.new_context()
        secure=world['f'].cfg['BASE_URL'].startswith('https://');cookie_name='__Host-proofit_oidc'if secure else 'proofit_oidc'
        context.add_cookies([{'name':cookie_name,'value':c.cookies.get(cookie_name),'url':world['f'].cfg['BASE_URL'],'secure':secure,'httpOnly':True,'sameSite':'Lax'}])
        page=context.new_page()
        from urllib.parse import urlsplit
        page.on('request',lambda request:callbacks.append(request.url) if urlsplit(request.url).path=='/api/intelligence/assessment/oidc/callback' else None)
        page.goto(start.json()['authorization_url'])
        page.locator('#username').fill('proofit-demo')
        page.locator('#password').fill(Path('runtime/keycloak-demo.secret').read_text().strip())
        page.locator('#kc-login').click()
        for _ in range(60):
            if callbacks:break
            page.wait_for_timeout(250)
        assert callbacks,'Real Keycloak authorization did not return a code: '+page.locator('body').inner_text()[:1500]
        assert c.get('/intelligence/assessment/oidc').json()['linked']
        callback=callbacks[0];browser.close()
    # A valid state alone is insufficient in a different browser.
    with httpx.Client(trust_env=False) as stranger:assert stranger.get(callback).status_code==400
    # Cross-site return may legitimately omit the Strict application cookie.
    with httpx.Client(trust_env=False,cookies={cookie_name:c.cookies.get(cookie_name)}) as browser:
        response=browser.get(callback,headers={'Sec-Fetch-Site':'cross-site','Sec-Fetch-Mode':'navigate','Sec-Fetch-Dest':'document'});assert response.status_code==400,response.text
    assert c.get('/intelligence/assessment/oidc').json()['linked']
    assert c.get(callback).status_code==400
