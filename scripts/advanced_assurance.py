"""Independent oracles and metamorphic contracts; controlled, no LLM/network."""
from __future__ import annotations
import ast
import copy
import hashlib
import itertools
import json
import math
import platform
import shutil
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from intelligence import graph_neural as nn, market_models as mm, experiments as ex
from intelligence import twins, role_matrix as rm, response_patterns as rp, prospective as pv

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'validation/reports/current'
PROTOCOL = json.loads((ROOT / 'validation/advanced_protocol.json').read_text(encoding='utf-8'))
SEED = PROTOCOL['seed']

def wilson(successes, total):
    if total == 0:
        return None
    p = successes / total; z = 1.959963984540054
    center = (p + z*z/(2*total))/(1 + z*z/total)
    half = z * math.sqrt(p*(1-p)/total + z*z/(4*total*total))/(1 + z*z/total)
    return [max(0, center-half), min(1, center+half)]

def graph(seed):
    rng = np.random.default_rng(seed)
    nodes = [{'id': f'n{i}', 'kind': ('evidence','skill','role')[i%3], 'strength': float(rng.uniform())} for i in range(12)]
    edges = [{'from': f'n{i}', 'to': f'n{j}', 'relation': ('supports','transfers_to')[(i+j)%2], 'weight': float(rng.uniform())}
             for i in range(12) for j in range(i+1,12) if rng.uniform() < .28]
    return {'nodes': nodes, 'edges': edges}

def graph_contracts(module=nn, cases=20):
    worst = 0.; independent = 0
    for seed in range(cases):
        g = graph(SEED+seed); before = copy.deepcopy(g)
        a = module.infer(g); assert g == before
        scores = {node['id']: node['routing_score'] for node in a['nodes']}
        assert all(math.isfinite(v) and 0 <= v <= 1 for v in scores.values())
        shuffled = copy.deepcopy(g); rng = np.random.default_rng(seed)
        rng.shuffle(shuffled['nodes']); rng.shuffle(shuffled['edges'])
        b = module.infer(shuffled)
        error = max(abs(scores[node['id']] - node['routing_score']) for node in b['nodes'])
        worst = max(worst, error)
        rename = {node['id']: f'opaque-{seed}-{index}' for index,node in enumerate(g['nodes'])}
        renamed = copy.deepcopy(g)
        for node in renamed['nodes']:
            node.update(id=rename[node['id']], name='private name', age=80, gender='ignored', citizenship='ignored')
        for edge in renamed['edges']:
            edge['from'], edge['to'] = rename[edge['from']], rename[edge['to']]
        c = module.infer(renamed)
        assert np.allclose([node['routing_score'] for node in a['nodes']], [node['routing_score'] for node in c['nodes']], atol=1e-12, rtol=0)
        assert not a['automatic_grade_promotion'] and not a['automatic_skill_verification']
        disconnected = copy.deepcopy(g)
        disconnected['nodes'].append({'id':'isolated-extra','kind':'evidence','strength':.99})
        extra = module.infer(disconnected)
        assert np.allclose([node['routing_score'] for node in a['nodes']], [node['routing_score'] for node in extra['nodes'][:-1]], atol=1e-12, rtol=0)
        x, relations = module.tensors(g)
        for relation in relations:
            sums = relation.sum(axis=1)
            assert np.allclose(sums[sums>0], 1, atol=1e-12, rtol=0)
        independent += 1
    assert worst <= PROTOCOL['acceptance']['graph_permutation_max_absolute_error']
    return {'graphs': cases, 'identity_and_sensitive_attribute_invariance': independent,
            'permutation_max_absolute_error': worst, 'input_mutations': 0,
            'disconnected_component_invariance_cases': cases,
            'interpretation': 'structural invariance and numerical bounds, not real hiring accuracy'}

def gradient_audit():
    x, relations = nn.tensors(graph(SEED)); weights = nn.initialize(seed=17)
    target = np.linspace(.1,.9,len(x)); _, analytical = nn.gradients(x, relations, weights, target)
    maximum = 0.; checked = 0; eps = 1e-5
    def loss():
        prediction,_ = nn.forward(x, relations, weights)
        return -math.fsum(float(y)*math.log(float(p))+(1-float(y))*math.log1p(-float(p)) for p,y in zip(prediction,target))/len(target)
    for key in weights:
        for pos in np.ndindex(weights[key].shape):
            previous = weights[key][pos]
            weights[key][pos] = previous + eps; plus = loss()
            weights[key][pos] = previous - eps; minus = loss()
            weights[key][pos] = previous
            maximum = max(maximum, abs(float(analytical[key][pos]) - (plus-minus)/(2*eps)))
            checked += 1
    assert maximum < PROTOCOL['acceptance']['gnn_gradient_max_absolute_error']
    return {'parameters_checked': checked, 'parameter_coverage': checked/sum(value.size for value in weights.values()),
            'finite_difference_epsilon': eps, 'max_absolute_gradient_error': maximum,
            'oracle': 'central difference of independently summed scalar cross-entropy'}

