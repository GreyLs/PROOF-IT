"""Predeclared controlled numerical checks, never a hiring-accuracy claim."""
from pathlib import Path
import asyncio,hashlib,json,time,xml.etree.ElementTree as ET
import numpy as np
from intelligence import experiments,market_models,graph_neural,github_evidence
from scripts.train_graph_neural import sample
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'validation/reports/current'

def main():
    rng=np.random.default_rng(20261010);start=time.perf_counter();metrics={}
    rows=[experiments.assign({'identity':str(i),'scope':'backend_python:middle','version':'validation-v1'}) for i in range(10000)]
    metrics['allocation_sample']=len(rows);metrics['variant_a_share']=sum(x['variant']=='A' for x in rows)/len(rows)
    coverage=0;violations=0
    for _ in range(5000):
        truth=float(rng.uniform());success=int(rng.binomial(120,truth));r=market_models.posterior({'accepted':success,'declined':120-success});lo,hi=r['interval_90'];coverage+=lo<=truth<=hi
        q=market_models.bilateral({'candidate':{'accepted':success,'declined':120-success},'employer':{'accepted':int(rng.integers(121)),'declined':120}})
        low,high=q['joint_mean_bounds'];p=q['candidate_acceptance']['mean']*q['employer_acceptance']['mean'];violations+=not(0<=low<=p<=high<=1)
    metrics.update(posterior_interval_trials=5000,posterior_interval_coverage=coverage/5000,frechet_bound_violations=violations)
    shifts=[];latencies=[];weights,_=graph_neural.load()
    for seed in range(12000,12100):
        graph,x,relations,target=sample(seed);before=graph_neural.infer(graph);graph['nodes'].reverse();after=graph_neural.infer(graph)
        a={n['id']:n['routing_score'] for n in before['nodes']};b={n['id']:n['routing_score'] for n in after['nodes']};shifts.extend(abs(a[k]-b[k]) for k in a)
        tick=time.perf_counter();graph_neural.infer(graph);latencies.append((time.perf_counter()-tick)*1000)
    metrics.update(permutation_graphs=100,permutation_nodes=len(shifts),permutation_max_score_difference=max(shifts),end_to_end_gnn_p95_ms=float(np.percentile(latencies,95)))
    a=rng.normal(0,.6,1000);b=rng.normal(.02,.6,1000);anchors=np.column_stack([a,a+rng.normal(.01,.02,1000)])
    eq=experiments.equivalence({'a':a.tolist(),'b':b.tolist(),'paired_anchors':anchors.tolist(),'planned_looks':10})
    negative=experiments.equivalence({'a':a.tolist(),'b':(b+.5).tolist(),'paired_anchors':anchors.tolist(),'planned_looks':10})
    metrics.update(controlled_tost=eq,shifted_control_rejected=not negative['equivalent'])
    assert violations==0 and max(shifts)<1e-12 and .86<coverage/5000<.94 and eq['equivalent'] and not negative['equivalent']
    scopes={
        'posterior_interval_coverage':'Beta(1,1) + Binomial n=120, 5,000 predeclared simulated truths; not hiring outcome calibration',
        'gnn_permutation':'100 independently generated controlled graphs, weights fixed; score invariance under node reorder',
        'parallel_forms':'controlled numerical TOST samples; not human role-form equivalence approval',
    }
    report={'passed':True,'measured_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'seed':20261010,'llm_calls':0,'metrics':metrics,'scope':scopes,'elapsed_seconds':time.perf_counter()-start,'real_hiring_labels':0}
    OUT.mkdir(parents=True,exist_ok=True);(OUT/'research-metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report))

async def live_github():
    client=github_evidence.PublicClient();repo=await github_evidence.fetch_repository({'repository':'psf/requests'},client)
    for item in repo['pull_requests'][:4]:
        try:snapshot=await github_evidence.fetch_pr({'url':item['url'],'specialization':'backend_python'},client);break
        except ValueError:continue
    else:raise AssertionError('No small public text PR available in bounded sample')
    report={'passed':True,'measured_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'scope':'Actual read-only GitHub REST; no identity binding or human authorship verdict claimed','repository':repo['repository'],'commits':len(repo['commits']),'prs':len(repo['pull_requests']),'repository_discussions_status':repo['repository_discussions']['status'],'pr_url':snapshot['url'],'artifact_digest':snapshot['digest'],'head_sha':snapshot['head_sha'],'files':len(snapshot['files']),'pr_commits':len(snapshot['commits']),'discussion_items':len(snapshot['discussion']),'questions':len(snapshot['questions']),'coverage':snapshot['coverage'],'rate_limits':client.rates,'code_executed':False,'llm_calls':0}
    (OUT/'github-live.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report))

if __name__=='__main__':
    import sys
    if '--live-github' in sys.argv:asyncio.run(live_github())
    else:main()
