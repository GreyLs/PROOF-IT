"""Evidence-grounded twin operations. Pure CPU, bounded input, no LLM calls."""
from __future__ import annotations
import ast, hashlib, math
from scipy.optimize import linear_sum_assignment

VERSION = 'twin-evidence-3.0.0'

def unit(x):
    if isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or not 0<=x<=1: raise ValueError('unit')
    return float(x)

def skills(item):
    return {str(k).strip().lower():unit(v) for k,v in item.get('support',{}).items()}

def requirements(v):
    return sorted({str(x).strip().lower() for x in v.get('skills',[]) if str(x).strip()})

def pair(c,v):
    support=skills(c); required=requirements(v)
    verified=[s for s in required if support.get(s,0)>=.5]
    missing=[s for s in required if s not in verified]
    coverage=sum(support.get(s,0) for s in required)/max(1,len(required))
    salary_ok=float(c.get('salary',0))<=float(v.get('salary',0))
    role_ok=c.get('specialization')==v.get('specialization')
    grade_ok={'junior':0,'middle':1,'senior':2}.get(c.get('grade'),-1)>={'junior':0,'middle':1,'senior':2}.get(v.get('grade'),0)
    required_grade_verified=bool(c.get('grade_verified',False))
    eligible=salary_ok and role_ok and grade_ok and required_grade_verified and not missing
    prefs=c.get('preferences',{}); team=v.get('team',{})
    comparable=[k for k in ('collaboration','pace','growth') if prefs.get(k) and team.get(k)]
    alignment=sum(prefs[k]==team[k] for k in comparable)/len(comparable) if comparable else None
    # Unknown preferences never count as disagreement and never gate employment.
    utility=round(coverage,6)
    return {'candidate_id':c.get('candidate_id',c['id']),'resume_id':c['id'],'vacancy_id':v['id'],'eligible':eligible,'utility':utility,'verified_skills':verified,'unknown_skills':missing,'salary_compatible':salary_ok,'same_role':role_ok,'grade_compatible':grade_ok and required_grade_verified,'working_preferences_alignment':alignment,'preference_fields_observed':comparable,'sensitive_features_used':[]}

def compatibility(p):
    result=pair(p['candidate'],p['vacancy'])
    return {'version':VERSION,**result,'method':'hard-constraints + temporally-weighted-evidence','autonomous_hiring_decision':False}

def allocation(p):
    cs=p.get('candidates',[]);vs=p.get('vacancies',[])
    if len(cs)>100 or len(vs)>30:raise ValueError('allocation_limit')
    slots=[]
    for v in vs:
        count=v.get('slots',1)
        if isinstance(count,bool) or not isinstance(count,int) or not 1<=count<=10:raise ValueError('slots')
        slots.extend([v]*count)
    if len(slots)>100:raise ValueError('slots_limit')
    if not cs or not slots:return {'version':VERSION,'assignments':[],'unfilled_slots':len(slots),'total_utility':0,'method':'maximum-weight-bipartite-assignment','empty_market':True}
    grouped={}
    for c in cs:grouped.setdefault(c.get('candidate_id',c['id']),[]).append(c)
    pairs=[]
    for profiles in grouped.values():
        row=[]
        for v in slots:
            variants=[pair(c,v) for c in profiles]
            row.append(max(variants,key=lambda x:(x['eligible'],x['utility'],x['resume_id'])))
        pairs.append(row)
    cs=list(grouped)
    # Dummy columns permit leaving a slot empty instead of violating a constraint.
    costs=[[-x['utility'] if x['eligible'] else 1e6 for x in row]+[0.0]*len(cs) for row in pairs]
    rows,cols=linear_sum_assignment(costs)
    chosen=[pairs[int(r)][int(c)] for r,c in zip(rows,cols) if c<len(slots) and pairs[int(r)][int(c)]['eligible']]
    return {'version':VERSION,'assignments':chosen,'unfilled_slots':len(slots)-len(chosen),'total_utility':round(sum(x['utility'] for x in chosen),6),'method':'maximum-weight-bipartite-assignment','constraints':['one-candidate-one-slot','verified-grade','verified-required-skills','salary','role'],'autonomous_hiring_decision':False}

