"""End-to-end contract for private candidate--employer conversations."""
import uuid

from test_api import world


def test_private_conversation_is_created_read_and_isolated(world):
    candidate = world["candidate"]
    employer = world["employer"]
    outsider = world["other"]
    db = world["db"]
    candidate_id = world["cu"]["subject_id"]
    company_id = world["eu"]["subject_id"]

    # Make a normal, searchable candidate only so the invitation path can be
    # exercised without calling the LLM worker. The resume is a test fixture;
    # the conversations themselves are created only through public API actions.
    profile = candidate.get("/profile").json()["profile"]
    profile.update(
        specialization="backend_python",
        declared_grade="junior",
        full_name="Private chat fixture",
        phone="+7 000 000-00-00",
        skills=["Python", "FastAPI"],
        about="Developed a Python API and reviewed production incidents.",
        expected_salary=150000,
        consent_publication=True,
        visibility="employer_searchable",
    )
    candidate.put("/profile", json=profile).raise_for_status()
    resume_id = "Rchat" + uuid.uuid4().hex
    db.execute(
        "INSERT INTO resume_profiles(id,candidate_id,target_position,specialization,declared_grade,experience_years,skills,about,expected_salary,work_format,visibility,status) VALUES(%s,%s,'Backend API Engineer','backend_python','junior',2,ARRAY['Python','FastAPI'],'Production API work',150000,'remote','employer_searchable','published')",
        (resume_id, candidate_id),
    )
    db.execute(
        "INSERT INTO qualification_certificates(id,candidate_id,resume_id,specialization,grade,skills,assessment_version,attempt) VALUES(%s,%s,%s,'backend_python','junior','[\"Python\"]','chat-boundary-fixture','{\"score\":80}')",
        ('CERT'+uuid.uuid4().hex, candidate_id, resume_id),
    )

    vacancy = employer.post(
        "/vacancies",
        json={
            "title": "Backend API Engineer",
            "description": "Develop reliable Python APIs and participate in architecture reviews.",
            "specialization": "backend_python",
            "grade": "junior",
            "skills": ["Python", "FastAPI"],
            "salary_from": 150000,
            "salary_to": 220000,
            "work_format": "remote",
            "status": "published",
        },
    )
    vacancy.raise_for_status()
    vacancy_id = vacancy.json()["vacancy"]["id"]

    application = candidate.post(
        f"/vacancies/{vacancy_id}/apply",
        json={"message": "I would like to discuss the API role.", "resume_id": resume_id},
    )
    application.raise_for_status()
    application_thread = application.json()["conversation_id"]

    candidate_threads = candidate.get("/conversations")
    candidate_threads.raise_for_status()
    listed = next(
        item
        for item in candidate_threads.json()["items"]
        if item["id"] == application_thread
    )
    assert listed["origin"] == "application"
    assert listed["vacancy_id"] == vacancy_id
    assert listed["resume_id"] == resume_id
    assert listed["unread_count"] == 0

    assert candidate.post(
        f"/conversations/{application_thread}/messages", json={"body": "   "}
    ).status_code == 400
    sent = candidate.post(
        f"/conversations/{application_thread}/messages",
        json={"body": "I led the release preparation and can explain the trade-offs."},
    )
    sent.raise_for_status()
    assert sent.json()["message"]["read_at"] is None

    employer_threads = employer.get("/conversations")
    employer_threads.raise_for_status()
    employer_item = next(
        item
        for item in employer_threads.json()["items"]
        if item["id"] == application_thread
    )
    assert employer_item["unread_count"] == 1
    assert employer_item["other_kind"] == "candidate"

    # A company that has no invitation/application relation cannot enumerate,
    # read, mark or send a message in this thread.
    assert outsider.get("/conversations").json()["items"] == []
    assert outsider.get(f"/conversations/{application_thread}").status_code == 404
    assert outsider.post(
        f"/conversations/{application_thread}/messages", json={"body": "intrusion"}
    ).status_code == 404
    assert outsider.post(f"/conversations/{application_thread}/read").status_code == 404

    history = employer.get(f"/conversations/{application_thread}")
    history.raise_for_status()
    assert len(history.json()["messages"]) == 1
    assert history.json()["messages"][0]["body"].startswith("I led")
    marked = employer.post(f"/conversations/{application_thread}/read")
    marked.raise_for_status()
    assert marked.json()["marked"] == 1
    assert candidate.get(f"/conversations/{application_thread}").json()["messages"][0]["read_at"]

    # Revoking direct contact data does not expose data and does not break the
    # platform-internal thread. This is the declared distinction in the UI.
    candidate.post("/account/contact-access", json={"company_id": company_id}).raise_for_status()
    assert employer.get(f"/candidates/{candidate_id}").json()["contacts"] is None
    after_revoke = candidate.post(
        f"/conversations/{application_thread}/messages",
        json={"body": "Please keep all communication in this private channel."},
    )
    after_revoke.raise_for_status()
    assert employer.get("/conversations").json()["items"][0]["contact_revoked"] is True
    exported = candidate.get("/account/export")
    exported.raise_for_status()
    assert any(
        item["conversation"]["id"] == application_thread
        and len(item["messages"]) == 2
        for item in exported.json()["conversations"]
    )

    invitation_payload = {
        "candidate_id": candidate_id,
        "resume_id": resume_id,
        "vacancy_id": vacancy_id,
        "title": "Backend API Engineer offer",
        "description": "A private invitation for the same target role.",
        "salary_from": 160000,
        "salary_to": 230000,
        "idempotency_key": uuid.uuid4().hex,
    }
    invitation = employer.post("/invitations", json=invitation_payload)
    invitation.raise_for_status()
    invitation_thread = invitation.json()["conversation_id"]
    assert invitation_thread == application_thread
    repeated = employer.post("/invitations", json=invitation_payload)
    repeated.raise_for_status()
    assert repeated.json()["conversation_id"] == application_thread
