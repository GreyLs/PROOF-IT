"""Four full journeys: Qwen generation/review plus HTTP contracts.

The server answer key is used only as a synthetic expert fixture after the
public response is proven not to contain it. It validates scoring without
pretending that a model solving its own questions is independent QA.
"""
from pathlib import Path
import hashlib, json, os, sys, time, uuid

import httpx
import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')
BASE, ORIGIN = 'http://localhost:8080/api', 'http://localhost:8080'
SCENARIOS = [
    ('backend_python', 'junior', 'Junior Python Developer', ['Python', 'PostgreSQL'], 'Built an order API, validated data and wrote SQL queries.'),
    ('frontend_development', 'middle', 'Middle Frontend Engineer', ['TypeScript', 'React'], 'Built account interfaces, designed form state and measured web vitals.'),
    ('lead_engineering', 'senior', 'Engineering Team Lead', ['Python', 'PostgreSQL', 'Docker'], 'Led a backend team, decomposed delivery, defined SLO and safe rollout.'),
    ('devops', 'senior', 'Senior DevOps Engineer', ['Kubernetes', 'Docker', 'PostgreSQL'], 'Owned platform reliability, Kubernetes infrastructure, recovery and SLO measurement.'),
]


def register(role, name):
    client = httpx.Client(base_url=BASE, headers={'Origin': ORIGIN}, timeout=httpx.Timeout(330), trust_env=False)
    response = client.post('/auth/register', json={
        'email': f'four-path-{uuid.uuid4().hex}@example.test',
        'password': 'FourPaths-2026-Synthetic', 'role': role, 'name': name,
        'consent_processing': True,
    })
    response.raise_for_status()
    response = client.post('/auth/verify', json={'token': response.json()['development_mail']['token']})
    response.raise_for_status()
    return client, response.json()['user']


def wait_for_test(client, resume_id):
    started, deadline = time.perf_counter(), time.time() + 720
    while time.time() < deadline:
        response = client.get(f'/resumes/{resume_id}/test')
        response.raise_for_status()
        body = response.json()
        if body['status'] == 'ready':
            return body, round(time.perf_counter() - started, 3)
        if body['generation_status'] == 'failed':
            raise AssertionError(body)
        time.sleep(2)
    raise TimeoutError(resume_id)


def synthetic_expert_answers(resume_id):
    with psycopg.connect(os.environ['DATABASE_URL']) as db:
        result = db.execute('SELECT questions FROM qualification_tests WHERE resume_id=%s', (resume_id,)).fetchone()[0]
    questions, review = result['questions'], result['review']
    required = ['clear', 'role_fit', 'grade_fit', 'single_or_explicit_multiple',
                'options_plausible', 'no_code_writing', 'answer_key_consistent']
    assert len(questions) == 10 and all(review.get(flag) is True for flag in required), review
    return [question['correct'] for question in questions], {flag: review[flag] for flag in required}


def cleanup(users):
    if not users:
        return
    ids, subjects = [user['id'] for user in users], [user['subject_id'] for user in users]
    with psycopg.connect(os.environ['DATABASE_URL']) as db:
        with db.transaction():
            db.execute('INSERT INTO file_deletions(storage_key) SELECT storage_key FROM documents WHERE user_id=ANY(%s) ON CONFLICT DO NOTHING', (ids,))
            db.execute('DELETE FROM audit_events WHERE actor_id=ANY(%s)', (ids,))
            db.execute('DELETE FROM documents WHERE user_id=ANY(%s)', (ids,))
            db.execute('DELETE FROM invitations WHERE candidate_id=ANY(%s) OR company_id=ANY(%s)', (subjects, subjects))
            db.execute('DELETE FROM applications WHERE candidate_id=ANY(%s) OR vacancy_id IN(SELECT id FROM vacancies WHERE company_id=ANY(%s))', (subjects, subjects))
            db.execute('DELETE FROM vacancies WHERE company_id=ANY(%s)', (subjects,))
            db.execute('DELETE FROM users WHERE id=ANY(%s)', (ids,))
            db.execute('DELETE FROM candidates WHERE id=ANY(%s)', (subjects,))
            db.execute('DELETE FROM companies WHERE id=ANY(%s)', (subjects,))


