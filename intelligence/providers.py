"""Prepared partner adapters; unavailable credentials produce neutral evidence."""
import json, os, re
from datetime import datetime, timezone
from urllib.parse import urlsplit
import httpx
from worker.config import secret

VERSION='partner-contract-1.0.0'
def source_url(value,provider):
    u=urlsplit(value)
    allowed=('dreamjob.ru','www.dreamjob.ru') if provider=='dreamjob' else ('fsp-russia.com','www.fsp-russia.com')
    if u.scheme!='https' or u.hostname not in allowed or u.username or u.port not in (None,443):raise ValueError('source_origin')
    return value

def normalize(provider,p):
    if not isinstance(p,dict):raise ValueError('schema')
    if provider=='dreamjob':
        rating=p.get('rating');count=p.get('review_count')
        if isinstance(rating,bool) or not isinstance(rating,(int,float)) or not 0<=rating<=5:raise ValueError('rating')
        if isinstance(count,bool) or not isinstance(count,int) or not 1<=count<=10000000:raise ValueError('review_count')
        date=datetime.fromisoformat(p['updated_at'].replace('Z','+00:00'))
        if date.tzinfo is None or date>datetime.now(timezone.utc):raise ValueError('timestamp')
        return {'rating':rating,'review_count':count,'source_url':source_url(p['source_url'],provider),'updated_at':date.isoformat(),'kind':'employee-reviews','verified_candidate_skill':False}
    if provider=='fsp':
        events=p.get('participations',[])
        if not isinstance(events,list) or len(events)>100:raise ValueError('events')
        result=[]
        for e in events:
            if not all(isinstance(e.get(k),str) and 1<=len(e[k])<=500 for k in ('event_id','event_name','discipline','result')):raise ValueError('event')
            result.append({k:e[k] for k in ('event_id','event_name','discipline','result') }|{'source_url':source_url(e['source_url'],provider),'event_date':e.get('event_date')})
        return {'participations':result,'registry_verified':True,'identity_implies_achievement':False}
    raise ValueError('provider')

async def fetch(p):
    provider=p['provider'];subject=p['subject_id']
    if provider not in ('fsp','dreamjob') or not re.fullmatch(r'[A-Za-z0-9_-]{1,120}',subject):raise ValueError('subject')
    prefix='FSP_REGISTRY' if provider=='fsp' else 'DREAMJOB_PARTNER'
    endpoint=os.getenv(prefix+'_URL','').rstrip('/');token=secret(prefix+'_TOKEN','')
    if not endpoint or not token:return {'provider':provider,'status':'not_connected','value':None,'ranking_effect':0,'contract':VERSION}
    url=urlsplit(endpoint)
    if url.scheme!='https' or not url.hostname or url.username:raise ValueError('partner_https')
    # The operator-controlled partner gateway translates the vendor's agreement
    # into this versioned contract. It is not a guessed official vendor API.
    async with httpx.AsyncClient(trust_env=False,timeout=10,follow_redirects=False) as client:
        async with client.stream('GET',endpoint+'/'+subject,headers={'Authorization':'Bearer '+token,'Accept':'application/json'}) as r:
            if r.status_code in (404,429,503):return {'provider':provider,'status':'temporarily_unavailable','value':None,'ranking_effect':0}
            r.raise_for_status();raw=bytearray()
            async for chunk in r.aiter_bytes():
                raw.extend(chunk)
                if len(raw)>128000:raise ValueError('provider_response_limit')
    value=normalize(provider,json.loads(raw))
    return {'provider':provider,'status':'verified','value':value,'contract':VERSION,'source':'authorized-partner-gateway'}
