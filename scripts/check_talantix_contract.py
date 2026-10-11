"""Exercise the Rust Talantix connector against a local HTTP contract server.

No real Talantix token, candidate or external network call is used.  A second API
process runs on 18082 against the isolated local database, then the script checks
the complete path: token check, catalogue, source, vacancy map, explicit candidate
consent, durable outbox and the GraphQL CreatePerson mutation.
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import sys
import time
import uuid

import httpx
import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "http://127.0.0.1:18082"
BASE = ORIGIN + "/api"
MOCK_PORT = 18081
CALLS: list[str] = []


class TalantixMock(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        return

    def _json(self, status: int, body: dict):
        raw = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/auth_check" and self.headers.get("Authorization") == "Bearer contract-access-token-1234567890":
            self.send_response(204)
            self.end_headers()
            return
        self._json(401, {"type": "invalid_token"})

    def do_POST(self):
        size = int(self.headers.get("Content-Length", "0"))
        data = json.loads(self.rfile.read(size) or b"{}")
        query = data.get("query", "")
        CALLS.append(query)
        if self.path != "/graphql" or self.headers.get("Authorization") != "Bearer contract-access-token-1234567890":
            self._json(401, {"error": "unauthorized"})
        elif "PersonSources" in query:
            self._json(200, {"data": {"personSources": {"items": [{"id": 11, "name": "ФСП · Траектория"}], "pageInfo": {"endCursor": None, "hasNextPage": False}}}})
        elif "VacancyList" in query:
            self._json(200, {"data": {"vacancies": {"items": [{"id": 9001, "title": "Backend · contract", "department": "IT", "status": "active", "createdAt": 0, "salary": {"currency": "RUR", "from": 100000, "to": 200000}}], "pageInfo": {"endCursor": None, "hasNextPage": False}}}})
        elif "CreatePerson" in query:
            self._json(200, {"data": {"createPerson": {"id": 444}}})
        else:
            self._json(400, {"errors": [{"message": "unexpected query"}]})


def wait_ready(process: subprocess.Popen):
    for _ in range(80):
        if process.poll() is not None:
            raise RuntimeError("Contract API exited before ready")
        try:
            if httpx.get(BASE + "/health", timeout=1, trust_env=False).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    raise RuntimeError("Contract API did not become ready")


def register(client: httpx.Client, role: str, name: str):
    password = "ContractOnly-2026-Long"
    email = f"talantix-contract-{uuid.uuid4().hex}@example.test"
    response = client.post("/auth/register", json={"email": email, "password": password, "role": role, "name": name, "consent_processing": True})
    response.raise_for_status()
    token = response.json()["development_mail"]["token"]
    response = client.post("/auth/verify", json={"token": token})
    response.raise_for_status()
    return response.json()["user"]


def cleanup(conn, users: list[dict]):
    subjects = [user["subject_id"] for user in users]
    identities = [user["id"] for user in users]
    with conn.transaction():
        conn.execute("DELETE FROM audit_events WHERE actor_id=ANY(%s)", (identities,))
        conn.execute("DELETE FROM documents WHERE user_id=ANY(%s)", (identities,))
        conn.execute("DELETE FROM saved_searches WHERE company_id=ANY(%s)", (subjects,))
        conn.execute("DELETE FROM micro_tasks WHERE company_id=ANY(%s) OR candidate_id=ANY(%s)", (subjects, subjects))
        conn.execute("DELETE FROM invitations WHERE company_id=ANY(%s) OR candidate_id=ANY(%s)", (subjects, subjects))
        conn.execute("DELETE FROM applications WHERE candidate_id=ANY(%s) OR vacancy_id IN(SELECT id FROM vacancies WHERE company_id=ANY(%s))", (subjects, subjects))
        conn.execute("DELETE FROM assessments WHERE candidate_id=ANY(%s)", (subjects,))
        conn.execute("DELETE FROM vacancies WHERE company_id=ANY(%s)", (subjects,))
        conn.execute("DELETE FROM users WHERE id=ANY(%s)", (identities,))
        conn.execute("DELETE FROM candidates WHERE id=ANY(%s)", (subjects,))
        conn.execute("DELETE FROM companies WHERE id=ANY(%s)", (subjects,))


def main():
    load_dotenv(ROOT / ".env")
    mock = ThreadingHTTPServer(("127.0.0.1", MOCK_PORT), TalantixMock)
    import threading
    thread = threading.Thread(target=mock.serve_forever, daemon=True)
    thread.start()
    environment = os.environ.copy()
    environment.update(BIND_ADDR="127.0.0.1:18082", BASE_URL=ORIGIN, FSP_SERVICE="all", TALANTIX_API_BASE=f"http://127.0.0.1:{MOCK_PORT}")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    log = (ROOT / "runtime/talantix-contract-api.log").open("wb")
    process = subprocess.Popen([ROOT / "target/release/fsp-trajectory.exe"], cwd=ROOT, stdout=log, stderr=log, env=environment, creationflags=flags)
    users: list[dict] = []
    connection = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)
    try:
        wait_ready(process)
        headers = {"Origin": ORIGIN}
        employer = httpx.Client(base_url=BASE, headers=headers, timeout=20, trust_env=False)
        candidate = httpx.Client(base_url=BASE, headers=headers, timeout=20, trust_env=False)
        try:
            employer_user = register(employer, "employer", "Talantix contract employer")
            candidate_user = register(candidate, "candidate", "Talantix contract candidate")
            users.extend([employer_user, candidate_user])
            profile = candidate.get("/profile").json()["profile"]
            profile.update(full_name="Contract Candidate", phone="+79990000000", specialization="backend_python", declared_grade="junior", industry="IT", experience_years=2, skills=["Python", "FastAPI"], soft_skills=[], about="Synthetic contract profile", expected_salary=150000, work_format="remote", visibility="private", consent_processing=True, consent_publication=False)
            assert candidate.put("/profile", json=profile).status_code == 200
            # Isolate the ATS contract from unrelated asynchronous qualification
            # generation; applications now require an owned target resume.
            resume_id = "ATS" + uuid.uuid4().hex
            connection.execute("INSERT INTO resume_profiles(id,candidate_id,target_position,specialization,declared_grade,experience_years,skills,about,expected_salary,visibility,status) VALUES(%s,%s,'Backend developer','backend_python','junior',2,ARRAY['Python','FastAPI'],'Controlled ATS contract resume',150000,'private','draft')",(resume_id,candidate_user['subject_id']))
            vacancy = {"title": "Backend contract vacancy", "description": "Synthetic vacancy used to validate Talantix delivery.", "specialization": "backend_python", "grade": "junior", "skills": ["Python", "FastAPI"], "salary_from": 100000, "salary_to": 200000, "work_format": "remote", "status": "published"}
            response = employer.post("/vacancies", json=vacancy)
            assert response.status_code == 200, response.text
            vacancy_id = response.json()["vacancy"]["id"]
            tokens = {"access_token": "contract-access-token-1234567890", "refresh_token": "contract-refresh-token-1234567890", "expires_in": 86400, "refresh_token_expires_in": 10368000}
            response = employer.put("/integrations/talantix", json=tokens)
            assert response.status_code == 200, response.text
            catalogue = employer.get("/integrations/talantix/catalogue")
            assert catalogue.status_code == 200, catalogue.text
            assert catalogue.json()["sources"][0]["id"] == 11
            assert catalogue.json()["vacancies"][0]["id"] == 9001
            assert employer.put("/integrations/talantix/source", json={"source_id": 11}).status_code == 200
            assert employer.put(f"/vacancies/{vacancy_id}/integrations/talantix", json={"external_vacancy_id": 9001}).status_code == 200
            response = candidate.post(f"/vacancies/{vacancy_id}/apply", json={"message": "Contract consent", "share_with_ats": True,"resume_id":resume_id})
            assert response.status_code == 200, response.text
            for _ in range(60):
                status = employer.get("/integrations/talantix").json()["connection"]
                if status.get("outbox", {}).get("sent") == 1:
                    break
                time.sleep(0.25)
            else:
                raise AssertionError(f"ATS delivery did not complete: {status}")
            created = [query for query in CALLS if "CreatePerson" in query]
            assert len(created) == 1
            assert "sourceId: 11" in created[0] and "vacancyIds: [9001]" in created[0]
        finally:
            employer.close()
            candidate.close()
    finally:
        cleanup(connection, users)
        connection.close()
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        log.close()
        mock.shutdown()
        mock.server_close()
    print("Talantix contract check: token validation, catalogue, mapping, consented outbox and CreatePerson passed")
    report={"passed":True,"method":"Real Rust adapter and durable database outbox against a local HTTP GraphQL contract server; no external ATS delivery.","checks":["token validation","catalogue and source","vacancy mapping","explicit candidate consent","durable outbox","one CreatePerson with selected source/vacancy"],"create_person_calls":len(created),"measured_at":time.strftime('%Y-%m-%dT%H:%M:%S%z')}
    (ROOT/'validation/reports/current/talantix-contract.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__ == "__main__":
    main()
