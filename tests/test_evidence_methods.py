"""Independent invariants and executable oracles; no generative model in tests."""
import ast,copy,itertools,json,math,random,re,sqlite3,time
import pytest
from intelligence import certification,professional,twins,integrity,passport,providers
from intelligence.item_bank import FAMILIES,render
from intelligence.engine import proof_graph

@pytest.mark.parametrize('family',list(itertools.chain.from_iterable(FAMILIES.values())))
@pytest.mark.parametrize('tier',[0,1,2])
def test_parameterized_family_contract(family,tier):
    variants=[render(family,tier,seed) for seed in range(30)]
    assert len({x['prompt'] for x in variants})>10
    assert len({x['answer_value'] for x in variants})>1
    for q in variants:
        assert len(set(q['options']))==4
        assert q['options'][q['correct']]==str(q['answer_value'])

@pytest.mark.parametrize('seed',range(40))
def test_python_items_with_independent_execution(seed):
    for family in FAMILIES['python']:
        q=render(family,seed%3,seed);p=q['prompt']
        if family=='py_slice':
            values=ast.literal_eval(re.search(r'values=(\[[^]]+\])',p)[1]);stop=int(re.search(r'values\[1:(\d+):2\]',p)[1]);expected=sum(values[1:stop:2])
        elif family=='py_alias':
            a,b,n=map(int,re.findall(r'(?:a=\[|range\()(\d+)',p));first=[a];alias=first;other=first.copy();alias.extend(range(b));other.extend(range(n));expected=len(first)+len(alias)+len(other)
        elif family=='py_defaults':
            a,b=map(int,re.findall(r'(\d+) вызовов',p));bag=[]
            def add(x,items=bag):items.append(x);return len(items)
            for _ in range(a):add(1)
            for _ in range(b):add(1,[])
            expected=add(1)
        elif family=='py_filter':
            values=ast.literal_eval(re.search(r'values=(\[[^]]+\])',p)[1]);expected=0
            for x in values:
                if x>0 and not x%2:expected+=x*x
        elif family=='py_counts':expected=len(set(ast.literal_eval(re.search(r'keys=(\[[^]]+\])',p)[1])))
        else:
            a,end,step=map(int,re.search(r'range\((\d+), (\d+), (\d+)\)',p).groups());expected=0
            while a<end:expected+=a;a+=step
        assert int(q['options'][q['correct']])==expected

@pytest.mark.parametrize('seed',range(40))
def test_sql_items_against_actual_sqlite(seed):
    db=sqlite3.connect(':memory:')
    for family in FAMILIES['sql']:
        q=render(family,seed%3,seed);p=q['prompt'];db.execute('DROP TABLE IF EXISTS t');db.execute('CREATE TABLE t(x INTEGER,key TEXT)')
        array=re.search(r'(?:содержит |scores=|x=)(\[[^]]+\])',p)
        if array:
            values=ast.literal_eval(array[1]);db.executemany('INSERT INTO t(x) VALUES(?)',[(x,) for x in values])
        if family=='sql_where':expected=db.execute('SELECT coalesce(SUM(x),0) FROM t WHERE x>?',(int(re.search(r'x>(\d+)',p)[1]),)).fetchone()[0]
        elif family=='sql_null':
            n,nulls=map(int,re.findall(r'(\d+) строк',p));db.executemany('INSERT INTO t(x) VALUES(?)',[(None,) if i<nulls else (1,) for i in range(n)]);expected=db.execute('SELECT COUNT(x) FROM t').fetchone()[0]
        elif family=='sql_having':
            a,b,n,threshold=map(int,re.findall(r'(?:принадлежат |, |>)(\d+)',p));db.executemany('INSERT INTO t(key) VALUES(?)',[(k,) for k,size in zip('ABC',(a,b,n)) for _ in range(size)]);expected=len(db.execute('SELECT key FROM t GROUP BY key HAVING COUNT(*)>?',(threshold,)).fetchall())
        elif family=='sql_rank':expected=db.execute('SELECT MAX(r) FROM (SELECT DENSE_RANK() OVER(ORDER BY x DESC) r FROM t)').fetchone()[0]
        elif family=='sql_distinct':expected=db.execute('SELECT COUNT(DISTINCT x) FROM t').fetchone()[0]
        else:
            a,b,n=map(int,re.findall(r'(?:SQL: |по |ещё )(\d+)',p));db.execute('CREATE TABLE clients(id INTEGER)');db.execute('CREATE TABLE orders(client_id INTEGER)');db.executemany('INSERT INTO clients VALUES(?)',[(i,) for i in range(a+n)]);db.executemany('INSERT INTO orders VALUES(?)',[(i,) for i in range(a) for _ in range(b)]);expected=db.execute('SELECT COUNT(*) FROM clients LEFT JOIN orders ON orders.client_id=clients.id').fetchone()[0];db.execute('DROP TABLE clients');db.execute('DROP TABLE orders')
        assert int(q['options'][q['correct']])==expected
    db.close()

