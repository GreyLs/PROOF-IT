"""Offline application backup, isolated restore verification; never overwrite the live DB."""
from pathlib import Path
import os,subprocess,urllib.request,datetime,uuid,shutil,json,hashlib,psutil
import psycopg
from psycopg import sql
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[1];load_dotenv(ROOT/'.env')
binary=(ROOT/'target/release/fsp-trajectory.exe').resolve()
for process in psutil.process_iter(['exe','cwd','cmdline']):
    try:
        own=process.info['cwd'] and Path(process.info['cwd']).resolve()==ROOT
        if own and ((process.info['exe'] and Path(process.info['exe']).resolve()==binary) or 'worker.main' in (process.info['cmdline']or[])):
            raise SystemExit('Stop only this checkout API and document worker before a consistent backup.')
    except (psutil.Error,OSError):pass
folder=ROOT/'runtime/backups'/datetime.datetime.now().strftime('%Y%m%d-%H%M%S');folder.mkdir(parents=True)
admin=(ROOT/'runtime/postgres-admin.secret').read_text().strip()
env={**os.environ,'PGPASSWORD':admin};bin=ROOT/'.tools/postgres17/pgsql/bin'
flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
subprocess.run([str(bin/'pg_dump.exe'),'-h','127.0.0.1','-p','55432','-U','fsp_admin','-d','fsp_trajectory','-Fc','--no-owner','-f',str(folder/'database.dump')],env=env,check=True,creationflags=flags)
shutil.copytree(ROOT/'runtime/storage',folder/'storage')
test_db='fsp_restore_check_'+uuid.uuid4().hex[:12]
params=dict(host='127.0.0.1',port=55432,user='fsp_admin',password=admin)
tables=['users','candidates','companies','vacancies','invitations','assessments','documents','applications','micro_tasks','resume_profiles','qualification_tests','qualification_certificates','qualification_attempt_history','intelligence.jobs','intelligence.review_cases','intelligence.passports','intelligence.followups','intelligence.weekly_campaigns']
with psycopg.connect(**params,dbname='postgres',autocommit=True) as admin_conn:
    admin_conn.execute(sql.SQL('CREATE DATABASE {} OWNER fsp_app').format(sql.Identifier(test_db)))
    try:
        subprocess.run([str(bin/'pg_restore.exe'),'-h','127.0.0.1','-p','55432','-U','fsp_admin','-d',test_db,'--no-owner','--role=fsp_app','--exit-on-error',str(folder/'database.dump')],env=env,check=True,creationflags=flags)
        with psycopg.connect(**params,dbname='fsp_trajectory') as live,psycopg.connect(**params,dbname=test_db) as restored:
            counts={}
            for table in tables:
                query=sql.SQL("SELECT count(*),md5(string_agg(to_jsonb(t)::text,E'\\n' ORDER BY to_jsonb(t)::text)) FROM {} t").format(sql.Identifier(*table.split('.')))
                a=live.execute(query).fetchone();b=restored.execute(query).fetchone();assert a==b,(table,a[0],b[0]);counts[table]={'rows':b[0],'content_digest_matches':True}
        files=[]
        for src in (ROOT/'runtime/storage').rglob('*'):
            if src.is_file():
                relative=src.relative_to(ROOT/'runtime/storage');copy=folder/'storage'/relative
                assert hashlib.sha256(src.read_bytes()).digest()==hashlib.sha256(copy.read_bytes()).digest();files.append(str(relative))
        report={'restored_successfully':True,'tables':counts,'files_verified':len(files),'backup_directory':str(folder.relative_to(ROOT)),'original_database_unchanged':True}
        (ROOT/'validation/reports/current/backup-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
    finally:
        assert test_db.startswith('fsp_restore_check_') and len(test_db)==30
        admin_conn.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(test_db)))
