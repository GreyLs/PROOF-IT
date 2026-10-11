"""Opt-in public GitHub evidence. Fixed origins, bounded reads, no code execution."""
import hashlib
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit
import httpx
from worker.config import secret
from intelligence.role_matrix import matrix

VERSION='github-evidence-1.0.0'
API='https://api.github.com'
NAME=re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\Z')
LOGIN=re.compile(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}\Z')

def pr_reference(url):
    if not isinstance(url,str) or len(url)>300:raise ValueError('pr_url')
    parsed=urlsplit(url)
    if parsed.scheme!='https' or parsed.netloc!='github.com' or parsed.query or parsed.fragment or parsed.username:raise ValueError('github_origin')
    match=re.fullmatch(r'/([^/]+)/([^/]+)/pull/([1-9][0-9]{0,8})/?',parsed.path)
    if not match or not all(NAME.fullmatch(x) and x not in ('.','..') for x in match.groups()[:2]):raise ValueError('pr_path')
    return match[1],match[2],int(match[3])

def redacted(text,limit=4000):
    text=str(text or '')[:limit]
    text=re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}','[email omitted]',text)
    return text

class PublicClient:
    def __init__(self,transport=None):
        self.transport=transport
        self.rates=[]
    async def get(self,path,params=None):
        return await self.request('GET',path,params=params)
    async def request(self,method,path,params=None,body=None):
        if not path.startswith('/') or '?' in path or '#' in path:raise ValueError('api_path')
        headers={'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'Proofit-OptIn-Evidence/1.0'}
        token=secret('GITHUB_PUBLIC_TOKEN','')
        if token:headers['Authorization']='Bearer '+token
        async with httpx.AsyncClient(timeout=12,follow_redirects=False,trust_env=False,transport=self.transport) as client:
            async with client.stream(method,API+path,params=params,json=body,headers=headers) as response:
                self.rates.append({k:response.headers.get(k) for k in ('x-ratelimit-limit','x-ratelimit-remaining','x-ratelimit-reset','retry-after')})
                if response.status_code in (403,429):raise ValueError('github_rate_or_access_limit')
                if not response.is_success:raise ValueError('github_unavailable_or_not_public')
                body=bytearray()
                async for chunk in response.aiter_bytes():
                    if len(body)+len(chunk)>1500000:raise ValueError('github_body_limit')
                    body.extend(chunk)
        return json.loads(body)

async def fetch_repository(payload,client=None):
    name=payload.get('repository','')
    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}',name):raise ValueError('repository')
    owner,repo=name.split('/');client=client or PublicClient();base='/repos/'+name
    repository=await client.get(base)
    if repository.get('private') is not False or repository.get('visibility','public')!='public':raise ValueError('public_repository_required')
    commits=await client.get(base+'/commits',{'per_page':30})
    prs=await client.get(base+'/pulls',{'state':'all','sort':'updated','per_page':30})
    discussions={'status':'token_required','items':[],'complete':False}
    if secret('GITHUB_PUBLIC_TOKEN',''):
        query='query($owner:String!,$name:String!){repository(owner:$owner,name:$name){isPrivate discussions(first:10,orderBy:{field:UPDATED_AT,direction:DESC}){nodes{number title url createdAt comments(first:10){nodes{bodyText createdAt} pageInfo{hasNextPage}}} pageInfo{hasNextPage}}}}'
        try:
            response=await client.request('POST','/graphql',body={'query':query,'variables':{'owner':owner,'name':repo}})
            data=response.get('data',{}).get('repository')
            if response.get('errors') or not data or data.get('isPrivate') is not False:raise ValueError('github_discussions_access')
            connection=data['discussions']
            discussions={'status':'connected','items':[{'number':d['number'],'title':redacted(d['title'],250),'url':d['url'],
                         'comments':[{'body':redacted(c['bodyText'],1000),'created_at':c['createdAt']} for c in d['comments']['nodes']],
                         'comments_complete':not d['comments']['pageInfo']['hasNextPage']} for d in connection['nodes']],
                         'complete':not connection['pageInfo']['hasNextPage']}
        except ValueError:
            discussions={'status':'access_or_feature_unavailable','items':[],'complete':False}
    return {'version':VERSION,'repository':name,'url':'https://github.com/'+name,
            'commits':[{'sha':c['sha'],'message':redacted(c.get('commit',{}).get('message'),500),
                        'author_github_id':(c.get('author') or {}).get('id')} for c in commits[:30]],
            'pull_requests':[{'number':p['number'],'title':redacted(p.get('title'),250),'url':f'https://github.com/{name}/pull/{p["number"]}'} for p in prs[:30]],
            'repository_discussions':discussions,'coverage':'first 30 recent commits and 30 updated PRs; bounded Discussions GraphQL',
            'public_only':True,'code_executed':False,'rate_limits':client.rates}

