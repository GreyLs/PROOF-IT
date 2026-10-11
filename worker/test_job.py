"""Credentialed controller for one queued qualification-test generation."""
from pathlib import Path
import json,os,sys
import httpx,psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from dotenv import load_dotenv
from .config import database_url,secret

ROOT=Path(__file__).resolve().parents[1];load_dotenv(ROOT/'.env')

def main():
    test_id,worker_id=sys.argv[1:3]
    with psycopg.connect(database_url(),autocommit=True,row_factory=dict_row) as conn:
        row=conn.execute("SELECT q.id,q.status,q.seed,r.id AS resume_id,r.target_position,r.specialization,r.declared_grade,r.experience_years,r.skills,r.about FROM qualification_tests q JOIN resume_profiles r ON r.id=q.resume_id WHERE q.id=%s AND q.worker_id=%s AND q.generation_status='processing'",(test_id,worker_id)).fetchone()
        if not row:
            # A lease must still belong to this process.  Treating a lost lease
            # as success would leave a test queued forever and cause duplicate
            # expensive generations.
            raise RuntimeError('qualification_job_lease_lost_before_generation')
        token=secret('PROCESSOR_TOKEN','')
        if len(token)<32:raise RuntimeError('processor token missing')
        resume={key:row[key] for key in ['resume_id','target_position','specialization','declared_grade','experience_years','skills','about']}
        with httpx.Client(timeout=280,trust_env=False,follow_redirects=False) as client:
            response=client.post(os.getenv('PROCESSOR_URL','http://127.0.0.1:8081').rstrip('/')+'/process',headers={'Authorization':'Bearer '+token,'X-Document-Kind':'qualification_generate'},json={'resume':resume,'seed':int(row['seed'][:8],16) if all(c in '0123456789abcdef' for c in row['seed'][:8].lower()) else 42})
            response.raise_for_status(); result=response.json()
        questions=result.get('questions')
        if not isinstance(result.get('contract'),dict) or result.get('version')!='certification-3.0.0':raise ValueError('invalid qualification contract')
        changed=conn.execute("UPDATE qualification_tests SET questions=%s,generation_status='ready',status=CASE WHEN status IN ('waiting_resume','queued','processing') THEN 'ready' ELSE status END,error=NULL,worker_id=NULL,lease_until=NULL,updated_at=now() WHERE id=%s AND worker_id=%s AND generation_status='processing' RETURNING id",(Jsonb(result),test_id,worker_id)).fetchone()
        if not changed:
            raise RuntimeError('qualification_job_lease_lost_before_commit')

if __name__=='__main__':
    try:main()
    except Exception as exc:
        try:
            with psycopg.connect(database_url(),autocommit=True) as conn:
                conn.execute("UPDATE qualification_tests SET generation_status='failed',status=CASE WHEN status IN ('waiting_resume','queued','processing') THEN 'failed' ELSE status END,error='Не удалось подготовить новый набор вопросов. Повторите подготовку.',worker_id=NULL,lease_until=NULL,updated_at=now() WHERE id=%s AND worker_id=%s",(sys.argv[1],sys.argv[2]))
        finally:
            print(json.dumps({'event':'test_job_error','type':type(exc).__name__,'detail':str(exc)[:300]}),flush=True);sys.exit(1)
