"""Trusted queue controller. Parsing happens in a separate, credential-free service."""
from pathlib import Path
import os
import sys
import json

import httpx
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from dotenv import load_dotenv
from .config import database_url, secret
from .errors import ProcessingFailure

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')


def main():
    job_id, worker_id = sys.argv[1:3]
    token = secret('PROCESSOR_TOKEN', '')
    endpoint = os.environ.get('PROCESSOR_URL', 'http://127.0.0.1:8081')
    if len(token) < 32:
        raise ProcessingFailure('processor_configuration')
    with psycopg.connect(database_url(), autocommit=True, row_factory=dict_row) as conn:
        job = conn.execute("SELECT * FROM documents WHERE id=%s AND worker_id=%s AND status='processing'", (job_id, worker_id)).fetchone()
        if not job:
            return
        storage = Path(os.getenv('STORAGE_DIR', str(ROOT / 'runtime/storage'))).resolve()
        path = (storage / job['storage_key']).resolve()
        if not path.is_relative_to(storage) or path.stat().st_size > 20 * 1024**2:
            raise ValueError('Invalid storage object')
        with httpx.Client(timeout=httpx.Timeout(300, connect=5), follow_redirects=False, trust_env=False) as client:
            with path.open('rb') as source:
                with client.stream('POST', endpoint.rstrip('/') + '/process', content=source,
                                   headers={'Authorization': 'Bearer ' + token, 'X-Document-Kind': job['kind']}) as response:
                    if response.status_code != 200:
                        code = {401:'processor_configuration',403:'processor_configuration',503:'processor_busy',504:'processing_timeout',422:'invalid_document',415:'invalid_document'}.get(response.status_code,'processor_error')
                        raise ProcessingFailure(code)
                    payload = bytearray()
                    for chunk in response.iter_bytes():
                        if len(payload) + len(chunk) > 4 * 1024**2:
                            raise ValueError('Processor output limit')
                        payload.extend(chunk)
        if job['kind'] == 'profile_export':
            if not payload.startswith(b'%PDF-'):
                raise ValueError('Invalid export')
            key = job_id + '-profile.pdf'
            (storage / key).write_bytes(payload)
            result, status = {'output_key': key, 'engine': 'ReportLab', 'fields': {}}, 'completed'
        else:
            result, status = json.loads(payload), 'review'
            if not isinstance(result, dict) or not isinstance(result.get('fields'), dict) or not result.get('requires_review'):
                raise ValueError('Invalid extraction contract')
            result.pop('output_key', None)
        if job['kind']=='employment':
            profile=conn.execute('SELECT id,full_name,about,consent_processing FROM candidates WHERE employment_document_id=%s',(job_id,)).fetchone()
            if profile and profile['consent_processing']:
                with httpx.Client(timeout=280,trust_env=False,follow_redirects=False) as client:
                    comparison=client.post(endpoint.rstrip('/')+'/process',headers={'Authorization':'Bearer '+token,'X-Document-Kind':'employment_compare'},json={'book':result['book'],'profile':{'full_name':profile['full_name'],'about':profile['about']}})
                    comparison.raise_for_status()
                    check=comparison.json()
                if check.get('status') not in ('aligned','mismatch','insufficient','invalid_document'):
                    raise ValueError('Invalid employment comparison')
                check['document_id']=job_id
                result['employment_check']=check
                with conn.transaction():
                    updated=conn.execute("UPDATE candidates SET employment_check=%s,employment_blocked=CASE WHEN %s='mismatch' THEN true WHEN %s='aligned' THEN false ELSE employment_blocked END WHERE id=%s AND employment_document_id=%s AND consent_processing AND full_name=%s AND about=%s AND EXISTS(SELECT 1 FROM documents WHERE id=%s AND worker_id=%s AND status='processing' AND lease_until>now()) RETURNING id",(Jsonb(check),check['status'],check['status'],profile['id'],job_id,profile['full_name'],profile['about'],job_id,worker_id)).fetchone()
                    if not updated:
                        conn.execute("UPDATE documents SET status='queued',attempts=0,lease_until=NULL,next_attempt_at=now(),result=%s WHERE id=%s AND worker_id=%s AND status='processing'",(Jsonb(result),job_id,worker_id))
                        return
            else:
                result['employment_check']={'status':'superseded','message':'Выбрана другая выписка или отозвано согласие на обработку.'}
            status='completed'
            payload=json.dumps(result,ensure_ascii=False).encode('utf-8')
        elif job['kind']=='resume':
            # A document can be uploaded quickly; the role-specific test is queued
            # once the parser has extracted the resume header. Generation itself is
            # a separate GPU task so this upload path remains responsive.
            fields=result.get('fields') or {}
            if not fields and isinstance(result.get('profiles'),list) and len(result['profiles'])==1:
                fields=result['profiles'][0].get('fields') or {}
            profile=conn.execute("SELECT r.id,r.candidate_id,r.target_position,r.specialization,r.declared_grade,r.experience_years,r.skills,r.about,r.expected_salary,r.work_format FROM resume_profiles r WHERE r.document_id=%s FOR UPDATE",(job_id,)).fetchone()
            if profile:
                title=str(fields.get('title') or profile['target_position']).strip()[:250]
                spec=str(fields.get('specialization') or profile['specialization']).strip()
                grade=str(fields.get('grade') or profile['declared_grade']).strip()
                years=fields.get('experience_years') if isinstance(fields.get('experience_years'),(int,float)) else profile['experience_years']
                skills=fields.get('skills') if isinstance(fields.get('skills'),list) else profile['skills']
                about=str(fields.get('description') or profile['about'])[:15000]
                salary=fields.get('salary_to') if isinstance(fields.get('salary_to'),int) else profile['expected_salary']
                work=str(fields.get('work_format') or profile['work_format'])[:100]
                conn.execute("UPDATE resume_profiles SET target_position=%s,specialization=%s,declared_grade=CASE WHEN %s IN ('junior','middle','senior') THEN %s ELSE declared_grade END,experience_years=%s,skills=%s,about=%s,expected_salary=%s,work_format=%s,status=CASE WHEN visibility='employer_searchable' THEN 'published' ELSE 'draft' END,updated_at=now(),version=version+1 WHERE id=%s",(title,spec,grade,grade,years,skills,about,salary,work,profile['id']))
                # A fresh test is tied to the extracted target role. It is hidden
                # until generated and never exposes its answer key in the API.
                conn.execute("UPDATE qualification_tests SET status='queued',generation_status='queued',questions='[]',score=NULL,passed=NULL,attempts=0,available_at=now(),seed=md5(random()::text||clock_timestamp()::text),error=NULL,updated_at=now() WHERE resume_id=%s AND status NOT IN ('in_progress','passed')",(profile['id'],))
        conn.execute("UPDATE documents SET result=%s,result_bytes=%s,status=%s,progress=100,error=NULL,lease_until=NULL,updated_at=now() WHERE id=%s AND worker_id=%s AND status='processing'",
                     (Jsonb(result), len(payload), status, job_id, worker_id))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        code = exc.code if isinstance(exc, ProcessingFailure) else ('processing_timeout' if isinstance(exc,httpx.TimeoutException) else 'processor_unavailable' if isinstance(exc,httpx.TransportError) else 'processor_error')
        print(json.dumps({'event':'job_error','code':code}),flush=True)
        sys.exit(1)
