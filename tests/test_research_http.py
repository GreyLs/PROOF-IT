"""Live Rust ownership, matrix and paired-decision integration; disposable fixtures."""
import uuid
from psycopg.types.json import Jsonb
from tests.test_resume_qualification import world,create_resume
from tests.test_evidence_http import accepted_offer
BASE='/intelligence/research-lab'

def test_workspace_and_matrix_are_authenticated_and_role_scoped(world):
    c,e=world['candidate'],world['employer'];r=create_resume(c,1).json()['resume']
    body=c.get(BASE+'/workspace');body.raise_for_status();assert body.json()['resumes'][0]['id']==r['id']
    assert e.get(BASE+'/workspace').json()['resumes']==[]
    matrix=c.get(BASE+'/matrix/data_engineering');matrix.raise_for_status();assert matrix.json()['family']=='data'
    assert not matrix.json()['knowledge_test_is_professional_certification']
    assert e.post(BASE+'/forms/'+r['id'],json={}).status_code==403
    a=c.post(BASE+'/forms/'+r['id'],json={});a.raise_for_status();assert a.json()==c.post(BASE+'/forms/'+r['id'],json={}).json()

def test_market_owner_industry_and_missing_employer_dimensions(world):
    c,e,o,db=world['candidate'],world['employer'],world['other'],world['db'];_,vid=accepted_offer(world)
    r=e.get(BASE+'/market/'+vid);r.raise_for_status();data=r.json();assert data['scope']['industry']=='ИТ' and data['pool']['available_pool']>=1
    assert data['moex']['ranking_effect']==data['moex']['forecast_effect']==0 and data['moex']['status']=='licensing_required'
    assert e.get(BASE+'/market/'+vid).json()['history'][0]['date']
    assert o.get(BASE+'/market/'+vid).status_code==404 and c.get(BASE+'/market/'+vid).status_code==403
    r=c.get(BASE+'/reliability/'+world['eu']['subject_id']);r.raise_for_status();assert r.json()['conservative_observed_index'] is None

def test_paired_stage_intentions_preserve_roles_and_censoring(world):
    c,e,o=world['candidate'],world['employer'],world['other'];_,vid=accepted_offer(world);cid=world['cu']['subject_id']
    assert c.get(BASE+'/bilateral/'+vid).status_code==403 and o.get(BASE+'/bilateral/'+vid).status_code==404
    c.post(BASE+'/bilateral/'+vid+'/decision',json={'stage':'offer','accepts':True}).raise_for_status()
    incomplete=e.get(BASE+'/bilateral/'+vid).json()['offer'];assert incomplete['candidate_acceptance']['observed']==0 and incomplete['candidate_acceptance']['censored_excluded']==1
    e.post(BASE+'/bilateral/'+vid+'/decision',json={'stage':'offer','accepts':True,'candidate_id':cid}).raise_for_status()
    r=e.get(BASE+'/bilateral/'+vid);r.raise_for_status();assert r.json()['offer']['candidate_acceptance']['observed']==1 and r.json()['vacancy']['candidate_acceptance']['observed']==0
    assert r.json()['offer']['joint_point_estimate'] is not None and not r.json()['offer']['independence_assumed']
    assert o.post(BASE+'/bilateral/'+vid+'/decision',json={'stage':'offer','accepts':False,'candidate_id':cid}).status_code==404
    participants=e.get(BASE+'/bilateral/'+vid+'/participants').json()['items'];assert len(participants)==1 and participants[0]['has_offer']
    c.post(BASE+'/bilateral/'+vid+'/decision',json={'stage':'offer','accepts':False,'candidate_id':world['ou']['subject_id']}).raise_for_status()
    row=world['db'].execute('SELECT candidate_accepts,employer_accepts FROM intelligence.bilateral_decisions WHERE vacancy_id=%s',(vid,)).fetchone();assert not row['candidate_accepts'] and row['employer_accepts']