def candidate(id='c1',**changes):return {'id':id,'salary':180000,'specialization':'backend_python','grade':'middle','grade_verified':True,'support':{'python':.85,'sql':.8},**changes}
def vacancy(id='v1',**changes):return {'id':id,'label':'Backend engineer','salary':250000,'specialization':'backend_python','grade':'middle','skills':['Python','SQL'],**changes}

@pytest.mark.parametrize('change',[{'salary':300000},{'grade_verified':False},{'grade':'junior'},{'specialization':'frontend'},{'support':{'python':.9}}])
def test_hard_constraints_cannot_be_traded_for_high_score(change):
    r=twins.compatibility({'candidate':candidate(**change),'vacancy':vacancy()});assert not r['eligible'] and not r['autonomous_hiring_decision']

@pytest.mark.parametrize('seed',range(20))
def test_allocation_equals_exhaustive_oracle(seed):
    rng=random.Random(seed);cs=[candidate(f'c{i}',support={'python':rng.uniform(.5,.99),'sql':rng.uniform(.5,.99)},salary=rng.choice([100000,200000,300000])) for i in range(4)];vs=[vacancy(f'v{i}',skills=rng.choice([['Python'],['SQL'],['Python','SQL']])) for i in range(3)]
    got=twins.allocation({'candidates':cs,'vacancies':vs});best=0
    for combo in itertools.product(range(-1,4),repeat=3):
        used=[i for i in combo if i>=0]
        if len(used)!=len(set(used)):continue
        rows=[twins.pair(cs[i],v) for i,v in zip(combo,vs) if i>=0]
        if all(x['eligible'] for x in rows):best=max(best,sum(x['utility'] for x in rows))
    assert got['total_utility']==pytest.approx(best,abs=2e-6)
    assert len({x['candidate_id'] for x in got['assignments']})==len(got['assignments'])

def test_missing_preferences_are_unknown_not_disagreement():
    r=twins.pair(candidate(),vacancy(team={'pace':'stable'}));assert r['working_preferences_alignment'] is None and r['eligible']
def test_multiple_resumes_cannot_allocate_one_person_twice():
    r=twins.allocation({'candidates':[candidate('r1',candidate_id='person'),candidate('r2',candidate_id='person')],'vacancies':[vacancy(),vacancy('v2')]})
    assert len(r['assignments'])==1 and r['unfilled_slots']==1
def test_next_proof_counts_single_gap_and_never_promises_hire():
    r=twins.next_proof({'candidate':candidate(support={'python':.9}),'vacancies':[vacancy(),vacancy('v2')]});assert r['tasks'][0]['skill']=='sql' and r['tasks'][0]['single_gap_opportunities']==2
def test_diagnosis_does_not_relax_active_constraints():
    r=twins.diagnosis({'vacancy':vacancy(),'candidates':[candidate(salary=300000)]});assert not r['constraints_satisfiable'] and r['minimal_relaxations'][0]['salary_increase_rub']==50000 and r['constraints_remain_enforced']
def test_transfer_only_uses_verified_skills():
    r=twins.transfer({'candidate':candidate(support={'python':.8,'sql':.2}),'roles':[vacancy()]});assert r['routes'][0]['skills_to_verify']==['sql'] and r['qualification_required_for_target_role']

