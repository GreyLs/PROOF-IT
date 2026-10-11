"""Public evidence boundaries and independent numerical checks. No LLM calls."""
import asyncio,copy,hashlib,json
import httpx,numpy as np,pytest
from intelligence import github_evidence as gh,role_matrix as rm,experiments as ex,market_models as mm,response_patterns as rp,graph_neural as nn,professional as cat,certification

@pytest.mark.parametrize('url',['http://github.com/o/r/pull/1','https://github.com.attacker.test/o/r/pull/1','https://github.com:443/o/r/pull/1','https://user@github.com/o/r/pull/1','https://github.com/o/r/pull/1?x=1','https://github.com/o/r/pull/1#diff','https://github.com/../r/pull/1','https://github.com/o/%2fr/pull/1','https://127.0.0.1/o/r/pull/1','file:///etc/passwd','https://github.com/o/r/pull/0'])
def test_github_fixed_origin(url):
    with pytest.raises(ValueError):gh.pr_reference(url)

def client(move=False,private=False):
    calls=[]
    def respond(request):
        path=request.url.path;calls.append(path)
        if path.endswith('/pulls/1/files'):value=[{'filename':'model.py','sha':'c'*40,'status':'modified','patch':'@@ -1 +1 @@\n-return old\n+return checked','additions':1,'deletions':1}]
        elif path.endswith('/pulls/1/commits'):value=[{'sha':'b'*40,'author':{'id':7},'commit':{'message':'reviewed change'}}]
        elif path.endswith('/comments') or path.endswith('/reviews'):value=[{'id':9,'body':'contact name@example.test','created_at':'2026-10-10T00:00:00Z','html_url':'https://github.com/o/r/pull/1#issuecomment-9'}]
        elif path.endswith('/pulls/1'):value={'head':{'sha':('d' if move and calls.count(path)>1 else 'a')*40},'user':{'id':7,'login':'owner'},'changed_files':1,'commits':1,'title':'change'}
        else:value={'private':private,'visibility':'private' if private else 'public'}
        return httpx.Response(200,json=value,headers={'x-ratelimit-remaining':'50'})
    return gh.PublicClient(httpx.MockTransport(respond)),calls

def test_pinned_public_pr_digest_and_questions():
    c,calls=client();a=asyncio.run(gh.fetch_pr({'url':'https://github.com/o/r/pull/1','specialization':'backend_python'},c))
    b=asyncio.run(gh.fetch_pr({'url':'https://github.com/o/r/pull/1','specialization':'backend_python'},c))
    assert a['digest']==b['digest'] and len(a['questions'])==4 and a['coverage']['files_complete']
    assert all(q['head_sha']=='a'*40 and q['artifact_digest']==a['digest'] and q['file']=='model.py' for q in a['questions'])
    assert len(a['commits'])==1 and len(a['discussion'])==3 and '@' not in json.dumps(a['discussion'])
    assert not a['code_executed'] and not a['personal_contact_fields_collected']

@pytest.mark.parametrize('move,private',[(True,False),(False,True)])
def test_private_or_moving_snapshot_rejected(move,private):
    c,calls=client(move,private)
    with pytest.raises(ValueError):asyncio.run(gh.fetch_pr({'url':'https://github.com/o/r/pull/1','specialization':'backend_python'},c))
    if private:assert len(calls)==1

@pytest.mark.parametrize('status',[302,403,429,500])
def test_rate_limit_and_redirect_closed(status):
    c=gh.PublicClient(httpx.MockTransport(lambda r:httpx.Response(status,headers={'location':'http://127.0.0.1'})))
    with pytest.raises(ValueError):asyncio.run(c.get('/repos/o/r'))

def test_gist_nonce_bound_and_redacted():
    nonce='f'*64;gist={'public':True,'files':{'proofit-claim.txt':{'content':nonce}},'owner':{'id':7,'login':'owner'}}
    c=gh.PublicClient(httpx.MockTransport(lambda r:httpx.Response(200,json=gist)))
    proof=asyncio.run(gh.verify_gist({'gist_id':'a'*20},c));assert proof['nonce_hash']==hashlib.sha256(nonce.encode()).hexdigest() and nonce not in json.dumps(proof)
    gist['files']['proofit-claim.txt']['truncated']=True
    with pytest.raises(ValueError):asyncio.run(gh.verify_gist({'gist_id':'a'*20},c))

