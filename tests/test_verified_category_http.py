"""Live Rust/PostgreSQL category boundary; disposable persisted evidence only.

Fixture certificates exercise visibility/state contracts, not assessment quality.
The full CAT -> certificate workflow is covered in test_resume_qualification.py.
"""
import uuid
import pytest
from psycopg.rows import dict_row
from scripts.workbench_test_fixture import Fixture


@pytest.fixture
def boundary():
    f = Fixture(local_transport=True)
    f.db.row_factory = dict_row
    c, cu = f.register('candidate')
    e, eu = f.register('employer')
    other, ou = f.register('candidate')
    f.db.execute('UPDATE candidates SET consent_publication=true WHERE id=%s', (cu['subject_id'],))
    body = dict(target_position='Python API Engineer', specialization='backend_python',
                declared_grade='senior', experience_years=4, skills=['Python', 'SQL'],
                about='Разработка API и проверка SQL-запросов.', expected_salary=180000,
                work_format='удалённо', visibility='employer_searchable')
    response = c.post('/resumes', json=body)
    response.raise_for_status()
    rid = response.json()['resume']['id']
    yield dict(f=f, db=f.db, c=c, e=e, cu=cu, eu=eu, ou=ou, rid=rid, body=body)
    f.close()


def certificate(w, **overrides):
    values = dict(id='CT'+uuid.uuid4().hex, candidate_id=w['cu']['subject_id'],
                  resume_id=w['rid'], specialization='backend_python', grade='middle',
                  scope='role-knowledge') | overrides
    w['db'].execute("""INSERT INTO qualification_certificates
        (id,candidate_id,resume_id,specialization,grade,skills,assessment_version,attempt,scope)
        VALUES(%(id)s,%(candidate_id)s,%(resume_id)s,%(specialization)s,%(grade)s,
               '["Python"]','boundary-fixture','{"score":90}',%(scope)s)""", values)
    return values['id']


def discovery(w, expected):
    cid = w['cu']['subject_id']
    response = w['e'].get('/candidates', params={'q': cid})
    response.raise_for_status()
    data = response.json()
    assert bool(data['total']) is expected
    assert data['eligibility_version'] == 'verified-category-1.0'
    detail = w['e'].get('/candidates/'+cid)
    assert detail.status_code == (200 if expected else 404)
    return data


def offer(w, **changes):
    return dict(candidate_id=w['cu']['subject_id'], resume_id=w['rid'],
                title='Backend engineer', description='Разработка и сопровождение Python API.',
                salary_from=180000, salary_to=240000, idempotency_key=uuid.uuid4().hex) | changes


def test_declared_grade_is_not_discoverable_or_invitable(boundary):
    w=boundary
    discovery(w, False)
    assert w['e'].post('/invitations', json=offer(w)).status_code == 404


@pytest.mark.parametrize('timestamp', ['NULL', "now()+interval '1 day'", "now()-interval '181 days'"])
def test_missing_future_and_expired_historical_dates_fail_closed(boundary, timestamp):
    w=boundary
    # Fixed parameterized test expressions; no user-controlled SQL interpolation.
    w['db'].execute("UPDATE qualification_tests SET certified_grade='middle', certified_specialization='backend_python', certified_at="+timestamp+" WHERE resume_id=%s", (w['rid'],))
    discovery(w, False)


def test_valid_historical_snapshot_and_grade_filter(boundary):
    w=boundary
    w['db'].execute("UPDATE qualification_tests SET certified_grade='middle', certified_specialization='backend_python', certified_at=now(), certified_score=88 WHERE resume_id=%s", (w['rid'],))
    data=discovery(w, True)
    assert data['items'][0]['confirmed_grade']=='middle'
    assert data['items'][0]['category_scope']=='role-knowledge'
    assert w['e'].get('/candidates', params={'q':w['cu']['subject_id'],'grade':'senior'}).json()['total']==0


