"""Assessment trust boundaries and independently specified business examples."""
import time
import json
import jwt
import numpy as np
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from intelligence import professional as cat, integrity, needs, oidc


def attempt(seed=41,mode="express",**kwargs):
    return cat.create({"seed":seed,"mode":mode,"specialization":"backend_python",**kwargs})


def complete(c,correct=True):
    while (q:=cat.next_item(c)) is not None:
        c=cat.step({"contract":c,"question_id":q["id"],"answer":q["correct"] if correct else (q["correct"]+1)%4,"elapsed_ms":5000})["contract"]
    return c


def test_keys_private_and_grade_unchanged():
    c=attempt();p=cat.public(c)
    assert set(p["question"])=={"id","prompt","options","topic","time_limit_seconds"}
    assert cat.result(complete(c))["grade_changed"] is False


def test_full_attempt_does_not_repeat_a_family():
    c=complete(attempt(mode="full"));a=c["answers"]
    assert 20<=len(a)<=32 and len({v["family"] for v in a})==len(a)


def test_unique_variants_and_reproducibility():
    a=cat.item("join",1,11);b=cat.item("join",1,12)
    assert a==cat.item("join",1,11) and a["prompt"]!=b["prompt"]
    assert len(set(a["options"]))==4


def test_timeout_and_replay_use_server_time():
    c=attempt();q=cat.next_item(c)
    r=cat.step({"contract":c,"question_id":q["id"],"answer":q["correct"],"elapsed_ms":q["time_limit_seconds"]*1000+1})
    assert not r["observation"]["correct"] and r["observation"]["timed_out"]
    with pytest.raises(ValueError):cat.step({"contract":r["contract"],"question_id":q["id"],"answer":q["correct"],"elapsed_ms":1000})


def test_pilot_does_not_change_posterior_and_only_one_is_served():
    d={"id":"pilot-x","prompt":"Как защитить счёт от двойного списания при повторной доставке события?","options":["Уникальный ключ и транзакция","Удалить ключ","Выключить журнал","Повторять всегда"],"correct":0,"rationale":"Ключ обеспечивает уникальность операции."}
    c=attempt(mode="full",pilots=[d,{**d,"id":"pilot-y"}])
    for _ in range(8):
        q=cat.next_item(c);c=cat.step({"contract":c,"question_id":q["id"],"answer":q["correct"],"elapsed_ms":6000})["contract"]
    before=cat.estimate(c);q=cat.next_item(c);assert q["pilot"]
    c=cat.step({"contract":c,"question_id":q["id"],"answer":q["correct"],"elapsed_ms":6000})["contract"]
    assert np.allclose(before[3],cat.estimate(c)[3])
    assert not cat.next_item(c).get("pilot",False)


def test_quarantine_removes_all_tiers_and_respects_minimum_bank():
    c=attempt(quarantined=["join"])
    assert all(q["family"]!="join" for q in c["bank"])
    with pytest.raises(ValueError):attempt(mode="full",quarantined=list(cat.FAMILIES[15:]))


def test_calibration_gate_and_parameter_fit():
    with pytest.raises(ValueError):cat.calibrate({"bins":[{"theta":0,"total":100,"correct":60}]})
    bins=[{"theta":t,"total":40,"correct":round(40*(.25+.75/(1+np.exp(-1.4*(t-.3)))))} for t in (-2,-1,0,1,2)]
    r=cat.calibrate({"bins":bins})
    assert r["responses"]==200 and r["activation_requires_expert"] and .4<=r["a"]<=3.5


def test_normalized_probabilities_and_no_sensitive_output():
    r=cat.result(complete(attempt()))
    assert abs(sum(r["grade_probabilities"].values())-1)<.0001
    assert not any(k in r for k in ("personality","gender","age","health"))


@pytest.mark.parametrize("text,low,high",[("180–250 тыс руб",180000,250000),("180000–250000 RUB",180000,250000),("180 000 — 250 000 ₽",180000,250000),("от 180 до 250 тыс. руб",180000,250000)])
def test_salary_formats(text,low,high):
    r=needs.parse({"text":"Python / Backend middle удалённо, "+text})
    assert (r["salary_from"],r["salary_to"])==(low,high)
    assert not r["created_vacancy"]


def test_skill_aliases_optional_and_ambiguity():
    r=needs.parse({"text":"Middle Python / Backend, PostgreSQL; желательно Docker, 200 тыс ₽, удалённо"})
    assert "Docker" in r["optional_skills"] and "Python" in r["required_skills"]
    r=needs.parse({"text":"Нужен специалист по технологиям"})
    assert r["specialization"] is None and "specialization" in r["needs_confirmation"]


def test_trusted_role_labels_survive_pii_redaction():
    for role in needs.taxonomy():
        r=needs.parse({"text":"Нужен "+role['label']+"; Middle; "+', '.join(role['skills'][:3])})
        assert r['specialization']==role['id']
    assert 'ivan@example.org' not in needs.private_text('Иван Петров, ivan@example.org; Python / Backend')


REFERENCE="def solve(data):\n    seen=set(); totals={}\n    for event in data['events']:\n        if event['id'] in seen: continue\n        seen.add(event['id'])\n        key=event['account']; totals[key]=totals.get(key,0)+event['amount']\n    return [{'account':k,'total':totals[k]} for k in sorted(totals)]"


def test_similarity_survives_rename_without_penalty():
    a=integrity.fingerprint({"code":REFERENCE})
    b=integrity.fingerprint({"code":REFERENCE.replace('seen','used').replace('totals','balances').replace('data','payload')})
    r=integrity.compare({"fingerprint":a,"references":[b]})
    assert r["similarity"]>.92 and not r["automatic_penalty"]
    assert 'events'not in str(a) and 'account'not in str(a)


@pytest.fixture
def signing():
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    jwk=json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid="test-key",use="sig",alg="RS256")
    claims={"iss":"https://issuer.example","sub":"professional-user","aud":"proofit","iat":int(time.time()),"exp":int(time.time())+120,"nonce":"nonce"}
    return key,{"keys":[jwk]},claims


def test_oidc_valid_signature_and_claims(signing):
    key,jwks,c=signing;t=jwt.encode(c,key,algorithm="RS256",headers={"kid":"test-key"})
    assert oidc.verify(t,jwks,c["iss"],"proofit","nonce")["subject"]==c["sub"]


@pytest.mark.parametrize("field,value",[("iss","https://other.example"),("aud","other-client"),("nonce","other-nonce"),("exp",0),("azp","other-client")])
def test_oidc_rejects_claim_substitution(signing,field,value):
    key,jwks,c=signing;t=jwt.encode({**c,field:value},key,algorithm="RS256",headers={"kid":"test-key"})
    with pytest.raises((ValueError,jwt.PyJWTError)):oidc.verify(t,jwks,c["iss"],"proofit","nonce")


def test_oidc_rejects_unsigned_token(signing):
    _,jwks,c=signing;t=jwt.encode(c,key=None,algorithm="none")
    with pytest.raises(ValueError):oidc.verify(t,jwks,c["iss"],"proofit","nonce")