def test_repository_graphql_discussions_public_only(monkeypatch):
    monkeypatch.setattr(gh,'secret',lambda *a:'unit-test-not-a-real-token')
    def respond(request):
        if request.url.path=='/graphql':
            assert request.method=='POST' and json.loads(request.content)['variables']=={'owner':'owner','name':'repo'}
            return httpx.Response(200,json={'data':{'repository':{'isPrivate':False,'discussions':{'nodes':[{'number':1,'title':'Engineering decision','url':'https://github.com/owner/repo/discussions/1','comments':{'nodes':[{'bodyText':'mail contact@example.test','createdAt':'2026-10-10'}],'pageInfo':{'hasNextPage':False}}}],'pageInfo':{'hasNextPage':False}}}}})
        return httpx.Response(200,json=[] if request.url.path.endswith(('/commits','/pulls')) else {'private':False,'visibility':'public'})
    result=asyncio.run(gh.fetch_repository({'repository':'owner/repo'},gh.PublicClient(httpx.MockTransport(respond))))
    assert result['repository_discussions']['status']=='connected' and result['repository_discussions']['complete']
    assert '@' not in json.dumps(result['repository_discussions']) and not result['code_executed']

def test_external_body_limit():
    c=gh.PublicClient(httpx.MockTransport(lambda r:httpx.Response(200,content=b'x'*1500001)))
    with pytest.raises(ValueError):asyncio.run(c.get('/repos/owner/repo'))

@pytest.mark.parametrize('spec',['backend_python','ml_data_science','data_engineering','mlops','frontend_development'])
def test_role_specific_practical_evidence(spec):
    rubric=rm.matrix({'specialization':spec});scores={x['id']:3 for x in rubric['criteria']}
    base={'specialization':spec,'grade':'senior','scores':scores,'identity_bound':True,'artifact_intact':True,'independent_review':True,'knowledge_scope_verified':True}
    assert rm.attestation(base)['role_confirmation_eligible']
    for condition in ('identity_bound','artifact_intact','independent_review','knowledge_scope_verified'):
        assert not rm.attestation({**base,condition:False})['role_confirmation_eligible']
    assert not rubric['knowledge_test_is_professional_certification']
    scores[next(iter(scores))]=2;assert not rm.attestation(base)['role_confirmation_eligible']

def test_cross_role_rubric_and_leadership_not_auto_certified():
    with pytest.raises(ValueError):rm.attestation({'specialization':'data_engineering','grade':'senior','scores':{'testing':3,'design':3,'correctness':3,'delivery':3}})
    r=rm.matrix({'specialization':'lead_engineering'});p={'specialization':'lead_engineering','grade':'senior','scores':{c['id']:4 for c in r['criteria']},'identity_bound':True,'artifact_intact':True,'independent_review':True,'knowledge_scope_verified':True}
    assert not rm.attestation(p)['role_confirmation_eligible']

@pytest.mark.parametrize('seed',range(12))
def test_forms_preserve_keys_and_answer_oracle(seed):
    a=cat.create({'seed':seed,'specialization':'backend_python','form_variant':'A'});b=cat.create({'seed':seed,'specialization':'backend_python','form_variant':'B'})
    for x,y in zip(a['bank'],b['bank']):
        assert x['id']==y['id'] and x['prompt']==y['prompt'] and sorted(x['options'])==sorted(y['options'])
        assert x['options'][x['correct']]==y['options'][y['correct']]
    assert a['parallel_form']['anchor_families']==b['parallel_form']['anchor_families']
    assert not b['parallel_form']['certificate_activation']

def test_randomization_stable_balanced_and_blocked():
    rows=[ex.assign({'identity':str(i),'scope':'python:middle','version':'v1'}) for i in range(10000)]
    assert .48<sum(x['variant']=='A' for x in rows)/len(rows)<.52
    assert rows[7]==ex.assign({'identity':'7','scope':'python:middle','version':'v1'})
    assert rows[7]['assignment_hash']!=ex.assign({'identity':'7','scope':'sql:middle','version':'v1'})['assignment_hash']

