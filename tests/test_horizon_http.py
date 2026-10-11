"""Live authorization/transaction/queue checks; no performance traffic."""
import time,uuid

import pytest
from scripts.workbench_test_fixture import Fixture

@pytest.fixture(scope="module")
def world():
    fixture = Fixture()
    try:
        c,cu = fixture.register("candidate")
        e,eu = fixture.register("employer")
        o,ou = fixture.register("candidate")
        r=c.post("/resumes",json={"target_position":"Python Developer","specialization":"backend_python","declared_grade":"middle","skills":["Python","SQL"],"experience_years":3,"expected_salary":180000,"about":"Разрабатываю API, пишу тесты и работаю с транзакциями.","work_format":"удалённо","visibility":"private"})
        assert r.status_code==200,r.text
        resume=c.get("/resumes").json()["items"][0]["id"]
        yield {"c":c,"e":e,"o":o,"cu":cu,"eu":eu,"resume":resume,"db":fixture.db}
    finally:
        fixture.close()


def finish(client, job_id):
    for _ in range(90):
        r=client.get("/intelligence/jobs/"+job_id)
        assert r.status_code==200,r.text
        p=r.json()
        if p["status"] in ("done","failed"):
            assert p["status"]=="done",p
            return p["result"]
        time.sleep(.25)
    raise AssertionError("job did not complete")


def test_role_and_preference_privacy(world):
    assert world["e"].get("/intelligence/preferences").status_code==403
    assert world["e"].get("/intelligence/graph").status_code==403
    assert world["c"].post("/intelligence/strategy",json={"extra_budget":1}).status_code==403
    c=world["c"]
    assert c.put("/intelligence/preferences",json={"personality_type":"type A"}).status_code==400
    assert c.put("/intelligence/preferences",json={"growth":"expert","weekly_hours":5}).status_code==200
    assert world["o"].get("/intelligence/preferences").json()["preferences"]=={}


def test_horizon_queue_owner_idempotency_and_ledger(world):
    c=world["c"]
    body={"entity_id":world["resume"],"changes":{"response_days":1},"idempotency_key":"test-horizon-idempotency"}
    one=c.post("/intelligence/horizon",json=body);assert one.status_code==200,one.text
    two=c.post("/intelligence/horizon",json=body);assert two.json()["job_id"]==one.json()["job_id"]
    jid=one.json()["job_id"]
    assert world["o"].get("/intelligence/jobs/"+jid).status_code==404
    assert world["o"].post("/intelligence/horizon",json=body).status_code==404
    result=finish(c,jid)
    assert result["trials"]==1024
    assert c.get("/intelligence/decisions").json()["items"]
    assert world["o"].post("/intelligence/decisions/"+result["decision_id"]+"/dispute",json={"reason":"Проверить основу результата"}).status_code==404
    assert c.post("/intelligence/decisions/"+result["decision_id"]+"/dispute",json={"reason":"Проверить основу результата"}).status_code==200


def test_graph_controls_and_career_route(world):
    c=world["c"];g=c.get("/intelligence/graph");assert g.status_code==200,g.text
    evidence=g.json()["evidence"][0]["id"]
    assert world["o"].put("/intelligence/evidence/"+evidence,json={"hidden":True}).status_code==404
    assert c.put("/intelligence/evidence/"+evidence,json={"hidden":True}).status_code==200
    assert not any(n["id"]=="e:"+evidence for n in c.get("/intelligence/graph").json()["nodes"])
    r=c.post("/intelligence/career-route",json={});assert r.status_code==200,r.text
    result=finish(c,r.json()["job_id"])
    assert len(result["milestones"])==3 and result["psychological_type_inferred"] is False


def test_arena_isolation_run_hidden_tests_and_adaptive_cas(world):
    c=world["c"]
    r=c.post("/intelligence/arena",json={"kind":"sql"});assert r.status_code==200,r.text
    aid=r.json()["id"]
    assert "hidden_tests"not in r.text and "reference_solution"not in r.text
    assert world["o"].post("/intelligence/arena/"+aid+"/run",json={"code":"SELECT 0"}).status_code==404
    result=c.post("/intelligence/arena/"+aid+"/run",json={"code":"SELECT name,0 FROM accounts ORDER BY name"});assert result.status_code==200,result.text
    assert result.json()["total"]==2 and result.json()["passed"]==1
    adaptive=c.post("/intelligence/arena",json={"kind":"adaptive"}).json();q=adaptive["contract"]["question"]
    payload={"question_id":q["id"],"answer":0,"revision":0}
    assert c.post("/intelligence/arena/"+adaptive["id"]+"/answer",json=payload).status_code==200
    assert c.post("/intelligence/arena/"+adaptive["id"]+"/answer",json=payload).status_code==409
    assert "bank"not in c.get("/intelligence/arena").text