@pytest.mark.parametrize('change', ["revoked_at=now()", "valid_until=now()-interval '1 second'", "issued_at=now()+interval '1 day'"])
def test_revocation_expiry_and_future_certificate_prevent_legacy_resurrection(boundary, change):
    w=boundary
    cid=certificate(w)
    w['db'].execute("UPDATE qualification_tests SET certified_grade='middle', certified_specialization='backend_python', certified_at=now() WHERE resume_id=%s", (w['rid'],))
    w['db'].execute("UPDATE candidates SET confirmed_grade='senior',test_valid_until=now()+interval '90 days',assessment_method='expert-dialogue-1.2' WHERE id=%s", (w['cu']['subject_id'],))
    w['db'].execute('UPDATE qualification_certificates SET '+change+' WHERE id=%s', (cid,))
    discovery(w, False)
    assert w['e'].post('/invitations', json=offer(w)).status_code==404


@pytest.mark.parametrize('control', ['hidden', 'disputed'])
def test_evidence_controls_remove_search_invitation_graph_and_twin_pool(boundary, control):
    w=boundary
    response=w['e'].post('/vacancies',json=dict(title='Python API team',description='Разработка и сопровождение Python API.',specialization='backend_python',grade='middle',skills=['Python'],salary_from=180000,salary_to=250000,work_format='удалённо',status='published'))
    response.raise_for_status()
    vid=response.json()['vacancy']['id']
    pair='/intelligence/evidence-lab/compatibility/'+w['rid']+'/'+vid
    assert w['e'].get(pair).status_code==404
    cid=certificate(w)
    assert w['e'].get(pair).status_code==200
    discovery(w, True)
    w['db'].execute('INSERT INTO intelligence.evidence_controls(user_id,evidence_id,'+control+') VALUES(%s,%s,true)', (w['cu']['id'],'cert:'+cid))
    discovery(w, False)
    assert w['e'].post('/invitations',json=offer(w)).status_code==404
    assert w['e'].get('/intelligence/graph/candidate/'+w['cu']['subject_id']).status_code==404
    assert w['e'].get(pair).status_code==404


@pytest.mark.parametrize('mismatch', ['candidate', 'specialization'])
def test_certificate_cannot_be_borrowed_from_another_subject_or_role(boundary, mismatch):
    w=boundary
    certificate(w, **({'candidate_id':w['ou']['subject_id']} if mismatch=='candidate' else {'specialization':'data_analysis'}))
    discovery(w, False)


def test_failed_retest_and_review_signal_preserve_valid_proof_until_finding(boundary):
    w=boundary
    certificate(w)
    w['db'].execute("UPDATE qualification_tests SET passed=false,status='cooldown',score=0 WHERE resume_id=%s", (w['rid'],))
    case='RC'+uuid.uuid4().hex
    w['db'].execute("INSERT INTO intelligence.review_cases(id,user_id,artifact_id,task_key,evidence) VALUES(%s,%s,%s,'role-knowledge-response-pattern','{}')", (case,w['cu']['id'],w['rid']))
    assert discovery(w, True)['items'][0]['test_score']==90
    w['db'].execute("UPDATE intelligence.review_cases SET status='confirmed' WHERE id=%s", (case,))
    discovery(w, False)
    w['db'].execute("UPDATE intelligence.review_cases SET status='challenged' WHERE id=%s", (case,))
    discovery(w, False)  # An appeal does not erase the established finding.
    w['db'].execute("UPDATE intelligence.review_cases SET status='dismissed' WHERE id=%s", (case,))
    discovery(w, True)


def test_no_vacancy_offer_and_explicit_contact_grant_remain_available(boundary):
    w=boundary
    cid=certificate(w)
    response=w['e'].post('/invitations',json=offer(w))
    response.raise_for_status()
    invitation=response.json()['invitation']['id']
    w['c'].put('/invitations/'+invitation, json={'status':'accepted'}).raise_for_status()
    w['db'].execute('UPDATE qualification_certificates SET revoked_at=now() WHERE id=%s', (cid,))
    assert w['e'].get('/candidates',params={'q':w['cu']['subject_id']}).json()['total']==0
    detail=w['e'].get('/candidates/'+w['cu']['subject_id'])
    detail.raise_for_status()
    assert detail.json()['contacts_released']
    assert detail.json()['candidate']['confirmed_grade'] is None