def next_proof(p):
    c=p['candidate'];vs=p.get('vacancies',[])
    if len(vs)>100:raise ValueError('vacancy_limit')
    support=skills(c);gaps={}
    for v in vs:
        if not (c.get('specialization')==v.get('specialization') and float(c.get('salary',0))<=float(v.get('salary',0))):continue
        missing=[s for s in requirements(v) if support.get(s,0)<.5]
        for s in missing:
            x=gaps.setdefault(s,{'skill':s,'vacancies_requiring_proof':0,'single_gap_opportunities':0,'candidate_ids':[]})
            grade_ok=bool(c.get('grade_verified')) and {'junior':0,'middle':1,'senior':2}.get(c.get('grade'),-1)>={'junior':0,'middle':1,'senior':2}.get(v.get('grade'),0)
            x['vacancies_requiring_proof']+=1;x['single_gap_opportunities']+=len(missing)==1 and grade_ok
    durations=p.get('minutes',{})
    for x in gaps.values():
        duration=float(durations.get(x['skill'],30))
        if not math.isfinite(duration) or not 5<=duration<=120:raise ValueError('minutes')
        x['minutes']=duration;x['opportunity_value_per_minute']=round((x['single_gap_opportunities']+.25*x['vacancies_requiring_proof'])/duration,6)
        x.pop('candidate_ids')
    tasks=sorted(gaps.values(),key=lambda x:(-x['opportunity_value_per_minute'],x['skill']))
    return {'version':VERSION,'tasks':tasks[:10],'method':'deterministic-opportunity-gap-value','estimate_kind':'market-gap-count, not hiring-probability','target':'verify skills, never fabricate them'}

def diagnosis(p):
    v=p['vacancy'];cs=p.get('candidates',[])
    if len(cs)>100:raise ValueError('candidate_limit')
    rows=[pair(c,v) for c in cs]
    relax=[]
    for c,r in zip(cs,rows):
        if not r['same_role']:continue
        relax.append({'candidate_id':c['id'],'skills_to_verify':r['unknown_skills'],'salary_increase_rub':max(0,int(c.get('salary',0))-int(v.get('salary',0))),'grade_requires_verification':not r['grade_compatible'],'changes_count':len(r['unknown_skills'])+int(not r['salary_compatible'])+int(not r['grade_compatible'])})
    relax.sort(key=lambda x:(x['changes_count'],x['salary_increase_rub'],x['candidate_id']))
    return {'version':VERSION,'pool_size':len(cs),'eligible_count':sum(x['eligible'] for x in rows),'constraints_satisfiable':any(x['eligible'] for x in rows),'minimal_relaxations':relax[:5],'constraints_remain_enforced':True,'method':'finite-pool-constraint-diagnostics','no_candidates_invented':True}

def transfer(p):
    support=skills(p['candidate']);roles=p.get('roles',[])
    result=[]
    for role in roles:
        req=requirements(role);proven=[s for s in req if support.get(s,0)>=.5]
        if proven:result.append({'id':role['id'],'label':role.get('label',role['id']),'verified_transferable_skills':proven,'skills_to_verify':[s for s in req if s not in proven],'coverage':len(proven)/max(1,len(req)),'role_grade_auto_transferred':False})
    result.sort(key=lambda x:(-x['coverage'],x['id']))
    return {'version':VERSION,'routes':result[:10],'method':'verified-prerequisite-transfer','qualification_required_for_target_role':True}

def authorship(p):
    code=p.get('code','');language=p.get('language','python')
    if not isinstance(code,str) or not 10<=len(code)<=20000:raise ValueError('code_size')
    if language=='python':
        try:tree=ast.parse(code)
        except SyntaxError:raise ValueError('syntax')
        functions=[x for x in ast.walk(tree) if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef))][:5]
        names=[x.name for x in functions]
        branches=sum(isinstance(x,(ast.If,ast.For,ast.While,ast.Try)) for x in ast.walk(tree))
    else:
        import re
        names=re.findall(r'(?:function\s+|(?:const|let)\s+)([A-Za-z_][A-Za-z_0-9]*)',code)[:5];branches=len(re.findall(r'\b(if|for|while|case)\b',code))
    symbol=names[0] if names else 'основного решения'
    return {'version':VERSION,'code_hash':hashlib.sha256(code.encode()).hexdigest(),'language':language,'questions':[f'Объясните контракт {symbol}: вход, выход и поведение на пустом входе.',f'Покажите на своём коде инвариант и оцените сложность; обнаружено ветвлений: {branches}.',f'Измените {symbol} для потокового входа и добавьте тест на границу; обоснуйте, что сохранилось.'],'ai_assistance_declared':bool(p.get('ai_assisted',False)),'baseline_and_assisted_separate':True,'assessment_state':'defense_required','automatic_authorship_verdict':False}
