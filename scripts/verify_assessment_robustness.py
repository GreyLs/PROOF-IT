"""Prespecified test--retest and parameter-stress simulation, without an LLM."""
import hashlib,json,math,time,sys
from pathlib import Path
import numpy as np
from intelligence import professional as cat
from scripts.validate_evidence import wilson

ROOT=Path(__file__).resolve().parents[1]

def refresh_statistics(report):
    """Resample whole latent persons, never correlated individual attempts."""
    rng=np.random.default_rng(report['protocol']['seed']+73)
    for summary in report['scenarios']:
        rows=[r for r in report['rows'] if r['scenario']==summary['scenario']]
        correct=np.array([sum(r[side]['grade']==r['truth_grade'] for side in ('a','b')) for r in rows])
        high=np.array([sum(r[side]['confidence']>=.85 for side in ('a','b')) for r in rows])
        high_correct=np.array([sum(r[side]['confidence']>=.85 and r[side]['grade']==r['truth_grade'] for side in ('a','b')) for r in rows])
        indices=rng.integers(0,len(rows),size=(1000,len(rows)))
        summary['accuracy_cluster_bootstrap95']=np.quantile(correct[indices].mean(axis=1)/2,[.025,.975]).tolist()
        ratios=high_correct[indices].sum(axis=1)/np.maximum(1,high[indices].sum(axis=1))
        summary['high_confidence_accuracy_cluster_bootstrap95']=np.quantile(ratios,[.025,.975]).tolist()
        summary.pop('high_confidence_accuracy_wilson95',None)
        summary['interval_method']='1000 person-cluster bootstrap replicates; both attempts remain together; fixed seed'
        summary['by_role']=[dict(role=role,paired_cases=sum(r['role']==role for r in rows),
            exact_grade_accuracy=sum(r[side]['grade']==r['truth_grade'] for r in rows if r['role']==role for side in ('a','b'))/max(1,2*sum(r['role']==role for r in rows))) for role in report['protocol']['roles']]
    return report

def kappa(a,b):
    matrix=np.zeros((3,3))
    for x,y in zip(a,b):matrix[x,y]+=1
    if not matrix.sum():return None
    observed=matrix/matrix.sum();expected=np.outer(observed.sum(axis=1),observed.sum(axis=0))
    distance=np.array([[(i-j)**2/4 for j in range(3)] for i in range(3)])
    denominator=float((distance*expected).sum())
    return 1-float((distance*observed).sum())/denominator if denominator else None

def run_attempt(theta,role,seed,variant,scenario):
    contract=cat.create(dict(seed=seed,specialization=role,mode='full',form_variant=variant,independent_forms=True))
    response=np.random.default_rng(seed+(0 if variant=='A' else 710003))
    perturb=np.random.default_rng(seed+(17 if variant=='A' else 810007))
    parameters={q['id']:dict(q,a=q['a']*math.exp(float(perturb.normal(0,scenario['discrimination_log_sd']))),b=q['b']+scenario['difficulty_shift']) for q in contract['bank']}
    while (item:=cat.next_item(contract)) is not None:
        correct=response.random()<float(cat.probability(theta,parameters[item['id']]))
        answer=item['correct'] if correct else (item['correct']+int(response.integers(1,4)))%4
        contract=cat.step(dict(contract=contract,question_id=item['id'],answer=answer,elapsed_ms=10000+137*len(contract['answers'])))['contract']
    result=cat.result(contract)
    return dict(theta=result['theta'],grade=cat.GRADES.index(result['suggested_grade']),
                confidence=max(result['grade_probabilities'].values()),questions=result['scored_questions'])

