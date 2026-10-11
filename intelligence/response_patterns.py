"""Bounded response signals: human review, no accusation or sanctions."""
import math
import statistics

VERSION='response-review-1.0.0'

def analyze(payload):
    answers=payload.get('answers',[])
    if not isinstance(answers,list) or len(answers)>100:raise ValueError('answers')
    if any(not isinstance(x,dict) or not isinstance(x.get('correct'),bool) for x in answers):raise ValueError('answer_record')
    scored=[x for x in answers if not x.get('pilot')]
    for x in scored:
        elapsed=x.get('elapsed_ms');prob=x.get('expected_correct',.5)
        if isinstance(elapsed,bool) or not isinstance(elapsed,(int,float)) or not math.isfinite(elapsed) or not 0<=elapsed<=86400000:raise ValueError('elapsed')
        if not isinstance(prob,(int,float)) or isinstance(prob,bool) or not math.isfinite(prob) or not 0<=prob<=1:raise ValueError('expected')
    signals=[]
    rapid=[i for i,x in enumerate(scored) if x['elapsed_ms']<800 and x.get('correct')]
    if len(scored)>=8 and len(rapid)>=6:
        signals.append({'kind':'rapid_correct_sequence','observations':len(rapid),'threshold':6,'item_indexes':rapid})
    logs=[math.log1p(x['elapsed_ms']) for x in scored]
    if len(logs)>=12:
        differences=[abs(b-a) for a,b in zip(logs,logs[1:])]
        elapsed_values=[x['elapsed_ms'] for x in scored]
        if statistics.median(differences)<.00005 and max(elapsed_values)-min(elapsed_values)<=2:
            signals.append({'kind':'near_constant_timing','observations':len(logs),'threshold_log_difference':.00005,'maximum_range_ms':2})
    # CAT has a 3PL guessing floor of .25: .15 would be an unreachable rule.
    surprising=[i for i,x in enumerate(scored) if x.get('correct') and x.get('expected_correct',.5)<.4 and x['elapsed_ms']<1200]
    if len(surprising)>=4:signals.append({'kind':'unlikely_rapid_successes','observations':len(surprising),'item_indexes':surprising})
    log_likelihood=sum(math.log(max(1e-9,min(1-1e-9,x.get('expected_correct',.5) if x.get('correct') else 1-x.get('expected_correct',.5)))) for x in scored)
    return {'version':VERSION,'signals':signals,'review_required':bool(signals),
            'action':'independent_context_review' if signals else 'none',
            'automatic_accusation':False,'automatic_sanction':False,'previous_certificates_revoked':False,
            'response_log_likelihood':log_likelihood,'scored_observations':len(scored),
            'threshold_status':'authored-screening, not population-calibrated',
            'alternative_explanations':['accessibility tools','network buffering','prior familiarity','timing instrumentation'],
            'reason_required_for_adverse_finding':True}
