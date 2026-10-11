from pathlib import Path
import os,time,json,sys
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
load_dotenv(ROOT/'.env')
from worker.extraction import extract
reports=[]
for filename,kind in [('candidate-text.pdf','resume'),('candidate-scan.pdf','resume'),('candidate-scan.png','resume'),('vacancy-text.pdf','vacancy'),('injection-text.pdf','resume')]:
    t=time.perf_counter();r=extract(ROOT/'tests/fixtures'/filename,kind)
    if filename.startswith('candidate-'):
        assert r['fields']['email']=='alexey@example.test'
        assert r['fields']['salary_from']==180000 and r['fields']['salary_to']==240000
        assert {'Python','FastAPI','PostgreSQL','Docker'}<=set(r['fields']['skills'])
        assert r['fields']['grade']=='middle' and r['requires_review']
    if filename.startswith('vacancy-'):
        assert r['fields']['salary_from']==220000 and r['fields']['salary_to']==300000
    if filename.startswith('injection-'):
        assert r['fields']['grade'] is None and r['requires_review']
        assert 'confirmed_grade' not in r['fields']
    reports.append({'filename':filename,'engine':r['engine'],'elapsed_seconds':round(time.perf_counter()-t,2),'fields':r['fields'],'provenance':r['provenance'],'warnings':r['warnings'],'page_methods':[p['method'] for p in r['pages']]})
    print(json.dumps({k:reports[-1][k] for k in ['filename','engine','elapsed_seconds','page_methods']}),flush=True)
    (ROOT/'validation/reports/current/document-validation.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
print('Document checks saved')