def graph(evidence):return proof_graph({'as_of':'2026-10-10T00:00:00+00:00','skills':['Python','SQL'],'roles':[vacancy()],'evidence':evidence})
def ev(id='p1',**changes):return {'id':id,'title':'Executed proof','status':'executed','skills':['Python'],'source':'sandbox','weight':.8,**changes}
def strength(r):return next(x['strength'] for x in r['nodes'] if x['id']=='s:python')
def test_graph_duplicate_source_is_capped():assert strength(graph([ev()]))==strength(graph([ev(str(i)) for i in range(100)]))
def test_graph_independent_sources_add_support():assert strength(graph([ev(),ev('q',source='qualification')]))>strength(graph([ev()]))
@pytest.mark.parametrize('change',[{'hidden':True},{'disputed':True},{'valid_until':'2026-10-01T00:00:00Z'},{'status':'declared'}])
def test_graph_visibility_expiry_and_declaration_have_zero_support(change):assert strength(graph([ev(**change)]))==0
def test_graph_age_decays_without_manufacturing_proof():assert strength(graph([ev(issued_at='2026-07-12T00:00:00Z')]))==pytest.approx(.4,abs=.003)

CODE="def solve(data):\n    seen=set(); totals={}\n    for event in data['events']:\n        if event['id'] in seen: continue\n        seen.add(event['id'])\n        key=event['account']; totals[key]=totals.get(key,0)+event['amount']\n    return [{'account':k,'total':totals[k]} for k in sorted(totals)]"
@pytest.mark.parametrize('padding',[0,1,10,20,100])
def test_similarity_contains_renamed_copy_despite_padding(padding):
    changed=CODE.replace('seen','used').replace('totals','balances')+'\n'+'\n'.join(f'def unused{i}(x):\n    return x*x+{i}' for i in range(padding))
    r=integrity.compare({'fingerprint':integrity.fingerprint({'code':changed}),'references':[integrity.fingerprint({'code':CODE})]});assert r['similarity']>=.85 and r['review_recommended'] and not r['automatic_penalty']
def test_template_alone_does_not_accuse_author():
    fp=integrity.fingerprint({'code':CODE,'template':CODE});r=integrity.compare({'fingerprint':fp,'references':[fp]});assert not r['review_recommended']
def test_language_and_version_mismatch_not_compared():
    a=integrity.fingerprint({'code':CODE});b=integrity.fingerprint({'code':CODE,'language':'typescript'});assert integrity.compare({'fingerprint':a,'references':[b]})['similarity']==0
def test_authorship_requires_human_defense_not_guessed_detector():
    r=twins.authorship({'code':CODE,'ai_assisted':True});assert len(r['questions'])==3 and r['ai_assistance_declared'] and not r['automatic_authorship_verdict']

def test_passport_signature_tamper_expiry(monkeypatch,tmp_path):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    path=tmp_path/'key.pem';path.write_bytes(Ed25519PrivateKey.generate().private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()));monkeypatch.setenv('PASSPORT_KEY_FILE',str(path))
    r=passport.issue({'id':'test','claims':{'certificates':[]}});assert passport.verify({'token':r['token']})['signature_valid']
    first,middle,last=r['token'].split('.');assert not passport.verify({'token':first+'.'+middle+'.'+('A' if last[0]!='A' else 'B')+last[1:]})['signature_valid']
    assert 'PRIVATE' not in passport.public({})['public_key']

@pytest.mark.parametrize('grade',['junior','middle','senior'])
def test_qualification_perfect_and_wrong_oracles(grade):
    results=[]
    for correct in (True,False):
        c=certification.prepare({'seed':32,'resume':{'specialization':'backend_python','declared_grade':grade}})['contract']
        while(q:=professional.next_item(c)) is not None:c=certification.step({'contract':c,'question_id':q['id'],'answer':q['correct'] if correct else (q['correct']+1)%4,'elapsed_ms':10000+137*len(c['answers'])})['contract']
        results.append(certification.decision(c))
    assert results[0]['passed'] and not results[1]['passed']
    assert 'Python' in results[0]['certified_skills'] and 'SQL' in results[0]['certified_skills']

def test_dreamjob_valid_schema_and_neutral_absence():
    p={'rating':4.5,'review_count':120,'source_url':'https://dreamjob.ru/employers/1234','updated_at':'2026-10-01T00:00:00Z'}
    r=providers.normalize('dreamjob',p);assert not r['verified_candidate_skill']
    for bad in ({**p,'rating':6},{**p,'review_count':0},{**p,'source_url':'https://dreamjob.ru.attacker.test/123'}):
        with pytest.raises(ValueError):providers.normalize('dreamjob',bad)