def market(seed):
    rng = np.random.default_rng(SEED+seed)
    cs = [{'id': f'r{i}', 'candidate_id': f'c{i//2}', 'salary': int(rng.choice([80,100,120])),
           'specialization': str(rng.choice(['python','data'])), 'grade': str(rng.choice(['junior','middle','senior'])),
           'grade_verified': bool(rng.integers(2)), 'support': {s:float(rng.choice([.2,.5,.7,1])) for s in ('python','sql')}} for i in range(8)]
    vs = [{'id': f'v{i}', 'salary': int(rng.choice([80,100,140])), 'specialization': str(rng.choice(['python','data'])),
           'grade': str(rng.choice(['junior','middle'])), 'skills': [str(rng.choice(['python','sql']))]} for i in range(3)]
    return {'candidates': cs, 'vacancies': vs}

def oracle_pair(c,v):
    grades = ['junior','middle','senior']
    requirements = set(v['skills'])
    eligible = c['salary'] <= v['salary'] and c['specialization'] == v['specialization'] and c['grade_verified'] and grades.index(c['grade']) >= grades.index(v['grade']) and all(c['support'].get(s,0) >= .5 for s in requirements)
    return eligible, round(math.fsum(c['support'].get(s,0) for s in requirements)/len(requirements),6)

def exhaustive_assignment(payload):
    # No scipy assignment and no production pair() calls: enumerate all physical-person choices.
    people = sorted({candidate['candidate_id'] for candidate in payload['candidates']})
    choices = [None] + people; optimum = 0.; enumerated = 0
    for selected in itertools.product(choices, repeat=len(payload['vacancies'])):
        assigned = [person for person in selected if person is not None]
        if len(assigned) != len(set(assigned)):
            continue
        utility = 0.; valid = True; enumerated += 1
        for person, vacancy in zip(selected,payload['vacancies']):
            if person is None:
                continue
            scores = [score for candidate in payload['candidates'] if candidate['candidate_id']==person
                      for eligible,score in [oracle_pair(candidate,vacancy)] if eligible]
            if not scores:
                valid = False; break
            utility += max(scores)
        if valid:
            optimum = max(optimum,utility)
    return round(optimum,6), enumerated

def assignment_contracts(module=twins, cases=20):
    worst = 0.; enumerated = 0; nonempty = 0
    for seed in range(cases):
        payload = market(seed); before = copy.deepcopy(payload)
        expected, count = exhaustive_assignment(payload); enumerated += count
        actual = module.allocation(payload); assert payload == before
        worst = max(worst, abs(actual['total_utility']-expected))
        people = [row['candidate_id'] for row in actual['assignments']]
        assert len(people) == len(set(people))
        for row in actual['assignments']:
            candidate = next(c for c in payload['candidates'] if c['id']==row['resume_id'])
            vacancy = next(v for v in payload['vacancies'] if v['id']==row['vacancy_id'])
            assert oracle_pair(candidate,vacancy)[0]
        nonempty += bool(actual['assignments'])
        reverse = {'candidates': list(reversed(payload['candidates'])), 'vacancies': list(reversed(payload['vacancies']))}
        assert abs(module.allocation(reverse)['total_utility']-expected) <= 2e-6
    assert worst <= PROTOCOL['acceptance']['assignment_max_objective_error']
    return {'markets': cases, 'profiles_per_market': 8, 'physical_candidates_per_market': 4,
            'vacancy_slots_per_market': 3, 'enumerated_assignments': enumerated, 'nonempty_optima': nonempty,
            'max_objective_error': worst, 'hard_constraint_violations': 0, 'duplicate_physical_assignments': 0,
            'oracle': 'exhaustive physical-person assignment, independent eligibility and utility'}