def test_tost_rejects_non_equivalence_and_small_anchors():
    a=np.linspace(-1,1,400);anchors=np.column_stack([a,a+.01]).tolist()
    r=ex.equivalence({'a':a.tolist(),'b':(a+.01).tolist(),'paired_anchors':anchors,'planned_looks':10})
    assert r['equivalent'] and r['statistical_gate_passed'] and not r['production_activation_allowed'] and r['confidence_interval'][0]>-.2
    assert not ex.equivalence({'a':a.tolist(),'b':(a+.4).tolist(),'paired_anchors':anchors})['equivalent']
    assert not ex.equivalence({'a':a.tolist(),'b':a.tolist(),'paired_anchors':[[0,0],[0,0]]})['statistical_gate_passed']
    assert not ex.equivalence({'a':[-4,4],'b':[-4,4]})['equivalent']

def test_signals_require_review_and_never_sanction():
    answers=[{'elapsed_ms':100,'correct':True,'expected_correct':.1} for _ in range(16)]
    r=rp.analyze({'answers':answers});assert len(r['signals'])==3 and r['review_required']
    assert not r['automatic_accusation'] and not r['automatic_sanction'] and not r['previous_certificates_revoked']
    assert not rp.analyze({'answers':[{**a,'elapsed_ms':7000+i*137,'expected_correct':.9} for i,a in enumerate(answers)]})['review_required']

@pytest.mark.parametrize('seed',range(10))
def test_frechet_bounds_match_independent_coupling(seed):
    rng=np.random.default_rng(seed)
    for _ in range(20):
        a,b,c,d=map(int,rng.integers(0,100,4));r=mm.bilateral({'candidate':{'accepted':a,'declined':b},'employer':{'accepted':c,'declined':d}})
        p,q=r['candidate_acceptance']['mean'],r['employer_acceptance']['mean'];lo,hi=r['joint_mean_bounds']
        assert 0<=lo<=p*q<=hi<=1 and r['joint_point_estimate'] is None and not r['independence_assumed']

def test_unknown_employer_not_bad_employer_and_censoring():
    assert mm.reliability({})['conservative_observed_index'] is None
    a=mm.posterior({'accepted':10,'declined':5});b=mm.posterior({'accepted':10,'declined':5,'censored':1000})
    assert a['mean']==b['mean'] and a['interval_90']==b['interval_90']

def graph():return {'nodes':[{'id':'e','kind':'evidence','strength':.8},{'id':'s','kind':'skill','strength':.8},{'id':'r','kind':'role'}],'edges':[{'from':'e','to':'s','relation':'supports','weight':.8},{'from':'s','to':'r','relation':'transfers_to','weight':.9}]}

@pytest.mark.parametrize('name',['w1','b1','w2','b2','wo','bo'])
def test_gnn_backprop_against_finite_difference(name):
    x,relations=nn.tensors(graph());w=nn.initialize();target=np.array([.8,.7,.6]);_,grad=nn.gradients(x,relations,w,target)
    pos=tuple(0 for _ in w[name].shape);original=w[name][pos];eps=1e-5
    def loss():
        p,_=nn.forward(x,relations,w);return -np.mean(target*np.log(p)+(1-target)*np.log1p(-p))
    w[name][pos]=original+eps;a=loss();w[name][pos]=original-eps;b=loss();w[name][pos]=original
    assert abs(grad[name][pos]-(a-b)/(2*eps))<1e-8

def test_gnn_permutation_identity_independence_and_integrity():
    a=nn.infer(graph());g=graph();g['nodes'].reverse();b=nn.infer(g)
    assert a['status']=='trained' and a['parameter_count']==1105
    assert {x['id']:x['routing_score'] for x in a['nodes']}==pytest.approx({x['id']:x['routing_score'] for x in b['nodes']},abs=1e-12)
    g=graph();g['nodes'][0]['display_name']='private';assert nn.infer(g)==a
    assert not a['automatic_grade_promotion'] and not a['automatic_skill_verification']
    g['edges'][0]['to']='absent'
    with pytest.raises(ValueError):nn.infer(g)
