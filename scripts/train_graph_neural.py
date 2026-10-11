"""Reproducible controlled structural-distillation benchmark, not market efficacy."""
import hashlib
import json
import time
from pathlib import Path
import numpy as np
from intelligence.graph_neural import VERSION,ARTIFACT,tensors,initialize,forward,gradients

ROOT=Path(__file__).resolve().parents[1]

def sample(seed):
    rng=np.random.default_rng(seed)
    nodes=[{'id':f'e{i}','kind':'evidence','strength':float(rng.uniform(.1,.95))} for i in range(8)]
    nodes += [{'id':f's{i}','kind':'skill','strength':float(rng.uniform(0,1))} for i in range(8)]
    nodes += [{'id':f'r{i}','kind':'role','strength':0.} for i in range(4)]
    edges=[]
    for i in range(8):
        for j in rng.choice(8,size=3,replace=False):
            edges.append({'from':f'e{i}','to':f's{j}','weight':nodes[i]['strength'],'relation':'supports'})
    for i in range(4):
        for j in rng.choice(8,size=4,replace=False):
            if nodes[8+j]['strength']>=.5:
                edges.append({'from':f's{j}','to':f'r{i}','weight':nodes[8+j]['strength'],'relation':'transfers_to'})
    graph={'nodes':nodes,'edges':edges};x,relations=tensors(graph)
    # Two-hop bounded target is an explicit structural teacher, not employment labels.
    target=np.clip(.08+.45*x[:,3]+.18*(relations[0]@x[:,3])+.25*(relations[1]@x[:,3]),.02,.98)
    return graph,x,relations,target

def main():
    started=time.perf_counter();train=[sample(seed) for seed in range(160)];test=[sample(seed) for seed in range(10000,10080)]
    weights=initialize();m={k:np.zeros_like(v) for k,v in weights.items()};v={k:np.zeros_like(value) for k,value in weights.items()};step=0
    for epoch in range(30):
        for _,x,relations,target in train:
            _,updates=gradients(x,relations,weights,target);step+=1
            for key in weights:
                m[key]=.9*m[key]+.1*updates[key];v[key]=.999*v[key]+.001*updates[key]**2
                weights[key]-=.004*(m[key]/(1-.9**step))/(np.sqrt(v[key]/(1-.999**step))+1e-8)
    errors=[];baseline=[];latencies=[]
    for _,x,relations,target in test:
        begin=time.perf_counter();prediction,_=forward(x,relations,weights);latencies.append((time.perf_counter()-begin)*1000)
        errors.extend(prediction-target);baseline.extend(np.full(len(target),.5)-target)
    ARTIFACT.parent.mkdir(exist_ok=True);np.savez_compressed(ARTIFACT,**weights)
    digest=hashlib.sha256(ARTIFACT.read_bytes()).hexdigest()
    report={'passed':True,'version':VERSION,'training_domain':'controlled structural teacher; no real hiring-outcome calibration',
            'train_graphs':len(train),'holdout_graphs':len(test),'holdout_nodes':len(errors),
            'split':'disjoint graph-generating seeds; test never optimized','sha256':digest,
            'mae':float(np.mean(np.abs(errors))),'rmse':float(np.sqrt(np.mean(np.square(errors)))),
            'constant_prior_mae':float(np.mean(np.abs(baseline))),'p95_inference_ms':float(np.percentile(latencies,95)),
            'elapsed_seconds':time.perf_counter()-started,'llm_used':False,'autonomous_certification':False,
            'parameter_count':sum(value.size for value in weights.values())}
    assert report['mae']<report['constant_prior_mae'] and np.isfinite(report['rmse'])
    ARTIFACT.with_suffix('.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (ROOT/'validation/reports/current/graph-neural.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))

if __name__=='__main__':main()
