"""Two-sided uncertain decisions and transparent employer observations."""
import math
import numpy as np
from scipy.stats import beta

VERSION='bilateral-market-1.0.0'

def posterior(record):
    if not isinstance(record,dict):raise ValueError('observation_record')
    success=record.get('accepted',0);failure=record.get('declined',0)
    if any(isinstance(v,bool) or not isinstance(v,int) or not 0<=v<=10000000 for v in (success,failure,record.get('censored',0))):raise ValueError('observations')
    a,b=1+success,1+failure
    return {'mean':a/(a+b),'interval_90':[float(beta.ppf(.05,a,b)),float(beta.ppf(.95,a,b))],
            'observed':success+failure,'accepted':success,'declined':failure,
            'censored_excluded':record.get('censored',0),'alpha':a,'beta':b}

def bilateral(payload):
    stage=payload.get('stage','offer')
    if stage not in ('vacancy','offer'):raise ValueError('stage')
    candidate=posterior(payload.get('candidate',{}));employer=posterior(payload.get('employer',{}))
    low=max(0,candidate['mean']+employer['mean']-1);high=min(candidate['mean'],employer['mean'])
    joint_data=payload.get('joint',{})
    joint=posterior(joint_data) if joint_data.get('accepted',0)+joint_data.get('declined',0)>0 else None
    bound=[max(0,candidate['interval_90'][0]+employer['interval_90'][0]-1),min(candidate['interval_90'][1],employer['interval_90'][1])]
    return {'version':VERSION,'stage':stage,'candidate_acceptance':candidate,'employer_acceptance':employer,
            'joint_mean_bounds':[low,high],'joint_uncertainty_bounds':bound,
            'joint_observation_posterior':joint,'joint_point_estimate':joint['mean'] if joint else None,
            'independence_assumed':False,'calibration_status':'insufficient_observed_outcomes' if min(candidate['observed'],employer['observed'])<120 else 'requires_temporal_holdout',
            'estimate_kind':'Bayesian observational scenario, not certified hiring probability',
            'autonomous_hiring_decision':False,'sensitive_features_used':[]}

def reliability(payload):
    indicators={key:posterior(payload.get(key,{})) for key in ('response','offer_followthrough','bilateral_followup')}
    observed=[v for v in indicators.values() if v['observed']>=10]
    return {'version':VERSION,'indicators':indicators,'verified_identity':payload.get('verified_identity') is True,
            'conservative_observed_index':float(np.mean([x['interval_90'][0] for x in observed])) if observed else None,
            'coverage':len(observed)/len(indicators),'insufficient_evidence_is_not_negative':True,
            'external_employee_reviews':payload.get('employee_reviews'),
            'rating_is_not_candidate_competence':True,'synthetic_context':bool(payload.get('synthetic')),
            'method':'separate Beta-binomial observations with lower credible bounds; missing dimensions excluded'}

def robust_twin(payload):
    base=bilateral(payload)
    alternatives=payload.get('alternatives',[])
    if not isinstance(alternatives,list) or len(alternatives)>30:raise ValueError('alternatives')
    rows=[]
    for index,alternative in enumerate(alternatives):
        cost=alternative.get('budget_increase_rub',0)
        if isinstance(cost,bool) or not isinstance(cost,(int,float)) or not math.isfinite(cost) or cost<0:raise ValueError('budget')
        scenario=bilateral({**payload,**alternative})
        rows.append({'id':str(alternative.get('id',index)),'budget_increase_rub':cost,
                     'conservative_joint_bound':scenario['joint_uncertainty_bounds'][0],
                     'joint_bounds':scenario['joint_mean_bounds'],'assumptions':alternative.get('assumptions',[])})
    for row in rows:
        row['pareto_dominated']=any(other['budget_increase_rub']<=row['budget_increase_rub'] and other['conservative_joint_bound']>=row['conservative_joint_bound'] and (other['budget_increase_rub']<row['budget_increase_rub'] or other['conservative_joint_bound']>row['conservative_joint_bound']) for other in rows)
    return {'version':VERSION,'baseline':base,'alternatives':rows,'frontier':[x for x in rows if not x['pareto_dominated']],
            'method':'two-sided partial identification + posterior downside + Pareto frontier',
            'counterfactual_is_causal_claim':False,'constraints_never_relaxed_implicitly':True}