def main():
    start=time.perf_counter()
    path=ROOT/'validation/assessment_robustness_protocol.json';protocol=json.loads(path.read_text(encoding='utf-8'))
    taxonomy=json.loads((ROOT/'data/taxonomy.json').read_text(encoding='utf-8'))
    assert set(protocol['roles']) <= {r['id'] for r in taxonomy}, 'Unknown production role in protocol'
    target=ROOT/'validation/reports/current/assessment-robustness.json'
    if '--refresh-statistics' in sys.argv:
        report=json.loads(target.read_text(encoding='utf-8'))
        assert report['protocol_sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
        refresh_statistics(report)
        report['statistics_refreshed_at']=time.strftime('%Y-%m-%dT%H:%M:%S%z')
        target.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
        print('Paired-person cluster intervals recomputed from all retained observations.')
        return
    rows=[];summaries=[]
    # Same latent persons across scenarios; attempts use independent random draws.
    latent=np.random.default_rng(protocol['seed']).uniform(*protocol['theta_range'],protocol['paired_cases_per_scenario'])
    for scenario in protocol['scenarios']:
        cases=[]
        for i,theta in enumerate(latent):
            role=protocol['roles'][i%len(protocol['roles'])];seed=protocol['seed']+1009*i
            a=run_attempt(theta,role,seed,'A',scenario);b=run_attempt(theta,role,seed,'B',scenario)
            truth=0 if theta<-.5 else 1 if theta<1 else 2
            cases.append(dict(scenario=scenario['id'],person=i,role=role,latent_theta=float(theta),truth_grade=truth,
                              boundary_distance=min(abs(theta+.5),abs(theta-1)),a=a,b=b))
        grade_a=[r['a']['grade'] for r in cases];grade_b=[r['b']['grade'] for r in cases]
        attempts=[(r,r[side]) for r in cases for side in ('a','b')]
        certain=[(r,a) for r,a in attempts if a['confidence']>=protocol['confidence_threshold']]
        correct=sum(r['truth_grade']==a['grade'] for r,a in attempts)
        high_correct=sum(r['truth_grade']==a['grade'] for r,a in certain)
        slices=[]
        for label,low,high in [('near_boundary',0,.3),('intermediate',.3,.6),('separated',.6,10)]:
            group=[r for r in cases if low<=r['boundary_distance']<high]
            count=sum(r['a']['grade']==r['b']['grade'] for r in group)
            slices.append(dict(slice=label,paired_cases=len(group),repeat_agreement=count/len(group) if group else None,
                               wilson95=wilson(count,len(group)) if group else None))
        summaries.append(dict(scenario=scenario['id'],paired_cases=len(cases),attempts=len(attempts),
            exact_grade_accuracy=correct/len(attempts),
            repeat_agreement=sum(x==y for x,y in zip(grade_a,grade_b))/len(cases),
            quadratic_weighted_kappa=kappa(grade_a,grade_b),
            theta_rmse=float(np.sqrt(np.mean([(r['latent_theta']-a['theta'])**2 for r,a in attempts]))),
            repeat_theta_rmse=float(np.sqrt(np.mean([(r['a']['theta']-r['b']['theta'])**2 for r in cases]))),
            high_confidence_attempts=len(certain),high_confidence_accuracy=high_correct/len(certain) if certain else None,
            high_confidence_accuracy_wilson95=wilson(high_correct,len(certain)) if certain else None,
            high_confidence_coverage=len(certain)/len(attempts),boundary_slices=slices,
            interval_unit='attempt for accuracy; person-pair for repeat agreement; paired attempts are correlated'))
        rows.extend(cases)
        print(json.dumps(summaries[-1],ensure_ascii=False),flush=True)
    report=dict(passed=True,generated_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                protocol=protocol,protocol_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                paired_cases=len(rows),attempts=len(rows)*2,automatic_grade_updates=0,
                elapsed_seconds=time.perf_counter()-start,scenarios=summaries,rows=rows,
                limitation='Controlled response generator and authored parameters; all scenarios retained. No human participants, training on validation cases, activation of alternate forms or external hiring claims.')
    refresh_statistics(report)
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')

if __name__=='__main__':main()
