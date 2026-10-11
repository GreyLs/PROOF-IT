"""Stable randomized parallel-form allocation and predeclared equivalence gates."""
import hashlib
import math
import numpy as np
from scipy.stats import norm, t

VERSION = 'parallel-forms-1.0.0'

def study_banks(payload):
    """Private operator artifact. Never a candidate/public answer-bank endpoint."""
    from intelligence import prospective, professional
    protocol=payload['protocol'];prospective.check_protocol(protocol,'parallel_forms')
    if protocol['model_version']!='role-parameter-forms-v1':raise ValueError('form_version')
    seed=int(hashlib.sha256((protocol['role']+':'+protocol['grade']+':'+protocol['model_version']).encode()).hexdigest()[:8],16)
    banks={variant:professional.create({'specialization':protocol['role'],'mode':'full','seed':seed,
                                       'form_variant':variant,'independent_forms':True}) for variant in ('A','B')}
    return {'protocol_sha256':protocol['protocol_sha256'],'contracts':banks,
            'contract_sha256':{variant:prospective.digest(bank) for variant,bank in banks.items()},
            'contains_private_answers':True,'candidate_access_allowed':False,
            'production_activation_allowed':False}

def assign(payload):
    identity=payload['identity'];scope=payload['scope'];version=payload.get('version','v1')
    if not all(isinstance(x,str) and 1<=len(x)<=200 for x in (identity,scope,version)):raise ValueError('assignment')
    digest=hashlib.sha256(f'{version}:{scope}:{identity}'.encode()).hexdigest()
    return {'version':VERSION,'variant':('A','B')[int(digest[:8],16)%2],
            'block':scope,'assignment_hash':digest,'stable_within_role':True,
            'method':'deterministic-role-blocked-hash-randomization','forms_interchangeable':False}

def equivalence(payload):
    a=np.asarray(payload['a'],dtype=float);b=np.asarray(payload['b'],dtype=float)
    margin=float(payload.get('margin',.2));alpha=float(payload.get('alpha',.05))
    if not 0<margin<=1 or not 0<alpha<.5 or a.ndim!=1 or b.ndim!=1 or min(len(a),len(b))<2 or max(len(a),len(b))>10000 or not np.isfinite(a).all() or not np.isfinite(b).all():raise ValueError('equivalence')
    looks=payload.get('planned_looks',1)
    if isinstance(looks,bool) or not isinstance(looks,int) or not 1<=looks<=20:raise ValueError('looks')
    effective=alpha/looks
    # Independent-group TOST; not a post-hoc failure-to-reject interpreted as equality.
    delta=float(a.mean()-b.mean());va=float(a.var(ddof=1)/len(a));vb=float(b.var(ddof=1)/len(b));se=math.sqrt(va+vb)
    if se==0:
        lower=upper=delta;p=0. if abs(delta)<margin else 1.;df=None
    else:
        df=(va+vb)**2/(va*va/(len(a)-1)+vb*vb/(len(b)-1))
        q=float(t.ppf(1-effective,df));lower,upper=delta-q*se,delta+q*se
        p=max(float(t.sf((delta+margin)/se,df)),float(t.cdf((delta-margin)/se,df)))
    # Sequential checks use an explicit Bonferroni alpha budget, not unlimited peeking.
    looks=payload.get('planned_looks',1)
    if isinstance(looks,bool) or not isinstance(looks,int) or not 1<=looks<=20:raise ValueError('looks')
    paired=payload.get('paired_anchors')
    anchor_shift=None;anchor_equivalent=False
    if paired is not None:
        anchors=np.asarray(paired,dtype=float)
        if anchors.ndim!=2 or anchors.shape[1]!=2 or not 2<=len(anchors)<=10000 or not np.isfinite(anchors).all():raise ValueError('anchors')
        differences=anchors[:,0]-anchors[:,1];anchor_shift=float(differences.mean());anchor_se=float(differences.std(ddof=1)/math.sqrt(len(differences)))
        anchor_p=(0. if abs(anchor_shift)<margin else 1.) if anchor_se==0 else max(float(t.sf((anchor_shift+margin)/anchor_se,len(differences)-1)),float(t.cdf((anchor_shift-margin)/anchor_se,len(differences)-1)))
        anchor_equivalent=len(differences)>=120 and anchor_p<effective
    return {'version':VERSION,'method':'Welch-TOST + role blocks + planned alpha spending',
            'sample_a':len(a),'sample_b':len(b),'mean_difference':delta,'confidence_interval':[lower,upper],
            'equivalence_margin':margin,'tost_p':p,'effective_alpha':alpha/looks,
            'equivalent':p<alpha/looks,'anchor_shift':anchor_shift,'anchor_equivalent':anchor_equivalent,
            'statistical_gate_passed':p<alpha/looks and min(len(a),len(b))>=120 and anchor_equivalent,
            'production_activation_allowed':False,
            'activation_requires':['independent role cohort','expert review','versioned publication'],
            'generalizes_to_other_roles':False}
