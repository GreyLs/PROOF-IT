"""Query-level ranking measures and reproducible macro bootstrap intervals."""
import math
import numpy as np

def measures(gains,available):
    relevant=sum(x>=2 for x in available);result={}
    dcg=lambda values:sum((2**x-1)/math.log2(i+2) for i,x in enumerate(values))
    for k in (5,10):
        top=gains[:k];ideal=dcg(sorted(available,reverse=True)[:k]);hits=sum(x>=2 for x in top)
        result[f'precision_at_{k}']=hits/k;result[f'recall_at_{k}']=hits/max(1,relevant);result[f'ndcg_at_{k}']=dcg(top)/ideal if ideal else 1.
    result['mrr_at_10']=next((1/(i+1) for i,x in enumerate(gains[:10]) if x>=2),0.)
    hits=0;ap=0
    for i,x in enumerate(gains[:10]):
        if x>=2:hits+=1;ap+=hits/(i+1)
    result['map_at_10']=ap/max(1,min(relevant,10))
    return result

def aggregate(rows):
    rng=np.random.default_rng(20261009);values=np.array([[r[k] for k in rows[0]] for r in rows],dtype=float);samples=values[rng.integers(0,len(rows),size=(1000,len(rows)))].mean(axis=1)
    return {'metrics':dict(zip(rows[0],values.mean(axis=0).tolist())),'bootstrap95':{k:np.quantile(samples[:,i],[.025,.975]).tolist() for i,k in enumerate(rows[0])},'bootstrap_method':'1000 query-level IID resamples, seed 20261009; macro means; does not account for shared candidate/vacancy correlations across queries'}
