"""Initialize an isolated PostgreSQL cluster and application credentials."""
from pathlib import Path
import os,subprocess,secrets,time
import psycopg
from psycopg import sql
ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/'runtime';RUNTIME.mkdir(exist_ok=True)
BIN=ROOT/'.tools/postgres17/pgsql/bin'
CREATE_NO_WINDOW=getattr(subprocess,'CREATE_NO_WINDOW',0)
def run(args):
    subprocess.run([str(x) for x in args],check=True,creationflags=CREATE_NO_WINDOW)
def main():
    cluster=RUNTIME/'postgres'
    envpath=ROOT/'.env'
    if not envpath.exists():
        app_password=secrets.token_urlsafe(32)
        envpath.write_text(f'DATABASE_URL=postgresql://fsp_app:{app_password}@127.0.0.1:55432/fsp_trajectory\nFSP_DEMO_MODE=true\nBIND_ADDR=127.0.0.1:80\nBASE_URL=http://127.0.0.1\nSTORAGE_DIR=runtime/storage\nOLLAMA_URL=http://127.0.0.1:11434\nOLLAMA_MODEL=qwen3:8b\nFSP_REQUIRE_GPU=true\nFSP_GPU_MIN_OFFLOAD_PERCENT=100\nFSP_FORECAST_URL=http://127.0.0.1:8090\nDOCUMENT_WORKERS=1\nTESSERACT_CMD=C:/Program Files/Tesseract-OCR/tesseract.exe\n',encoding='utf-8')
    else:
        from urllib.parse import urlparse
        env=dict(line.split('=',1) for line in envpath.read_text().splitlines() if '=' in line)
        app_password=urlparse(env['DATABASE_URL']).password
    admin_file=RUNTIME/'postgres-admin.secret'
    if not admin_file.exists():admin_file.write_text(secrets.token_urlsafe(32),encoding='ascii')
    admin_password=admin_file.read_text().strip()
    if not (cluster/'PG_VERSION').exists():
        run([BIN/'initdb.exe','-D',cluster,'-U','fsp_admin','--encoding=UTF8','--locale=C','--auth=scram-sha-256',f'--pwfile={admin_file}'])
    status=subprocess.run([str(BIN/'pg_ctl.exe'),'-D',str(cluster),'status'],capture_output=True,creationflags=CREATE_NO_WINDOW)
    if status.returncode!=0:
        run([BIN/'pg_ctl.exe','-D',cluster,'-l',RUNTIME/'postgres.log','-o','-p 55432 -h 127.0.0.1 -c shared_buffers=128MB -c max_connections=60','start'])
    with psycopg.connect(host='127.0.0.1',port=55432,user='fsp_admin',password=admin_password,dbname='postgres',autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname='fsp_app'").fetchone():
            conn.execute(sql.SQL('CREATE ROLE fsp_app LOGIN PASSWORD {}').format(sql.Literal(app_password)))
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname='fsp_trajectory'").fetchone():
            conn.execute('CREATE DATABASE fsp_trajectory OWNER fsp_app')
    print('PostgreSQL ready at 127.0.0.1:55432. Credentials stored only in .env and runtime secrets.')
if __name__=='__main__':main()
