"""Trainable two-layer typed GraphSAGE; CPU inference, no identity features.

Model learns a structural routing surrogate on controlled graphs. Its output
is advisory connectivity, never verified skill strength or a hiring outcome.
"""
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import numpy as np

VERSION='typed-graphsage-1.0.0'
ARTIFACT=Path(__file__).with_name('artifacts')/'graphsage.npz'

def tensors(graph):
    nodes=graph['nodes'];edges=graph['edges']
    if len(nodes)>1200 or len(edges)>20000:raise ValueError('neural_graph_limit')
    ids=[n['id'] for n in nodes]
    if len(set(ids))!=len(ids):raise ValueError('duplicate_nodes')
    index={identifier:i for i,identifier in enumerate(ids)}
    x=np.zeros((len(nodes),6),dtype=np.float64)
    for i,node in enumerate(nodes):
        kind=node.get('kind');x[i,{'evidence':0,'skill':1,'role':2}.get(kind,2)]=1
        strength=node.get('strength',.7 if kind=='evidence' else 0)
        if not np.isfinite(strength) or not 0<=strength<=1:raise ValueError('strength')
        x[i,3]=strength
    relations=[np.zeros((len(nodes),len(nodes)),dtype=np.float64) for _ in range(2)]
    for edge in edges:
        if edge['from'] not in index or edge['to'] not in index:raise ValueError('dangling_edge')
        weight=edge.get('weight',0)
        if not np.isfinite(weight) or not 0<=weight<=1:raise ValueError('edge_weight')
        if edge.get('relation') not in ('supports','transfers_to'):continue
        a,b=index[edge['from']],index[edge['to']]
        relation=relations[0 if edge['relation']=='supports' else 1]
        relation[a,b]+=weight;relation[b,a]+=weight
    for i,relation in enumerate(relations):
        degree=relation.sum(axis=1);x[:,4+i]=np.log1p(degree)/5
        relation/=np.maximum(degree[:,None],1e-12)
    return x,relations

def initialize(seed=20261010,hidden=16):
    rng=np.random.default_rng(seed)
    return {'w1':rng.normal(0,.14,(18,hidden)),'b1':np.zeros(hidden),
            'w2':rng.normal(0,.14,(hidden*3,hidden)),'b2':np.zeros(hidden),
            'wo':rng.normal(0,.14,(hidden,1)),'bo':np.zeros(1)}

def forward(x,relations,weights):
    a,b=relations
    z=np.concatenate([x,a@x,b@x],axis=1)
    h=np.tanh(z@weights['w1']+weights['b1'])
    neighbors=np.concatenate([h,a@h,b@h],axis=1)
    h2=np.tanh(neighbors@weights['w2']+weights['b2'])
    logits=np.clip(h2@weights['wo']+weights['bo'],-30,30)
    prediction=1/(1+np.exp(-logits))
    return prediction[:,0],(z,h,neighbors,h2)

def gradients(x,relations,weights,target):
    prediction,(z,h,neighbors,h2)=forward(x,relations,weights)
    dlogit=(prediction-np.asarray(target))[:,None]/max(1,len(target))
    output={'wo':h2.T@dlogit,'bo':dlogit.sum(axis=0)}
    dh2=(dlogit@weights['wo'].T)*(1-h2*h2)
    output['w2']=neighbors.T@dh2;output['b2']=dh2.sum(axis=0)
    back=dh2@weights['w2'].T;width=h.shape[1]
    dh=(back[:,:width]+relations[0].T@back[:,width:width*2]+relations[1].T@back[:,width*2:])*(1-h*h)
    output['w1']=z.T@dh;output['b1']=dh.sum(axis=0)
    return prediction,output

@lru_cache(maxsize=1)
def load():
    manifest=json.loads(ARTIFACT.with_suffix('.json').read_text(encoding='utf-8'))
    if manifest['version']!=VERSION or hashlib.sha256(ARTIFACT.read_bytes()).hexdigest()!=manifest['sha256']:raise ValueError('model_integrity')
    with np.load(ARTIFACT,allow_pickle=False) as data:
        weights={key:data[key] for key in ('w1','b1','w2','b2','wo','bo')}
    if any(not np.isfinite(value).all() for value in weights.values()):raise ValueError('nonfinite_weights')
    return weights,manifest

def infer(graph):
    if not graph['nodes']:return {'version':VERSION,'status':'empty_graph','nodes':[],'automatic_skill_verification':False}
    if not ARTIFACT.exists():return {'version':VERSION,'status':'model_not_available','nodes':[],'automatic_skill_verification':False}
    weights,manifest=load();x,relations=tensors(graph);scores,_=forward(x,relations,weights)
    return {'version':VERSION,'status':'trained','architecture':'2-layer typed GraphSAGE, self/support/transfer aggregation',
            'model_sha256':manifest['sha256'],'training_domain':manifest['training_domain'],
            'nodes':[{'id':node['id'],'routing_score':float(score)} for node,score in zip(graph['nodes'],scores)],
            'parameter_count':sum(value.size for value in weights.values()),
            'sensitive_features_used':[],'automatic_skill_verification':False,'automatic_grade_promotion':False,
            'estimate_kind':'learned structural routing score, not hiring probability'}