def role_contracts(module=rm):
    cases = 0
    for spec in ('backend_python','ml_data_science','data_engineering','mlops','frontend_development'):
        rubric = module.matrix({'specialization': spec})
        for grade, threshold in [('junior',1),('middle',2),('senior',3)]:
            for flags in itertools.product((False,True), repeat=4):
                for failed in (-1,0,1,2,3):
                    scores = {criterion['id']: threshold for criterion in rubric['criteria']}
                    if failed >= 0:
                        scores[rubric['criteria'][failed]['id']] = threshold-1
                    payload = {'specialization':spec,'grade':grade,'scores':scores,
                               **dict(zip(('identity_bound','artifact_intact','independent_review','knowledge_scope_verified'),flags))}
                    result = module.attestation(payload)
                    assert result['role_confirmation_eligible'] == (all(flags) and failed == -1)
                    assert not result['grade_auto_promoted']
                    cases += 1
    return {'role_grade_gate_cases': cases, 'roles': 5, 'grades': 3, 'false_confirmations': 0,
            'scope': 'full Boolean gate truth table and one failed mandatory practical criterion'}

def score_contracts(module=pv, cases=50):
    rng = np.random.default_rng(SEED); worst = 0.; pairwise = 0
    for _ in range(cases):
        p = np.round(rng.uniform(0,1,80),1); y = rng.integers(0,2,80)
        actual = module._scores(p,y)
        brier = math.fsum((float(a)-int(b))**2 for a,b in zip(p,y))/len(y)
        logloss = -math.fsum(math.log(min(1-1e-12,max(1e-12,float(a)))) if b else math.log1p(-min(1-1e-12,max(1e-12,float(a)))) for a,b in zip(p,y))/len(y)
        positive = [float(a) for a,b in zip(p,y) if b]; negative = [float(a) for a,b in zip(p,y) if not b]
        terms = [(a>b)+.5*(a==b) for a in positive for b in negative]; pairwise += len(terms)
        auc = math.fsum(terms)/len(terms)
        # Scalar equal-width bin oracle also checks p=1 belongs to final bin.
        bins = [[] for _ in range(10)]
        for a,b in zip(p,y):
            bins[min(9,int(float(a)*10))].append((float(a),int(b)))
        ece = math.fsum(abs(math.fsum(a for a,_ in group)-sum(b for _,b in group))/len(y) for group in bins if group)
        error = max(abs(actual['brier']-brier),abs(actual['log_loss']-logloss),abs(actual['auc']-auc),abs(actual['ece_10_equal_width']-ece))
        worst = max(worst,error)
    assert worst < PROTOCOL['acceptance']['numerical_score_max_absolute_error']
    assert module._scores([.1,.7],[1,1])['auc'] is None
    return {'cohorts': cases, 'probability_outcome_pairs': cases*80, 'auc_pairwise_comparisons':pairwise,
            'score_max_absolute_error': worst, 'scores': ['Brier','LogLoss','AUC with ties','ECE with boundary bins']}

def posterior_contracts(module=mm, cases=50):
    for index in range(cases):
        a,b = index%17,index%11
        result = module.posterior({'accepted':a,'declined':b,'censored':100000})
        assert abs(result['mean']-(a+1)/(a+b+2)) < 1e-12
        assert result['observed']==a+b
        assert result['interval_90'][0] <= result['mean'] <= result['interval_90'][1]
        base = module.posterior({'accepted':a,'declined':b})
        assert base['mean']==result['mean'] and base['interval_90']==result['interval_90']
        value = module.bilateral({'candidate':{'accepted':a,'declined':b},'employer':{'accepted':index%13+1,'declined':index%5}})
        p,q = value['candidate_acceptance']['mean'],value['employer_acceptance']['mean']
        lo,hi = value['joint_mean_bounds']
        assert abs(lo-max(0,p+q-1)) < 1e-12 and abs(hi-min(p,q)) < 1e-12
        assert lo <= p*q <= hi and value['joint_point_estimate'] is None
        assert not value['independence_assumed']
    return {'analytic_posterior_and_frechet_cases': cases, 'censoring_changes_to_mean_or_interval':0}

def equivalence_safety(module=ex):
    assert not module.equivalence({'a':[0,0,0,0], 'b':[0,0,0,0], 'paired_anchors':[[0,0]]*4})['statistical_gate_passed']
    assert not module.equivalence({'a':[0]*240,'b':[.4]*240,'paired_anchors':[[0,0]]*240})['equivalent']
    assert not module.equivalence({'a':[0]*240,'b':[0]*240,'paired_anchors':[[0,0]]*240})['production_activation_allowed']
    anchor=np.linspace(-1,1,120).tolist()
    assert module.equivalence({'a':anchor,'b':anchor})['equivalent']
    assert not module.equivalence({'a':anchor,'b':anchor,'planned_looks':20})['equivalent']

