"""Read-only stack checks and private Grafana browser inspection."""
import hashlib
import json
import time
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright, expect
from prometheus_client.parser import text_string_to_metric_families
from dotenv import dotenv_values
import psycopg
from psycopg.conninfo import make_conninfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'validation/reports/current'

def main():
    checks = []
    def check(name, value):
        assert value, name
        checks.append(name)
    token = (ROOT / 'runtime/monitoring/exporter-token').read_text().strip()
    password = (ROOT / 'runtime/monitoring/grafana-password').read_text().strip()
    with httpx.Client(timeout=10, trust_env=False) as client:
        check('exporter_no_token_401', client.get('http://127.0.0.1:9198/metrics').status_code == 401)
        check('exporter_wrong_token_401', client.get('http://127.0.0.1:9198/metrics', headers={'Authorization': 'Bearer wrong'}).status_code == 401)
        response = client.get('http://127.0.0.1:9198/metrics', headers={'Authorization': 'Bearer ' + token})
        check('authenticated_exporter_200', response.status_code == 200)
        families = list(text_string_to_metric_families(response.text))
        check('valid_prometheus_exposition', len(families) > 20)
        check('no_secret_values_or_personal_labels', token not in response.text and password not in response.text and not any(word in response.text for word in ('candidate_id', 'vacancy_id', 'email', 'token', 'password')))
        targets = client.get('http://localhost:9095/api/v1/targets').json()['data']['activeTargets']
        check('prometheus_targets_up', len(targets) == 2 and all(target['health'] == 'up' for target in targets))
        results = client.get('http://localhost:9095/api/v1/query', params={'query': 'proofit_service_up'}).json()['data']['result']
        check('nine_live_domain_probes', len(results) == 9 and all(value['value'][1] == '1' for value in results))
        check('fresh_collection', time.time() - float(client.get('http://localhost:9095/api/v1/query', params={'query': 'proofit_collection_last_success_timestamp_seconds'}).json()['data']['result'][0]['value'][1]) < 45)
        check('database_live', client.get('http://localhost:9095/api/v1/query', params={'query': 'proofit_database_up'}).json()['data']['result'][0]['value'][1] == '1')
        grafana = client.get('http://localhost:3001/api/dashboards/uid/proofit-operations', auth=('proofit-admin', password))
        check('provisioned_grafana_dashboard', grafana.status_code == 200 and len(grafana.json()['dashboard']['panels']) == 16)
        errors = []
        for panel in grafana.json()['dashboard']['panels']:
            data = client.get('http://localhost:9095/api/v1/query', params={'query': panel['targets'][0]['expr']}).json()
            if data['status'] != 'success':
                errors.append(panel['id'])
        check('all_sixteen_promql_queries_valid', not errors)
        collectors = client.get('http://localhost:9095/api/v1/query', params={'query': grafana.json()['dashboard']['panels'][14]['targets'][0]['expr']}).json()['data']['result']
        check('both_collector_series_visible', {value['metric']['collector'] for value in collectors} == {'cpu', 'postgres'})
        check('alertmanager_ready', client.get('http://localhost:9096/-/ready').status_code == 200)
    cfg = dotenv_values(ROOT / '.env')
    dsn = make_conninfo(cfg['DATABASE_URL'], user='proofit_monitor', password=(ROOT / 'runtime/monitoring/database-password').read_text())
    with psycopg.connect(dsn) as db:
        check('monitor_role_no_business_select', not db.execute("SELECT has_table_privilege(current_user,'users','SELECT') OR has_table_privilege(current_user,'resume_profiles','SELECT')").fetchone()[0])
        check('monitor_role_read_only', db.execute('SHOW default_transaction_read_only').fetchone()[0] == 'on')
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 960})
        page.goto('http://localhost:3001/login')
        page.get_by_label('Email or username').fill('proofit-admin')
        page.get_by_label('Password', exact=True).fill(password)
        page.get_by_role('button', name='Log in', exact=True).click()
        page.wait_for_url(lambda url: '/login' not in url, timeout=30000)
        page.goto('http://localhost:3001/d/proofit-operations')
        expect(page.get_by_text('Доступность доменов', exact=True)).to_be_visible(timeout=30000)
        page.wait_for_timeout(6000)
        expect(page.get_by_text('Доступность доменов', exact=True)).to_be_visible()
        page.screenshot(path=str(OUT / 'monitoring-grafana.png'), full_page=False)
        check('grafana_browser_dashboard_visible', True)
        browser.close()
    report = {'passed': True, 'measured_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'checks': checks,
              'health_services': 9, 'dashboard_panels': 16, 'metric_families': len(families),
              'metric_samples': sum(len(family.samples) for family in families),
              'collection_duration_seconds': next(f.samples[0].value for f in families if f.name == 'proofit_collection_duration_seconds'),
              'llm_calls': 0, 'scope': 'operational stack and access control; no hiring-effectiveness or load claim'}
    (OUT / 'monitoring-live.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))

if __name__ == '__main__':
    main()