def test_answer_binding_revision_foreign_owner_and_no_auto_grade(world):
    c,e,o,db=world['candidate'],world['employer'],world['other'],world['db'];r=create_resume(c,1).json()['resume'];id='GHT'+uuid.uuid4().hex
    questions=[{'id':'question1','criterion':'correctness','prompt':'Explain concrete change'}]
    db.execute("INSERT INTO intelligence.github_defenses(id,user_id,resume_id,specialization,target_grade,repository,pr_number,head_sha,artifact_digest,snapshot,questions) VALUES(%s,%s,%s,'backend_python','middle','owner/repo',1,%s,%s,%s,%s)",(id,world['cu']['id'],r['id'],'a'*40,'b'*64,Jsonb({'url':'https://github.com/owner/repo/pull/1','coverage':{},'author_login':'owner'}),Jsonb(questions)))
    assert e.put(BASE+'/github/pr/'+id+'/answers',json={'revision':0,'answers':{'question1':'x'*50}}).status_code==403
    assert c.put(BASE+'/github/pr/'+id+'/answers',json={'revision':0,'answers':{'other':'x'*50}}).status_code==400
    c.put(BASE+'/github/pr/'+id+'/answers',json={'revision':0,'answers':{'question1':'x'*50}}).raise_for_status()
    assert c.put(BASE+'/github/pr/'+id+'/answers',json={'revision':0,'answers':{'question1':'x'*50}}).status_code==409
    assert not e.get(BASE+'/workspace').json()['items']
    assert o.post(BASE+'/github/pr/'+id+'/review',json={'revision':1,'scores':{},'skills':['Python'],'reason':'x'*50}).status_code==403
    assert db.execute('SELECT count(*) n FROM qualification_certificates WHERE resume_id=%s',(r['id'],)).fetchone()['n']==0

def test_cat_knowledge_is_not_full_role_hard_gate(world):
    from tests.test_resume_qualification import complete
    c,e,db=world['candidate'],world['employer'],world['db'];r=create_resume(c,1).json()['resume'];state,_=complete(c,db,r['id'])
    assert state['passed'] and state['certification_scope']=='role-knowledge' and not state['professional_role_certified']
    assert db.execute('SELECT scope FROM qualification_certificates WHERE resume_id=%s',(r['id'],)).fetchone()['scope']=='role-knowledge'
    out=c.get('/intelligence/evidence-lab/workspace');out.raise_for_status()
    assert not out.json()['items'][0]['resume']['grade_verified']

def test_live_artifact_review_issues_scoped_certificate_only_after_independent_review(world):
    import os,json
    from pathlib import Path
    import pytest
    if os.getenv('PROOFIT_LIVE_GITHUB_VALIDATION')!='1':pytest.skip('explicit live read-only GitHub validation required')
    from tests.test_resume_qualification import complete
    c,e,db=world['candidate'],world['employer'],world['db'];r=create_resume(c,1).json()['resume'];complete(c,db,r['id'])
    source=json.loads(Path('validation/reports/current/github-live.json').read_text(encoding='utf-8'))
    imported=c.post(BASE+'/github/pr',json={'url':source['pr_url'],'resume_id':r['id'],'consent_public_evidence':True});imported.raise_for_status();id=imported.json()['id']
    snapshot=db.execute('SELECT snapshot,questions FROM intelligence.github_defenses WHERE id=%s',(id,)).fetchone();github_id=snapshot['snapshot']['author_github_id']
    # Deliberately provision control-bound identity only in a disposable synthetic
    # fixture. Nonce/control verification is separately covered by transport tests.
    db.execute("INSERT INTO intelligence.github_accounts(user_id,github_id,login,proof_url) VALUES(%s,%s,'fixture-controlled','https://gist.github.com/fixture')",(world['cu']['id'],github_id))
    c.put(BASE+'/github/pr/'+id+'/answers',json={'revision':0,'answers':{q['id']:'Контрольный ответ одноразового синтетического сценария. '+q['file'] for q in snapshot['questions']}}).raise_for_status()
    payload={'revision':1,'scores':{q['criterion']:2 for q in snapshot['questions']},'skills':['Python'],'reason':'Контрольный независимый review синтетической fixture: проверены binding, SHA и критерии; не аттестация реального автора.'}
    assert e.post(BASE+'/github/pr/'+id+'/review',json=payload).status_code==403
    db.execute('INSERT INTO intelligence.assessment_experts(user_id,approved) VALUES(%s,true)',(world['eu']['id'],))
    result=e.post(BASE+'/github/pr/'+id+'/review',json=payload);result.raise_for_status();assert result.json()['role_confirmation_eligible']
    certificate=db.execute("SELECT scope,skills FROM qualification_certificates WHERE resume_id=%s AND scope='role-reviewed'",(r['id'],)).fetchone();assert certificate['skills']==['Python']
    assert e.post(BASE+'/github/pr/'+id+'/review',json=payload).status_code==409
    exported=c.get('/account/export');exported.raise_for_status();assert exported.json()['research_lab']['contribution_defenses'][0]['artifact_digest']==imported.json()['artifact_digest']
