"""Qualification contracts share the CAT estimator and immutable role snapshot."""
from __future__ import annotations
import hashlib
from intelligence import professional as cat

VERSION = 'certification-3.0.0'

def prepare(payload):
    resume=payload['resume']
    seed=int(hashlib.sha256(str(payload.get('seed',42)).encode()).hexdigest()[:8],16)
    contract=cat.create({'seed':seed,'mode':'full','specialization':resume['specialization'],
                         'exposure':payload.get('exposure',{}),'quarantined':payload.get('quarantined',[]),
                         'pilots':payload.get('pilots',[])})
    contract.update(target_grade=resume['declared_grade'],version=VERSION,qualification=True)
    return {'version':VERSION,'contract':contract,'target_specialization':resume['specialization'],
            'target_grade':resume['declared_grade'],'questions':[],'review':{'deterministic_oracle':True}}

def decision(contract):
    result=cat.result(contract)
    threshold={'junior':-2.0,'middle':-.5,'senior':1.0}[contract['target_grade']]
    _,_,_,weights=cat.estimate(contract)
    confidence=float(weights[cat.GRID>=threshold].sum())
    passed=confidence>=.85 and not result['review_required']
    skills={}
    lookup={q['id']:q for q in contract['bank']}
    for answer in contract['answers']:
        if answer.get('pilot'):continue
        q=lookup[answer['question_id']]
        skill=q.get('skill')
        if skill:
            entry=skills.setdefault(skill,{'answered':0,'correct':0})
            entry['answered']+=1;entry['correct']+=int(answer['correct'])
    result.update(passed=passed,target_grade=contract['target_grade'],
                  confirmation_probability=round(confidence,5),
                  certified_skills=[k for k,v in skills.items() if v['answered']>=2 and v['correct']/v['answered']>=.75],
                  skill_evidence=skills,grade_changed=False,knowledge_grade_confirmed=passed,
                  certification_scope='role-knowledge',professional_role_certified=False,version=VERSION,
                  next_action='confirmation' if result['review_required'] else 'higher_test' if passed and confidence>.97 else 'lower_test' if not passed else 'maintain')
    return result

def step(payload):
    result=cat.step(payload)
    if result['completed']:result['result']=decision(result['contract'])
    return result