def main():
    users, reports, candidates, employers = [], [], [], []
    out = {
        'passed': False, 'model': os.getenv('OLLAMA_MODEL', 'qwen3:8b'),
        'generated_and_reviewed_by_local_qwen': True,
        'synthetic_answer_mode': 'server-held answer key after public key-hiding assertion',
        'independent_validation': False, 'runs': reports,
    }
    try:
        for index, (spec, grade, title, skills, about) in enumerate(SCENARIOS):
            client, user = register('candidate', f'Candidate {index + 1}')
            users.append(user)
            profile = client.get('/profile').json()['profile']
            profile.update({'consent_publication': True, 'visibility': 'employer_searchable'})
            client.put('/profile', json=profile).raise_for_status()
            response = client.post('/resumes', json={
                'target_position': title, 'specialization': spec, 'declared_grade': grade,
                'experience_years': 2 + index * 2, 'skills': skills, 'about': about,
                'expected_salary': 140000 + index * 40000, 'work_format': 'remote',
                'visibility': 'employer_searchable',
            })
            response.raise_for_status()
            resume = response.json()['resume']
            public_test, generation_seconds = wait_for_test(client, resume['id'])
            public_wire = json.dumps(public_test)
            assert len(public_test['questions']) == 10 and 'correct' not in public_wire and 'rationale' not in public_wire
            answers, review = synthetic_expert_answers(resume['id'])
            client.post(f"/resumes/{resume['id']}/test/start").raise_for_status()
            final = client.post(f"/resumes/{resume['id']}/test/submit", json={'answers': answers})
            final.raise_for_status()
            reports.append({
                'role': spec, 'grade': grade, 'resume_id': resume['id'],
                'generation_seconds': generation_seconds, 'review': review,
                'public_answer_key_hidden': True, 'test': final.json(),
            })
            candidates.append((client, user, resume))

        # The public API allows declaration only. This direct update represents
        # the mocked FSP registry integration named in the task specification.
        candidate_client, candidate_user, _ = candidates[0]
        candidate_client.post('/fsp/participations', json={
            'event_name': 'FSP validation event', 'discipline': 'software engineering',
            'event_date': '2026-09-20', 'result': 'finalist', 'source_url': 'https://example.test/fsp-protocol',
        }).raise_for_status()
        with psycopg.connect(os.environ['DATABASE_URL']) as db:
            db.execute("UPDATE candidates SET employment_check='{\"status\":\"aligned\"}'::jsonb WHERE id=%s", (candidate_user['subject_id'],))
            db.execute("UPDATE fsp_participations SET status='mock_verified',verified_at=now() WHERE candidate_id=%s", (candidate_user['subject_id'],))

        for index, (spec, grade, title, skills, _about) in enumerate(SCENARIOS):
            client, user = register('employer', f'Company {index + 1}')
            users.append(user)
            employers.append(client)
            client.put('/company', json={
                'name': f'Company {index + 1}', 'description': 'Technology company for end-to-end validation.',
                'industry': 'IT', 'contact': f'hr{index}@example.test',
            }).raise_for_status()
            vacancy = client.post('/vacancies', json={
                'title': title, 'description': f'{title}: solutions, quality and ownership of outcome.',
                'specialization': spec, 'grade': grade, 'skills': skills,
                'salary_from': 120000 + index * 40000, 'salary_to': 250000 + index * 50000,
                'work_format': 'remote', 'status': 'published',
            })
            vacancy.raise_for_status()
            vacancy_id = vacancy.json()['vacancy']['id']
            matches = client.get('/candidates', params={'vacancy_id': vacancy_id})
            matches.raise_for_status()
            reports[index]['vacancy_id'] = vacancy_id
            reports[index]['employer_matches'] = [
                {'candidate': item['id'], 'resume': item['resume_id'], 'target': item['target_position'], 'tier': item['relevance']}
                for item in matches.json()['items'][:5]
            ]
            candidate_matches = candidates[index][0].get('/vacancies/recommended', params={'resume_id': candidates[index][2]['id']})
            candidate_matches.raise_for_status()
            reports[index]['candidate_top_match'] = candidate_matches.json()['items'][0]['vacancy']['id']

        out.update({
            'passed': len(reports) == len(SCENARIOS) and all(item['test']['passed'] for item in reports),
            'source_sha256': {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in ['worker/qualification.py', 'src/resumes.rs', 'src/matching.rs']},
        })
    except Exception as exc:
        out['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        for client, _, _ in candidates:
            client.close()
        for client in employers:
            client.close()
        cleanup(users)
    (ROOT / 'validation/reports/current/four-resumes-four-vacancies-results.json').write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'passed': out['passed'], 'runs': len(reports)}, ensure_ascii=False))
    sys.exit(0 if out['passed'] else 1)


if __name__ == '__main__':
    main()