def test_owner_export_has_new_data_without_hidden_tests(world):
    r=world["c"].get("/account/export");assert r.status_code==200,r.text
    p=r.json()["intelligence"]
    assert p["decisions"] and p["preferences"]
    assert "hidden_tests"not in r.text and "reference_solution"not in r.text
    assert world["o"].get("/account/export").json()["intelligence"]["decisions"]==[]


def test_outcome_owner_and_actual_error_metrics(world):
    c=world["c"]
    decision=next(x for x in c.get("/intelligence/decisions").json()["items"] if x["kind"]=="horizon")
    assert world["o"].post("/intelligence/outcomes",json={"decision_id":decision["id"],"actual_days":20}).status_code==404
    assert c.post("/intelligence/outcomes",json={"decision_id":decision["id"],"actual_days":-1}).status_code==400
    assert c.post("/intelligence/outcomes",json={"decision_id":decision["id"],"actual_days":20}).status_code==200
    metrics=c.get("/intelligence/quality").json()["forecast_accuracy"]
    assert metrics["outcomes"]==1
    if decision["result"]["scenario"]["median_days"] is not None:
        assert metrics["mae_days"]>=0
        assert metrics["rmse_days"]>=metrics["mae_days"]-1e-9


def test_queue_lease_recovery_and_expired_final_attempt(world):
    from psycopg.types.json import Jsonb
    import uuid
    c,db=world["c"],world["db"]
    jid="RQ"+uuid.uuid4().hex;dead="DQ"+uuid.uuid4().hex
    input={"operation":"graph","skills":["Python"],"roles":[],"evidence":[]}
    db.execute("INSERT INTO intelligence.jobs(id,user_id,kind,input,status,worker_id,lease_until,attempts,idempotency_key) VALUES(%s,%s,'graph',%s,'running','old-worker',now()-interval '1 minute',1,%s)",(jid,world["cu"]["id"],Jsonb(input),jid))
    result=finish(c,jid)
    assert result["version"]=="proof-graph-3.0.0"
    db.execute("INSERT INTO intelligence.jobs(id,user_id,kind,input,status,worker_id,lease_until,attempts,idempotency_key) VALUES(%s,%s,'graph',%s,'running','dead-worker',now()-interval '1 minute',3,%s)",(dead,world["cu"]["id"],Jsonb(input),dead))
    for _ in range(30):
        state=c.get("/intelligence/jobs/"+dead).json()["status"]
        if state=="failed":break
        time.sleep(.1)
    assert state=="failed"


def test_public_graph_suppresses_private_resume_and_preferences(world):
    c,e,db=world["c"],world["e"],world["db"]
    assert e.get("/intelligence/graph/candidate/"+world["cu"]["subject_id"]).status_code==404
    db.execute("UPDATE candidates SET consent_publication=true WHERE id=%s",(world["cu"]["subject_id"],))
    db.execute("UPDATE resume_profiles SET visibility='employer_searchable',status='published' WHERE id=%s",(world["resume"],))
    assert e.get('/intelligence/graph/candidate/'+world['cu']['subject_id']).status_code==404
    db.execute("INSERT INTO qualification_certificates(id,candidate_id,resume_id,specialization,grade,skills,assessment_version,attempt) SELECT %s,candidate_id,id,specialization,declared_grade,'[]','graph-boundary-fixture','{\"score\":80}' FROM resume_profiles WHERE id=%s", ('CERT'+uuid.uuid4().hex,world['resume']))
    published=e.get("/intelligence/graph/candidate/"+world["cu"]["subject_id"]);assert published.status_code==200,published.text
    assert 'working_preferences'not in published.text and 'opportunities'not in published.text
    assert not any(x["id"]=='resume:'+world["resume"] for x in published.json()["evidence"])
    assert '@'not in published.text