def test_idempotency_key_is_bound_to_resume_too(boundary):
    w=boundary
    certificate(w)
    response=w['c'].post('/resumes',json=w['body'] | {'target_position':'Python engineer second profile'})
    response.raise_for_status()
    second=response.json()['resume']['id']
    certificate(w,resume_id=second)
    payload=offer(w)
    w['e'].post('/invitations',json=payload).raise_for_status()
    assert w['e'].post('/invitations',json=payload | {'resume_id':second}).status_code==409


@pytest.mark.parametrize('field', ['consent_publication', 'consent_processing'])
def test_consent_revocation_excludes_discovery_and_invitations(boundary, field):
    w=boundary
    certificate(w)
    discovery(w,True)
    w['db'].execute('UPDATE candidates SET '+field+'=false WHERE id=%s', (w['cu']['subject_id'],))
    discovery(w,False)
    assert w['e'].post('/invitations',json=offer(w)).status_code==404


@pytest.mark.parametrize('method', ['synthetic_scenario', 'legacy'])
def test_historical_synthetic_profile_has_an_explicit_scope_and_valid_offer_fk(boundary,method):
    w=boundary;cid=w['cu']['subject_id']
    w['db'].execute('DELETE FROM resume_profiles WHERE id=%s',(w['rid'],))
    w['db'].execute("UPDATE candidates SET specialization='backend_python',declared_grade='middle',confirmed_grade='middle',test_score=90,test_valid_until=now()+interval '90 days',assessment_method='synthetic_scenario',visibility='employer_searchable' WHERE id=%s",(cid,))
    w['db'].execute('UPDATE candidates SET assessment_method=%s WHERE id=%s',(method,cid))
    w['db'].execute("INSERT INTO assessments(id,candidate_id,specialization,grade,blueprint_version,seed,items,status,score,finished_at,synthetic) VALUES(%s,%s,'backend_python','middle','boundary-fixture','fixture','[]','completed_seed',90,now(),true)",('BA'+uuid.uuid4().hex,cid))
    data=discovery(w,True)
    assert data['items'][0]['category_scope']=='synthetic-scenario'
    response=w['e'].post('/invitations',json=offer(w,resume_id='Rlegacy_'+cid))
    response.raise_for_status()
    assert response.json()['invitation']['resume_id'] is None
    w['db'].execute('UPDATE candidates SET synthetic=false WHERE id=%s',(cid,))
    assert w['e'].get('/candidates',params={'q':cid}).json()['total']==0


def test_role_review_retains_the_actual_knowledge_score(boundary):
    w=boundary
    w['db'].execute("UPDATE qualification_tests SET certified_grade='middle',certified_specialization='backend_python',certified_score=92,certified_at=now() WHERE resume_id=%s",(w['rid'],))
    certificate(w,scope='role-reviewed')
    item=discovery(w,True)['items'][0]
    assert item['category_scope']=='role-reviewed' and item['test_score']==92


def test_unbound_acceptance_does_not_expose_future_private_resumes(boundary):
    w=boundary
    certificate(w)
    response=w['e'].post('/invitations',json=offer(w,resume_id=None))
    response.raise_for_status()
    w['c'].put('/invitations/'+response.json()['invitation']['id'],json={'status':'accepted'}).raise_for_status()
    w['db'].execute("UPDATE resume_profiles SET visibility='private',status='draft' WHERE id=%s",(w['rid'],))
    private=w['c'].post('/resumes',json=w['body'] | {'target_position':'Private future role','visibility':'private'})
    private.raise_for_status()
    assert w['e'].get('/candidates/'+w['cu']['subject_id']).status_code==404