def equivalence_simulation():
    rng = np.random.default_rng(SEED+31); rows = []
    n = PROTOCOL['equivalence_group_size']; trials = PROTOCOL['equivalence_trials_per_shift']
    for shift in PROTOCOL['equivalence_shifts']:
        accepted = 0
        for _ in range(trials):
            a = rng.normal(0,PROTOCOL['equivalence_response_sd'],n)
            b = rng.normal(shift,PROTOCOL['equivalence_response_sd'],n)
            result = ex.equivalence({'a':a.tolist(),'b':b.tolist(),'margin':.2,'alpha':.05})
            accepted += result['equivalent']
            assert not result['production_activation_allowed']
        rows.append({'true_shift':shift, 'trials':trials, 'equivalence_acceptances':accepted,
                     'acceptance_rate':accepted/trials, 'wilson_95':wilson(accepted,trials)})
    assert all(row['acceptance_rate'] <= .10 for row in rows if abs(row['true_shift'])==.2)
    assert rows[-1]['equivalence_acceptances']==0
    equivalence_safety()
    sequential_acceptances=0
    for _ in range(trials):
        a=rng.normal(0,.4,240);b=rng.normal(.2,.4,240)
        accepted=False
        for size in (120,160,200,240):
            result=ex.equivalence({'a':a[:size].tolist(),'b':b[:size].tolist(),'planned_looks':4})
            accepted=accepted or result['equivalent']
        sequential_acceptances+=accepted
    assert sequential_acceptances/trials <= .10
    return {'settings':'independent Normal groups, SD .4, n=240, margin=.2, alpha=.05; authored response process',
            'conditions':rows,'planned_four_looks_boundary':{'trials':trials,'nested_sample_sizes':[120,160,200,240],
                'familywise_acceptances':sequential_acceptances,'familywise_rate':sequential_acceptances/trials,
                'wilson_95':wilson(sequential_acceptances,trials)},
            'not_real_role_equivalence':True,'production_activations':0}

def response_contracts(module=rp):
    value = module.analyze({'answers':[{'correct':True,'elapsed_ms':100,'expected_correct':.25}]*24})
    assert value['review_required']
    assert not value['automatic_accusation'] and not value['automatic_sanction'] and not value['previous_certificates_revoked']

def response_simulation():
    rng = np.random.default_rng(SEED+45); clean_alerts = 0; review_signals = 0; count=PROTOCOL['response_profiles_per_class']
    for _ in range(count):
        answers = [{'correct':bool(rng.uniform()<.7),'elapsed_ms':float(rng.lognormal(math.log(6500),.9)),
                    'expected_correct':float(rng.uniform(.25,.9))} for _ in range(24)]
        clean = rp.analyze({'answers':answers}); clean_alerts += clean['review_required']
        suspicious = rp.analyze({'answers':[{'correct':True,'elapsed_ms':100,'expected_correct':.25}]*24})
        review_signals += suspicious['review_required']
        for result in (clean,suspicious):
            assert not result['automatic_accusation'] and not result['automatic_sanction'] and not result['previous_certificates_revoked']
    return {'profiles_per_class':count,'authored_clean_review_rate':clean_alerts/count,
            'clean_review_wilson_95':wilson(clean_alerts,count),'rapid_constant_review_rate':review_signals/count,
            'automatic_sanctions':0,'interpretation':'screening behavior on an authored timing model; not empirical cheating detection accuracy'}

def posterior_simulation():
    rng = np.random.default_rng(SEED+71); total=PROTOCOL['posterior_simulations']; contained=0
    for _ in range(total):
        truth=float(rng.uniform()); accepted=int(rng.binomial(80,truth))
        interval=mm.posterior({'accepted':accepted,'declined':80-accepted})['interval_90']
        contained += interval[0] <= truth <= interval[1]
    return {'simulations':total,'observation_count_per_case':80,'prior_predictive_process':'p~Uniform(0,1); successes~Binomial(80,p)',
            'interval_level':.90,'observed_coverage':contained/total,'coverage_wilson_95':wilson(contained,total),
            'interpretation':'prior-predictive mathematical calibration, not field forecast calibration'}