async def fetch_profile(payload,client=None):
    login=payload['login']
    if not isinstance(login,str) or not LOGIN.fullmatch(login):raise ValueError('login')
    client=client or PublicClient()
    user=await client.get('/users/'+login)
    if user.get('type')!='User' or not isinstance(user.get('id'),int):raise ValueError('github_person')
    repos=await client.get('/users/'+login+'/repos',{'type':'owner','sort':'updated','per_page':30})
    return {'version':VERSION,'github_id':user['id'],'login':user['login'],
            'repositories':[{'name':r['name'],'full_name':r['full_name'],'url':r['html_url'],
                             'language':r.get('language'),'fork':r.get('fork',False),'updated_at':r.get('updated_at')}
                            for r in repos if r.get('private') is False],
            'coverage':'first 30 owner repositories; not exhaustive contribution history',
            'ownership_verified':False,'public_profile_is_not_authorship':True,'rate_limits':client.rates}

async def verify_gist(payload,client=None):
    gist_id=payload['gist_id']
    if not isinstance(gist_id,str) or not re.fullmatch(r'[a-fA-F0-9]{12,40}',gist_id):raise ValueError('gist_id')
    client=client or PublicClient();gist=await client.get('/gists/'+gist_id)
    if gist.get('public') is not True:raise ValueError('public_gist_required')
    item=gist.get('files',{}).get('proofit-claim.txt',{})
    nonce=item.get('content','').strip()
    if item.get('truncated') or not re.fullmatch(r'[a-f0-9]{64}',nonce):raise ValueError('claim_file')
    owner=gist.get('owner',{})
    if not isinstance(owner.get('id'),int) or not LOGIN.fullmatch(owner.get('login','')):raise ValueError('gist_owner')
    return {'github_id':owner['id'],'login':owner['login'],'nonce_hash':hashlib.sha256(nonce.encode()).hexdigest(),
            'proof_url':'https://gist.github.com/'+owner['login']+'/'+gist_id,'binding_kind':'one-time-public-gist-control'}

def questions(snapshot,specialization):
    rubric=matrix({'specialization':specialization})
    if not rubric['supported']:raise ValueError('coding_role_not_supported')
    files=[file for file in snapshot['files'] if file.get('patch')]
    if not files:raise ValueError('no_text_diff_available')
    output=[]
    for index,criterion in enumerate(rubric['criteria']):
        file=files[index%len(files)];patch=file['patch'];hunk=next((line for line in patch.splitlines() if line.startswith('@@')),'diff excerpt')
        added=[line[1:] for line in patch.splitlines() if line.startswith('+') and not line.startswith('+++')]
        excerpt='\n'.join(added[:8])[:900] or patch[:900]
        bound=f"{file['filename']} · {hunk}"
        question_id=hashlib.sha256((snapshot['digest']+criterion['id']+bound).encode()).hexdigest()[:24]
        output.append({'id':question_id,'criterion':criterion['id'],'file':file['filename'],'hunk':hunk,
                       'artifact_digest':snapshot['digest'],'head_sha':snapshot['head_sha'],'code_excerpt':excerpt,
                       'prompt':f"{bound}. {criterion['name']}: {criterion['observable']}. Какие конкретно строки изменили лично вы, почему и как проверили результат? Назовите альтернативу и ограничение решения."})
    return output

