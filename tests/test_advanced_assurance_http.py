"""Bounded real ledger races, exact fixture scope and no global restart/failure injection."""
from concurrent.futures import ThreadPoolExecutor
import json
import threading
import time
import pytest
from tests.test_resume_qualification import world
from tests.test_evidence_http import accepted_offer
from tests.test_prospective_http import BASE, freeze

def test_same_pair_eight_way_freeze_is_linearizable(world):
    employer=world['employer']; _,vacancy=accepted_offer(world); candidate=world['cu']['subject_id']
    barrier=threading.Barrier(8)
    def request(_):
        barrier.wait(timeout=15)
        response=freeze(employer,vacancy,candidate)
        return response.status_code, response.json()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(request,range(8)))
    statuses=[status for status,_ in results]
    assert statuses.count(200)==1 and statuses.count(409)==7,statuses
    assert world['db'].execute('SELECT count(*) n FROM intelligence.prospective_predictions WHERE vacancy_id=%s AND candidate_id=%s',(vacancy,candidate)).fetchone()['n']==1
    winner=next(value for status,value in results if status==200)
    assert winner['synthetic'] and winner['model_version']=='bilateral-market-1.0.0'

@pytest.mark.parametrize('round_id',range(6))
def test_prediction_and_first_intention_race_respects_causal_order(world,round_id):
    employer,candidate=world['employer'],world['candidate']; _,vacancy=accepted_offer(world); cid=world['cu']['subject_id']
    barrier=threading.Barrier(2)
    def predict():
        barrier.wait(timeout=15)
        return freeze(employer,vacancy,cid)
    def decide():
        barrier.wait(timeout=15)
        return candidate.post(BASE+'/bilateral/'+vacancy+'/decision',json={'stage':'vacancy','accepts':True})
    with ThreadPoolExecutor(max_workers=2) as pool:
        first,second=pool.submit(predict),pool.submit(decide)
        forecast,decision=first.result(timeout=30),second.result(timeout=30)
    decision.raise_for_status()
    assert forecast.status_code in (200,409),forecast.status_code
    rows=world['db'].execute('SELECT created_at FROM intelligence.prospective_predictions WHERE vacancy_id=%s AND candidate_id=%s',(vacancy,cid)).fetchall()
    if forecast.status_code==200:
        # Server ledger reports only correctly pre-intention predictions. The paired decision path seals a valid outcome.
        employer.post(BASE+'/bilateral/'+vacancy+'/decision',json={'stage':'vacancy','accepts':False,'candidate_id':cid}).raise_for_status()
        exported=employer.get(BASE+'/validation/export?vacancy_id='+vacancy).json()['records']
        assert len(exported)==1 and exported[0]['created_at'] < exported[0]['candidate_decided_at']
        assert exported[0]['created_at'] < exported[0]['employer_decided_at']
    else:
        assert not rows

def test_twelve_concurrent_changes_preserve_first_outcome_and_scope(world):
    employer,candidate,other=world['employer'],world['candidate'],world['other']
    _,vacancy=accepted_offer(world);cid=world['cu']['subject_id']
    prediction=freeze(employer,vacancy,cid);prediction.raise_for_status();identity=prediction.json()['id']
    candidate.post(BASE+'/bilateral/'+vacancy+'/decision',json={'stage':'vacancy','accepts':True}).raise_for_status()
    employer.post(BASE+'/bilateral/'+vacancy+'/decision',json={'stage':'vacancy','accepts':False,'candidate_id':cid}).raise_for_status()
    original=world['db'].execute('SELECT * FROM intelligence.prospective_outcomes WHERE prediction_id=%s',(identity,)).fetchone()
    def change(index):
        client=candidate if index%2 else employer
        body={'stage':'vacancy','accepts':bool(index%3)}
        if client is employer:body['candidate_id']=cid
        return client.post(BASE+'/bilateral/'+vacancy+'/decision',json=body).status_code
    with ThreadPoolExecutor(max_workers=4) as pool:
        statuses=list(pool.map(change,range(12)))
    assert statuses==[200]*12,statuses
    assert world['db'].execute('SELECT * FROM intelligence.prospective_outcomes WHERE prediction_id=%s',(identity,)).fetchone()==original
    assert not other.get(BASE+'/validation/export?vacancy_id='+vacancy).json().get('records')
    assert candidate.get(BASE+'/validation/export').status_code==403

def test_rejected_ledger_update_rolls_back_without_poisoning_next_transaction(world):
    employer=world['employer'];_,vacancy=accepted_offer(world);cid=world['cu']['subject_id']
    prediction=freeze(employer,vacancy,cid);prediction.raise_for_status();identity=prediction.json()['id']
    before=world['db'].execute('SELECT prediction FROM intelligence.prospective_predictions WHERE id=%s',(identity,)).fetchone()
    with pytest.raises(Exception,match='immutable'):
        with world['db'].transaction():
            world['db'].execute("UPDATE intelligence.prospective_predictions SET prediction='{}'::jsonb WHERE id=%s",(identity,))
    assert world['db'].execute('SELECT prediction FROM intelligence.prospective_predictions WHERE id=%s',(identity,)).fetchone()==before
    # A new authorized transaction/stage succeeds after the failed transaction, not just a SELECT.
    assert freeze(employer,vacancy,cid,'offer').status_code==200
