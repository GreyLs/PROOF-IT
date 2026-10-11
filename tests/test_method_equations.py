"""Independent numeric oracles for the equations published in Methods.pdf."""
import math
import numpy as np
import pytest
from scipy.stats import beta
from intelligence import professional, graph_neural, market_models, twins


@pytest.mark.parametrize('seed', range(10))
def test_discrete_eap_matches_independent_log_likelihood(seed):
    rng=np.random.default_rng(seed)
    bank=[dict(id=str(i),a=float(rng.uniform(.7,1.8)),b=float(rng.uniform(-2,2)),c=.25,pilot=i==2) for i in range(12)]
    answers=[dict(question_id=q['id'],correct=bool(rng.integers(2))) for q in bank]
    contract=dict(bank=bank,answers=answers)
    grid=[-4+.05*j for j in range(161)]
    logs=[]
    for theta in grid:
        value=-theta*theta/2
        for q,a in zip(bank,answers):
            if q['pilot']:continue
            p=.25+.75/(1+math.exp(-q['a']*(theta-q['b'])))
            value+=math.log(p if a['correct'] else 1-p)
        logs.append(value)
    weights=[math.exp(x-max(logs)) for x in logs]
    total=math.fsum(weights);weights=[x/total for x in weights]
    mean=math.fsum(x*y for x,y in zip(grid,weights))
    deviation=math.sqrt(math.fsum(y*(x-mean)**2 for x,y in zip(grid,weights)))
    theta,se,_,actual=professional.estimate(contract)
    assert abs(theta-mean)<1e-12 and abs(se-deviation)<1e-12
    assert np.max(np.abs(actual-weights))<1e-12


@pytest.mark.parametrize('seed', range(10))
def test_typed_graphsage_forward_matches_scalar_layer_equations(seed):
    rng=np.random.default_rng(seed)
    graph=dict(nodes=[dict(id='a',kind='evidence',strength=.8),dict(id='b',kind='skill',strength=.6),dict(id='c',kind='role')],
               edges=[dict(**{'from':'a','to':'b'},relation='supports',weight=.8),dict(**{'from':'b','to':'c'},relation='transfers_to',weight=.68)])
    x,relations=graph_neural.tensors(graph)
    w=graph_neural.initialize(seed=seed)
    # Scalar aggregation is deliberately separate from the vectorized forward.
    def aggregate(matrix,data):
        return [[math.fsum(matrix[i,j]*data[j,k] for j in range(3)) for k in range(data.shape[1])] for i in range(3)]
    def layer(data,key):
        merged=np.concatenate([data,np.array(aggregate(relations[0],data)),np.array(aggregate(relations[1],data))],axis=1)
        return np.array([[math.tanh(math.fsum(merged[i,k]*w['w'+key][k,j] for k in range(merged.shape[1]))+w['b'+key][j]) for j in range(16)] for i in range(3)])
    first=layer(x,'1');second=layer(first,'2')
    expected=[1/(1+math.exp(-max(-30,min(30,math.fsum(second[i,j]*w['wo'][j,0] for j in range(16))+w['bo'][0])))) for i in range(3)]
    actual,_=graph_neural.forward(x,relations,w)
    assert np.max(np.abs(actual-expected))<1e-12


@pytest.mark.parametrize('accepted,declined,censored', [(0,0,500),(1,9,0),(9,1,100),(120,80,17),(500,0,20)])
def test_bilateral_beta_and_frechet_equations(accepted,declined,censored):
    output=market_models.bilateral(dict(candidate=dict(accepted=accepted,declined=declined,censored=censored),employer=dict(accepted=declined,declined=accepted)))
    c=output['candidate_acceptance'];e=output['employer_acceptance']
    assert c['mean']==(1+accepted)/(2+accepted+declined)
    assert np.allclose(c['interval_90'],beta.ppf([.05,.95],1+accepted,1+declined),atol=1e-12,rtol=0)
    assert output['joint_mean_bounds']==[max(0,c['mean']+e['mean']-1),min(c['mean'],e['mean'])]
    assert c['censored_excluded']==censored and output['joint_point_estimate'] is None


def test_next_proof_counts_single_gap_with_the_published_weight():
    candidate=dict(id='r',specialization='backend_python',grade='middle',grade_verified=True,salary=100,support={'python':.8})
    vacancies=[dict(id='v1',specialization='backend_python',grade='middle',salary=200,skills=['Python','SQL']),
               dict(id='v2',specialization='backend_python',grade='middle',salary=200,skills=['Python','SQL','Docker'])]
    result=twins.next_proof(dict(candidate=candidate,vacancies=vacancies,minutes={'sql':20,'docker':30}))
    task=next(x for x in result['tasks'] if x['skill']=='sql')
    assert task['single_gap_opportunities']==1 and task['vacancies_requiring_proof']==2
    assert task['opportunity_value_per_minute']==round((1+.25*2)/20,6)