async def fetch_pr(payload,client=None):
    owner,repo,number=pr_reference(payload['url']);client=client or PublicClient()
    base='/repos/'+owner+'/'+repo
    repository=await client.get(base)
    if repository.get('private') is not False or repository.get('visibility','public')!='public':raise ValueError('public_repository_required')
    pr=await client.get(base+'/pulls/'+str(number))
    head=pr.get('head',{}).get('sha','')
    if not re.fullmatch(r'[a-f0-9]{40}',head):raise ValueError('head_sha')
    files=await client.get(base+'/pulls/'+str(number)+'/files',{'per_page':50})
    commits=await client.get(base+'/pulls/'+str(number)+'/commits',{'per_page':50})
    comments=await client.get(base+'/issues/'+str(number)+'/comments',{'per_page':20})
    reviews=await client.get(base+'/pulls/'+str(number)+'/reviews',{'per_page':20})
    inline=await client.get(base+'/pulls/'+str(number)+'/comments',{'per_page':20})
    # Re-read mutable PR metadata after paged endpoints to detect a moving head.
    fresh=await client.get(base+'/pulls/'+str(number))
    if fresh.get('head',{}).get('sha')!=head:raise ValueError('pr_changed_during_snapshot')
    snapshot={'version':VERSION,'url':f'https://github.com/{owner}/{repo}/pull/{number}',
              'repository':owner+'/'+repo,'number':number,'head_sha':head,'title':redacted(pr.get('title'),250),
              'author_github_id':pr.get('user',{}).get('id'),'author_login':pr.get('user',{}).get('login'),
              'files':[{'filename':redacted(f['filename'],300),'sha':f.get('sha'),'status':f.get('status'),
                        'additions':f.get('additions',0),'deletions':f.get('deletions',0),'patch':str(f.get('patch',''))[:16000]} for f in files[:50]],
              'commits':[{'sha':c['sha'],'author_github_id':(c.get('author') or {}).get('id'),
                          'message':redacted(c.get('commit',{}).get('message'),500)} for c in commits[:50]],
              'discussion':[{'id':c['id'],'url':c.get('html_url'),'body':redacted(c.get('body'),1000),
                             'kind':kind,'created_at':c.get('created_at')}
                            for kind,items in [('pr-conversation',comments),('review',reviews),('inline-review',inline)] for c in items[:20]],
              'coverage':{'files_received':len(files),'files_total':pr.get('changed_files'),
                          'commits_received':len(commits),'commits_total':pr.get('commits'),
                          'files_complete':len(files)==pr.get('changed_files'),
                          'discussions_complete':len(comments)<20 and len(reviews)<20 and len(inline)<20,
                          'repository_discussions':'GraphQL authorization required; PR discussion retrieved via REST'},
              'fetched_at':datetime.now(timezone.utc).isoformat(),'code_executed':False,
              'personal_contact_fields_collected':False}
    canonical={k:v for k,v in snapshot.items() if k not in ('fetched_at','rate_limits')}
    snapshot['digest']=hashlib.sha256(json.dumps(canonical,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    snapshot['questions']=questions(snapshot,payload['specialization']);snapshot['rate_limits']=client.rates
    return snapshot

async def operation(payload):
    kind=payload['operation']
    if kind=='github_profile':return await fetch_profile(payload)
    if kind=='github_repository':return await fetch_repository(payload)
    if kind=='github_verify_gist':return await verify_gist(payload)
    if kind=='github_pr':return await fetch_pr(payload)
    if kind=='github_head':
        owner,repo,number=pr_reference(payload['url']);client=PublicClient()
        repository=await client.get('/repos/'+owner+'/'+repo)
        if repository.get('private') is not False or repository.get('visibility','public')!='public':raise ValueError('public_repository_required')
        current=await client.get('/repos/'+owner+'/'+repo+'/pulls/'+str(number))
        return {'head_sha':current.get('head',{}).get('sha')}
    raise ValueError('github_operation')