MUTANTS = [
    ('posterior_denominator',mm,'a/(a+b)','a/(a-b)',posterior_contracts),
    ('frechet_lower_bound',mm,'low=max(0,','low=min(0,',posterior_contracts),
    ('hard_constraint_and_to_or',twins,'eligible=salary_ok and role_ok and grade_ok and required_grade_verified and not missing','eligible=salary_ok or role_ok or grade_ok or required_grade_verified or not missing',assignment_contracts),
    ('physical_person_grouping_removed',twins,"grouped.setdefault(c.get('candidate_id',c['id']),[])","grouped.setdefault(c['id'],[])",assignment_contracts),
    ('assignment_ineligible_cost',twins,"if x['eligible'] else 1e6","if x['eligible'] else -1e6",assignment_contracts),
    ('role_gate_all_to_any',rm,"all(conditions.values())","any(conditions.values())",role_contracts),
    ('small_cohort_gate_removed',ex,'>=120','>=0',equivalence_safety),
    ('planned_alpha_budget_ignored',ex,'alpha/looks','alpha',equivalence_safety),
    ('silent_role_activation',ex,"'production_activation_allowed':False","'production_activation_allowed':True",equivalence_safety),
    ('automatic_accusation',rp,"'automatic_accusation':False","'automatic_accusation':True",response_contracts),
    ('brier_difference_to_sum',pv,'(p-y)**2','(p+y)**2',score_contracts),
    ('auc_ties_removed',pv,".5*(np.searchsorted(ordered, positives, 'right')","0.*(np.searchsorted(ordered, positives, 'right')",score_contracts),
    ('relation_normalization_multiplied',nn,'relation/=np.maximum','relation*=np.maximum',graph_contracts),
]

def mutation_controls():
    rows=[]
    for name,module,old,new,verify in MUTANTS:
        source=Path(module.__file__).read_text(encoding='utf-8')
        assert old in source, name
        # Controlled executable source mutations in memory; production files/weights never change.
        modified=source.replace(old,new)
        ast.parse(modified)
        namespace={'__file__':module.__file__,'__name__':'proofit_controlled_mutant_'+name}
        exec(compile(modified,module.__file__,'exec'),namespace)
        status='survived';reason=None
        try:
            verify(SimpleNamespace(**namespace))
        except Exception as error:
            status='killed';reason=type(error).__name__
        rows.append({'mutation':name,'status':status,'detected_by':verify.__name__,'failure_kind':reason})
    return {'targeted_mutants':len(rows),'killed':sum(row['status']=='killed' for row in rows),
            'survived':sum(row['status']=='survived' for row in rows),'rows':rows,
            'scope':'13 explicitly specified semantic mutations; not exhaustive repository mutation coverage'}

def run():
    OUT.mkdir(parents=True,exist_ok=True)
    previous = OUT/'advanced-assurance.json'
    previous_report = None
    previous_digest = None
    if previous.exists():
        attempts = OUT/'advanced-assurance-attempts'; attempts.mkdir(exist_ok=True)
        previous_digest = hashlib.sha256(previous.read_bytes()).hexdigest()
        previous_report = json.loads(previous.read_text(encoding='utf-8'))
        shutil.copy2(previous, attempts/(previous_digest+'.json'))
    results={};timings={}
    steps=[('graph_metamorphic',lambda:graph_contracts(cases=PROTOCOL['graph_cases'])),
           ('gradient_audit',gradient_audit),('assignment_oracle',lambda:assignment_contracts(cases=PROTOCOL['allocation_markets'])),
           ('role_gates',role_contracts),('proper_scores',score_contracts),('posterior_contracts',posterior_contracts),
           ('ab_equivalence',equivalence_simulation),('response_review',response_simulation),
           ('posterior_coverage',posterior_simulation),('mutation_controls',mutation_controls)]
    for name,fn in steps:
        started=time.perf_counter();results[name]=fn();timings[name]=time.perf_counter()-started
        print(name, 'completed', flush=True)
    files=['validation/advanced_protocol.json','scripts/advanced_assurance.py',
           *['intelligence/'+name+'.py' for name in ('graph_neural','market_models','experiments','twins','role_matrix','response_patterns','prospective')],
           'intelligence/artifacts/graphsage.npz']
    source_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files}
    same_source = bool(previous_report and previous_report['source_sha256'] == source_sha256)
    equal = results == previous_report['results'] if same_source else None
    report={'passed':results['mutation_controls']['survived']==0 and equal is not False,'measured_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),
            'protocol':PROTOCOL,'results':results,'durations_seconds':timings,'python':platform.python_version(),
            'source_sha256':source_sha256,
            'reproducibility':{'previous_attempt_sha256':previous_digest,'same_source_comparison':same_source,
                               'all_deterministic_results_equal':equal,'timings_excluded_from_comparison':True},
            'llm_calls':0,'real_human_pilot':False,'results_selectively_filtered':False}
    (OUT/'advanced-assurance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'mutants_killed':results['mutation_controls']['killed'],
                      'report':'validation/reports/current/advanced-assurance.json'}))
    assert report['passed'], 'A semantic mutant survived; preserve the report and improve the detecting contract.'

if __name__=='__main__':
    run()
