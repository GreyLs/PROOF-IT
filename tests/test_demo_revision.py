"""Scoped access-policy checks through real password/registration HTTP flows."""
import uuid
import httpx
import pytest
from scripts.workbench_test_fixture import Fixture

LOGINS = {'candidate': 'candidate@demo.proofit.invalid', 'employer': 'employer@demo.proofit.invalid'}
PASSWORD = 'Proofit-Demo-2026!'

@pytest.fixture(scope='module')
def world():
    fixture = Fixture()
    clients = []
    def client():
        instance = httpx.Client(base_url=fixture.cfg['BASE_URL']+'/api',
            headers={'Origin': fixture.cfg['BASE_URL']}, timeout=60, trust_env=False)
        clients.append(instance)
        return instance
    def login(instance, role):
        response = instance.post('/auth/login', json={'identifier': LOGINS[role], 'password': PASSWORD,
            'role': 'employer' if role == 'candidate' else 'candidate'})
        assert response.status_code == 200, response.text
        assert response.json()['user']['role'] == role
        return response.json()['user']
    def register(role):
        instance = client()
        email = 'access-'+uuid.uuid4().hex+'@example.test'
        password = 'Access-Verification-2026!'
        response = instance.post('/auth/register', json={'email': email, 'password': password,
            'role': role, 'name': 'Проверка авторизованного доступа '+uuid.uuid4().hex[:8], 'consent_processing': True})
        assert response.status_code == 200, response.text
        uid, subject = fixture.db.execute('SELECT id,subject_id FROM users WHERE email=%s', (email,)).fetchone()
        fixture.users.append({'id': uid, 'subject_id': subject, 'role': role})
        assert instance.post('/auth/login', json={'identifier': email, 'password': password}).status_code == 403
        assert instance.post('/auth/verify', json={'token': response.json()['development_mail']['token']}).status_code == 200
        assert instance.post('/auth/logout').status_code == 200
        response = instance.post('/auth/login', json={'identifier': email, 'password': password})
        assert response.status_code == 200 and response.json()['user']['role'] == role
        return instance, response.json()['user']
    yield fixture, client, login, register
    for instance in clients:
        # Revoke only sessions owned by this test client.
        if instance.cookies:
            instance.post('/auth/logout')
        instance.close()
    fixture.close()

@pytest.mark.parametrize('method,path,payload', [
    ('POST', '/auth/guest', {'consent_processing': True, 'role': 'candidate'}),
    ('POST', '/auth/demo-switch', {'role': 'employer'}),
    ('GET', '/auth/demo-credentials', None),
])
def test_removed_entry_points_issue_no_session(world, method, path, payload):
    fixture, client, _, _ = world
    instance = client()
    before = fixture.db.execute('SELECT count(*) FROM users').fetchone()[0]
    response = instance.request(method, path, json=payload) if payload is not None else instance.get(path)
    assert response.status_code in (404, 405)
    assert 'set-cookie' not in response.headers
    assert instance.get('/auth/me').status_code == 401
    assert fixture.db.execute('SELECT count(*) FROM users').fetchone()[0] == before

def test_private_api_requires_authentication(world):
    _, client, _, _ = world
    instance = client()
    for path in ('/auth/me', '/auth/demo-context', '/profile', '/resumes', '/applications', '/documents'):
        assert instance.get(path).status_code == 401, path

@pytest.mark.parametrize('role', ('candidate', 'employer'))
def test_password_login_stored_role_seeded_data_and_logout(world, role):
    _, client, login, _ = world
    instance = client()
    assert instance.post('/auth/login', json={'identifier': LOGINS[role], 'password': 'incorrect-password'}).status_code == 401
    assert instance.get('/auth/me').status_code == 401
    user = login(instance, role)
    assert user['synthetic']
    context = instance.get('/auth/demo-context').json()['workspace']
    assert context['shared']
    if role == 'candidate':
        resumes = instance.get('/resumes').json()['items']
        assert len(resumes) >= 2 and all(item['candidate_id'] == user['subject_id'] for item in resumes)
        assert instance.get('/candidates').status_code == 403
        assert len(instance.get('/vacancies', params={'company_id': context['company_id']}).json()['items']) >= 2
    else:
        vacancies = instance.get('/vacancies', params={'mine': True}).json()['items']
        assert len(vacancies) >= 2 and all(item['company_id'] == user['subject_id'] for item in vacancies)
        assert instance.get('/resumes').status_code == 403
    assert instance.post('/auth/demo-switch', json={'role': 'employer' if role == 'candidate' else 'candidate'}).status_code in (404, 405)
    assert instance.get('/auth/me').json()['user']['role'] == role
    assert instance.post('/auth/logout').status_code == 200
    assert instance.get('/auth/me').status_code == 401

@pytest.mark.parametrize('role', ('candidate', 'employer'))
def test_own_registration_verification_and_password_login(world, role):
    _, _, _, register = world
    instance, user = register(role)
    assert not user['synthetic']
    assert instance.get('/auth/demo-context').json()['workspace'] is None
    assert instance.post('/auth/logout').status_code == 200
    assert instance.get('/auth/me').status_code == 401

def test_legacy_guest_sessions_revoked_without_deleting_accounts(world):
    fixture, _, _, _ = world
    assert fixture.db.execute('SELECT count(*) FROM sessions s JOIN users u ON u.id=s.user_id WHERE u.is_guest').fetchone()[0] == 0
    assert fixture.db.execute("SELECT count(*) FROM users WHERE email=ANY(%s) AND NOT is_guest", (list(LOGINS.values()),)).fetchone()[0] == 2

def test_application_visible_after_separate_employer_password_login(world):
    _, client, login, register = world
    candidate, user = register('candidate')
    resume = candidate.post('/resumes', json={'target_position': 'Python Backend Engineer',
        'specialization': 'backend_python', 'declared_grade': 'middle', 'experience_years': 4,
        'skills': ['Python', 'SQL', 'PostgreSQL'], 'about': 'Синтетическое резюме для проверки авторизованного сквозного сценария.',
        'expected_salary': 180000, 'work_format': 'удалённо', 'visibility': 'private'})
    assert resume.status_code == 200, resume.text
    employer = client()
    login(employer, 'employer')
    vacancy = next(item for item in employer.get('/vacancies', params={'mine': True}).json()['items'] if item['specialization'] == 'backend_python')
    message = 'Authenticated access verification '+uuid.uuid4().hex
    response = candidate.post('/vacancies/'+vacancy['id']+'/apply', json={
        'message': message, 'resume_id': resume.json()['resume']['id'], 'share_with_ats': False})
    assert response.status_code == 200, response.text
    application = response.json()['application']['id']
    assert candidate.post('/auth/logout').status_code == 200
    assert candidate.get('/applications').status_code == 401
    # A fresh login, not a role-switch endpoint, opens the other cabinet.
    assert employer.post('/auth/logout').status_code == 200
    login(employer, 'employer')
    incoming = next(item for item in employer.get('/applications').json()['items'] if item['id'] == application)
    assert incoming['candidate']['id'] == user['subject_id'] and incoming['message'] == message
    assert employer.put('/applications/'+application, json={'status': 'interview'}).status_code == 200
    assert employer.post('/auth/logout').status_code == 200
