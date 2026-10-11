"""Launch native collector and isolated local monitoring containers, no app restart."""
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import urllib.request

import psycopg
from psycopg.conninfo import make_conninfo, conninfo_to_dict
from psycopg import sql
from dotenv import dotenv_values
from scripts.prepare_monitoring import main as prepare

ROOT = Path(__file__).resolve().parents[1]

def main():
    prepare()
    cfg = dotenv_values(ROOT / '.env')
    env = os.environ.copy()
    database_enabled = False
    # Explicit local-only bootstrap; production DBA uses deploy/monitoring/monitor-role.sql.
    if cfg.get('FSP_DEMO_MODE') == 'true' and cfg.get('DATABASE_URL'):
        password_file = ROOT / 'runtime/monitoring/database-password'
        if not password_file.exists():
            with password_file.open('x', encoding='ascii') as file:
                file.write(secrets.token_urlsafe(48))
        password = password_file.read_text()
        try:
            admin_dsn = cfg['DATABASE_URL']
            connection = conninfo_to_dict(admin_dsn)
            admin_file = ROOT / 'runtime/postgres-admin.secret'
            if connection.get('host') == '127.0.0.1' and connection.get('port') == '55432' and admin_file.exists():
                admin_dsn = make_conninfo(admin_dsn, user='fsp_admin', password=admin_file.read_text().strip())
            with psycopg.connect(admin_dsn, autocommit=True, connect_timeout=3) as db:
                exists = db.execute("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='proofit_monitor')").fetchone()[0]
                if not exists:
                    db.execute(sql.SQL('CREATE ROLE proofit_monitor LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD {}').format(sql.Literal(password)))
                    db.execute('GRANT pg_read_all_stats TO proofit_monitor')
                    db.execute('ALTER ROLE proofit_monitor SET default_transaction_read_only = on')
                    db.execute("ALTER ROLE proofit_monitor SET statement_timeout = '2s'")
                    db.execute("ALTER ROLE proofit_monitor SET lock_timeout = '1s'")
            dsn = make_conninfo(cfg['DATABASE_URL'], user='proofit_monitor', password=password)
            with psycopg.connect(dsn, connect_timeout=3) as db:
                db.execute('SELECT numbackends FROM pg_stat_database WHERE datname=current_database()').fetchone()
                if db.execute("SELECT has_table_privilege(current_user,'users','SELECT') OR has_table_privilege(current_user,'resume_profiles','SELECT')").fetchone()[0]:
                    raise RuntimeError('Monitor role must not read business tables')
            env['MONITORING_DATABASE_URL'] = dsn
            database_enabled = True
        except Exception:
            print('Dedicated database collector not activated; no application credentials used for monitoring.')
    token = (ROOT / 'runtime/monitoring/exporter-token').read_text().strip()
    running = False
    try:
        request = urllib.request.Request('http://127.0.0.1:9198/metrics', headers={'Authorization': 'Bearer ' + token})
        with urllib.request.urlopen(request, timeout=2) as response:
            running = response.status == 200
    except Exception:
        pass
    if not running:
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
        with (ROOT / 'runtime/monitoring/exporter.log').open('ab') as log:
            process = subprocess.Popen([sys.executable, '-m', 'scripts.monitoring_exporter'], cwd=ROOT,
                                       env=env, stdout=log, stderr=log, stdin=subprocess.DEVNULL, creationflags=flags)
        (ROOT / 'runtime/monitoring/exporter.pid').write_text(str(process.pid))
    docker = shutil.which('docker') or 'C:/Program Files/Docker/Docker/resources/bin/docker.exe'
    subprocess.run([docker, 'compose', '-f', 'deploy/monitoring/compose.yml', 'up', '-d'], cwd=ROOT, check=True)
    print(json.dumps({'grafana': 'http://localhost:3001', 'prometheus': 'http://localhost:9095',
                      'alertmanager': 'http://localhost:9096', 'database_bootstrap_verified': database_enabled,
                      'grafana_user': 'proofit-admin', 'password_file': 'runtime/monitoring/grafana-password'}))

if __name__ == '__main__':
    main()
