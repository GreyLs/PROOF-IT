"""Verify imported private fixtures stay private, including direct profile URLs."""
from pathlib import Path
import csv,json,os
import httpx,psycopg
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[1];load_dotenv(ROOT/'.env')
with (ROOT/'data/candidates.csv').open(encoding='utf-8-sig',newline='') as f:
 rows=list(csv.DictReader(f))
private=[r['candidate_id'] for r in rows if r['profile_visibility']=='private']
account=json.loads((ROOT/'runtime/test-accounts.json').read_text(encoding='utf-8'))['employer']
with psycopg.connect(os.environ['DATABASE_URL']) as db:
 actual=db.execute("SELECT id FROM candidates WHERE id=ANY(%s) AND visibility='private' AND synthetic",(private,)).fetchall()
 assert len(actual)==len(private)==56
origin=os.environ['BASE_URL'].rstrip('/')
with httpx.Client(base_url=origin+'/api',headers={'Origin':origin},trust_env=False) as c:
 c.post('/auth/login',json={k:account[k] for k in ('email','password')}).raise_for_status()
 for cid in private:
  r=c.get('/candidates/'+cid);assert r.status_code==404,(cid,r.status_code)
report={'passed':True,'private_csv_profiles':len(private),'private_db_profiles':len(actual),'direct_profile_urls_denied':len(private),'public_source_profiles':len(rows)-len(private)}
(ROOT/'validation/reports/current/fixture-privacy-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
