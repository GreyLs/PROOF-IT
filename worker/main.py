"""Durable PostgreSQL queue with bounded workers, retries, lease recovery and fencing."""
from pathlib import Path
import os,sys,time,uuid,json,subprocess,signal
import psycopg,httpx
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from dotenv import load_dotenv
from .config import database_url,secret
from .errors import MESSAGES,ProcessingFailure
ROOT=Path(__file__).resolve().parents[1]
load_dotenv(ROOT/'.env')
def main():
    token=secret('PROCESSOR_TOKEN','')
    if len(token)<32:raise SystemExit('Processor credentials are required; run scripts/start_local.py')
    worker_id=str(uuid.uuid4());stopping=False
    def stop(*_):
        nonlocal stopping;stopping=True
    signal.signal(signal.SIGINT,stop)
    if hasattr(signal,'SIGTERM'):signal.signal(signal.SIGTERM,stop)
    while not stopping:
        try:
            with psycopg.connect(database_url(),autocommit=True,row_factory=dict_row) as conn:
                try:
                    response=httpx.get(os.getenv('PROCESSOR_URL','http://127.0.0.1:8081').rstrip('/')+'/ready',headers={'Authorization':'Bearer '+token},timeout=5,trust_env=False)
                    ready=response.status_code==200
                except httpx.HTTPError:ready=False
                conn.execute("INSERT INTO system_meta(key,value) VALUES('document_worker',%s) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value",(Jsonb({'worker_id':worker_id,'heartbeat':time.time(),'model':os.getenv('OLLAMA_MODEL'),'status':'ready' if ready else 'processor_unavailable'}),))
                if not ready:
                    time.sleep(3)
                    continue
                conn.execute("UPDATE documents SET status=CASE WHEN attempts>=3 THEN 'failed' ELSE 'queued' END,error='Обработчик был перезапущен; задание восстановлено',worker_id=NULL,lease_until=NULL,next_attempt_at=now() WHERE status='processing' AND lease_until<now()")
                conn.execute("UPDATE qualification_tests SET generation_status='queued',status=CASE WHEN status='processing' THEN 'queued' ELSE status END,worker_id=NULL,lease_until=NULL,error=NULL,updated_at=now() WHERE generation_status='processing' AND lease_until<now()")
                job=conn.execute("""WITH picked AS(SELECT id FROM documents WHERE status='queued' AND next_attempt_at<=now() AND attempts<3 ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1)
                    UPDATE documents d SET status='processing',attempts=attempts+1,worker_id=%s,lease_until=now()+interval '6 minutes',progress=5,updated_at=now() FROM picked WHERE d.id=picked.id RETURNING d.id,d.attempts""",(worker_id,)).fetchone()
                if not job:
                    test=conn.execute("""WITH picked AS(SELECT id FROM qualification_tests WHERE generation_status='queued' AND available_at<=now()+interval '1 month' ORDER BY updated_at FOR UPDATE SKIP LOCKED LIMIT 1)
                        UPDATE qualification_tests q SET generation_status='processing',status=CASE WHEN status='queued' THEN 'processing' ELSE status END,worker_id=%s,lease_until=now()+interval '6 minutes',updated_at=now() FROM picked WHERE q.id=picked.id RETURNING q.id""",(worker_id,)).fetchone()
                    if not test:
                        time.sleep(1);continue
                    print(json.dumps({'event':'test_generation_started','id':test['id']}),flush=True)
                    try:
                        result=subprocess.run([sys.executable,'-m','worker.test_job',test['id'],worker_id],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=300,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                        if result.returncode:
                            detail=(result.stdout+' '+result.stderr).replace('\n',' ')[:500]
                            print(json.dumps({'event':'test_generation_child_error','id':test['id'],'detail':detail}),flush=True)
                            raise ProcessingFailure('processor_error')
                        print(json.dumps({'event':'test_generation_finished','id':test['id']}),flush=True)
                    except Exception as exc:
                        conn.execute("UPDATE qualification_tests SET generation_status='failed',status=CASE WHEN status IN ('queued','processing') THEN 'failed' ELSE status END,error='Не удалось подготовить тест. Повторите подготовку.',worker_id=NULL,lease_until=NULL,updated_at=now() WHERE id=%s AND worker_id=%s",(test['id'],worker_id))
                        print(json.dumps({'event':'test_generation_failed','id':test['id'],'error_type':type(exc).__name__}),flush=True)
                    continue
                print(json.dumps({'event':'job_started','id':job['id'],'attempt':job['attempts']}),flush=True)
                try:
                    result=subprocess.run([sys.executable,'-m','worker.process_job',job['id'],worker_id],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=300,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    if result.returncode:
                        code='processor_error'
                        for line in result.stdout.splitlines():
                            try:
                                event=json.loads(line)
                                if event.get('event')=='job_error' and event.get('code') in MESSAGES:code=event['code']
                            except (ValueError,AttributeError):pass
                        raise ProcessingFailure(code)
                    print(json.dumps({'event':'job_finished','id':job['id']}),flush=True)
                except Exception as exc:
                    state='failed' if job['attempts']>=3 else 'queued'
                    code=exc.code if isinstance(exc,ProcessingFailure) else ('processing_timeout' if isinstance(exc,subprocess.TimeoutExpired) else 'processor_error')
                    message=MESSAGES[code]
                    conn.execute("UPDATE documents SET status=%s,error=%s,lease_until=NULL,next_attempt_at=now()+interval '10 seconds',updated_at=now() WHERE id=%s AND worker_id=%s AND status='processing'",(state,message,job['id'],worker_id))
                    if state=='failed':
                        conn.execute("UPDATE candidates SET employment_check=employment_check || jsonb_build_object('status','failed','message','Сверка временно не завершена. Откройте документы и повторите обработку. Новое несоответствие не установлено.') WHERE employment_document_id=%s",(job['id'],))
                    print(json.dumps({'event':'job_failed','id':job['id'],'error_code':code}),flush=True)
        except psycopg.Error as exc:
            print(json.dumps({'event':'database_unavailable','error_type':type(exc).__name__}),flush=True);time.sleep(3)
if __name__=='__main__':main()
