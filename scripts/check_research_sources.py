"""Read-only primary source reachability and bibliographic identity checks."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib,json,re,time
import httpx
from scripts.build_pdf_documentation import SOURCES
ROOT=Path(__file__).resolve().parents[1]
def check(s):
 key,author,year,title,url,kind,note=s
 item={'key':key,'author':author,'year':year,'title':title,'url':url,'class':kind}
 try:
  with httpx.Client(trust_env=False,timeout=12,follow_redirects=True,headers={'User-Agent':'ProofitResearchSourceVerifier/1.0'})as c:
   with c.stream('GET',url)as r:
    prefix=b''
    for block in r.iter_bytes():
     prefix+=block
     if len(prefix)>=65536:break
    text=prefix.decode('utf-8',errors='replace');match=re.search(r'<title[^>]*>(.*?)</title>',text,re.S|re.I)
    item.update(status=r.status_code,final_url=str(r.url),content_type=r.headers.get('content-type',''),prefix_sha256=hashlib.sha256(prefix).hexdigest(),page_title=re.sub(r'\s+',' ',match.group(1)).strip()if match else None)
 except httpx.HTTPError as e:item.update(error=type(e).__name__)
 return item
def main():
 with ThreadPoolExecutor(max_workers=6)as pool:items=list(pool.map(check,SOURCES))
 report={'checked_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'method':'Primary URL GET; bounded prefix, metadata only; HTTP blocking is distinguished from document absence. Primary bibliographic/content inspection is documented separately.','sources':items,'http_success':sum(x.get('status')==200 for x in items),'total':len(items)}
 out=ROOT/'validation/reports/current';out.mkdir(parents=True,exist_ok=True);(out/'research-sources.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'total':len(items),'http_success':report['http_success'],'exceptions':[{'key':x['key'],'status':x.get('status'),'error':x.get('error')}for x in items if x.get('status')!=200]}))
if __name__=='__main__':main()
