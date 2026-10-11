"""Private, bounded operational collector; never emits application records or secrets."""
from __future__ import annotations
from scripts.private_runtime import private_file
import concurrent.futures
import hmac
import json
import math
import os
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import psutil
import psycopg
from dotenv import dotenv_values
from prometheus_client import CollectorRegistry, Histogram, generate_latest
from prometheus_client.core import GaugeMetricFamily, CounterMetricFamily

ROOT = Path(__file__).resolve().parents[1]
SERVICES = {'gateway': (1717, '/api/health'), 'identity': (8082, '/api/health'),
            'talent': (8083, '/api/health'), 'recruitment': (8084, '/api/health'),
            'documents': (8085, '/api/health'), 'integrations': (8086, '/api/health'),
            'platform': (8087, '/api/health'), 'intelligence': (8088, '/api/health'),
            'cpu': (8092, '/health')}
COUNTERS = {'operations': 'operations_total', 'errors': 'errors_total',
            'cache_hits': 'cache_hits_total', 'duration_seconds': 'processing_seconds_total'}
REGISTRY = CollectorRegistry()
LATENCY = Histogram('proofit_health_probe_duration_seconds', 'Synthetic readiness probe latency, NOT user API latency',
                    ['service'], buckets=(.005, .01, .025, .05, .1, .25, .5, 1, 2, 4), registry=REGISTRY)

def fetch(port, path, host):
    request = urllib.request.Request(f'http://127.0.0.1:{port}{path}', headers={'Host': host})
    # Ignore proxy environment; do not follow redirects outside the fixed loopback target.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args):
            return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=3) as response:
        body = response.read(65537)
        if len(body) > 65536 or response.status != 200:
            raise ValueError('invalid monitoring response')
        return body

def parse_counters(body):
    result = {}
    for line in body.decode('ascii').splitlines():
        parts = line.split()
        if len(parts) == 2:
            for source, target in COUNTERS.items():
                if parts[0] == 'proofit_intelligence_' + source:
                    value = float(parts[1])
                    if not math.isfinite(value) or value < 0:
                        raise ValueError('invalid cumulative counter')
                    result[target] = value
    if len(result) != len(COUNTERS):
        raise ValueError('missing native counters')
    return result

class Collector:
    def __init__(self, host, database_url=None):
        self.host, self.database_url = host, database_url
        self.lock = threading.Lock()
        self.snapshot = {}
        self.started = time.time()
        psutil.cpu_percent()
        for service in SERVICES:
            LATENCY.labels(service)

    def probe(self, item):
        name, (port, path) = item
        started = time.perf_counter()
        try:
            payload = json.loads(fetch(port, path, self.host))
            success = int(payload.get('status') == 'ok')
        except Exception:
            success = 0
        LATENCY.labels(name).observe(time.perf_counter() - started)
        return name, success

    def update(self):
        started = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=9) as pool:
            probes = dict(pool.map(self.probe, SERVICES.items()))
        state = {'services': probes, 'cpu_percent': psutil.cpu_percent(),
                 'memory_available_bytes': psutil.virtual_memory().available,
                 'memory_total_bytes': psutil.virtual_memory().total,
                 'disk_free_bytes': psutil.disk_usage(str(ROOT)).free,
                 'disk_total_bytes': psutil.disk_usage(str(ROOT)).total,
                 'cpu_metrics_up': 0, 'database_enabled': int(bool(self.database_url)), 'database_up': 0}
        try:
            state['native'] = parse_counters(fetch(8092, '/metrics', self.host))
            state['cpu_metrics_up'] = 1
        except Exception:
            pass  # Omit stale counters; expose collector failure separately.
        if self.database_url:
            try:
                with psycopg.connect(self.database_url, connect_timeout=3,
                                     options='-c default_transaction_read_only=on -c statement_timeout=2000 -c lock_timeout=1000') as db:
                    stats = db.execute("SELECT numbackends,xact_commit,xact_rollback,blks_hit,blks_read,deadlocks FROM pg_stat_database WHERE datname=current_database()").fetchone()
                    maximum = db.execute('SHOW max_connections').fetchone()[0]
                    state['database'] = dict(zip(('connections', 'commits_total', 'rollbacks_total', 'cache_hits_total', 'blocks_read_total', 'deadlocks_total'), stats))
                    state['database']['max_connections'] = int(maximum)
                    state['database']['cluster_connections'] = db.execute('SELECT count(*) FROM pg_stat_activity').fetchone()[0]
                    state['database_up'] = 1
            except Exception:
                pass  # No connection string, exception text or SQL payload in metrics/logs.
        for name in SERVICES:
            file = ROOT / 'runtime' / ('intelligence-engine.pid' if name == 'cpu' else f'api-{name}.pid')
            try:
                process = psutil.Process(int(file.read_text().strip()))
                # PID files can be reused; accept only the expected binary/interpreter.
                expected = 'python' if name == 'cpu' else 'fsp-trajectory'
                if expected not in process.name().lower():
                    continue
                state.setdefault('processes', {})[name] = (process.memory_info().rss, sum(process.cpu_times()[:2]))
            except (OSError, ValueError, psutil.Error):
                pass
        state['collected_at'] = time.time()
        state['duration'] = time.perf_counter() - started
        with self.lock:
            self.snapshot = state

    def collect(self):
        with self.lock:
            state = dict(self.snapshot)
        def gauge(name, help_text, value):
            return GaugeMetricFamily('proofit_' + name, help_text, value=value)
        yield gauge('exporter_start_time_seconds', 'Exporter process start timestamp', self.started)
        yield gauge('collection_last_success_timestamp_seconds', 'Last completed collection, including explicit failed target statuses', state.get('collected_at', 0))
        yield gauge('collection_duration_seconds', 'Last collection duration', state.get('duration', 0))
        targets = GaugeMetricFamily('proofit_service_up', 'Readiness probe success; not full workflow readiness', labels=['service'])
        for name in SERVICES:
            targets.add_metric([name], state.get('services', {}).get(name, 0))
        yield targets
        for name in ('cpu_percent', 'memory_available_bytes', 'memory_total_bytes', 'disk_free_bytes', 'disk_total_bytes', 'cpu_metrics_up', 'database_enabled', 'database_up'):
            if name in state:
                yield gauge('host_' + name if name in ('cpu_percent', 'memory_available_bytes', 'memory_total_bytes', 'disk_free_bytes', 'disk_total_bytes') else name, name.replace('_', ' '), state[name])
        for name, value in state.get('native', {}).items():
            metric = CounterMetricFamily('proofit_compute_' + name, 'Native CPU service cumulative counter')
            metric.add_metric([], value)
            yield metric
        for name, value in state.get('database', {}).items():
            if name.endswith('_total'):
                metric = CounterMetricFamily('proofit_postgres_' + name, 'PostgreSQL database cumulative statistic')
                metric.add_metric([], value)
                yield metric
            else:
                yield gauge('postgres_' + name, 'PostgreSQL connection capacity statistic', value)
        for index, metric_name in enumerate(('resident_memory_bytes', 'cpu_seconds_total')):
            cls = GaugeMetricFamily if index == 0 else CounterMetricFamily
            metric = cls('proofit_process_' + metric_name, 'Native process resource usage', labels=['service'])
            for name, values in state.get('processes', {}).items():
                metric.add_metric([name], values[index])
            yield metric

def authorized(header, token):
    return bool(token and hmac.compare_digest((header or '').encode('utf-8'), ('Bearer ' + token).encode('utf-8')))

def main():
    cfg = dotenv_values(ROOT / '.env')
    public = private_file('public-settings.json')
    if public.exists():
        cfg.update(json.loads(public.read_text(encoding='utf-8')))
    token = (ROOT / 'runtime/monitoring/exporter-token').read_text().strip()
    if len(token) < 32:
        raise SystemExit('Monitoring token must contain at least 32 characters')
    host = urlsplit(cfg.get('BASE_URL', 'http://localhost:1717')).netloc
    # Deliberately opt-in; no automatic use of privileged application DB credentials.
    collector = Collector(host, os.getenv('MONITORING_DATABASE_URL'))
    REGISTRY.register(collector)
    collector.update()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if not authorized(self.headers.get('Authorization'), token):
                self.send_response(401); self.end_headers(); return
            if self.path != '/metrics':
                self.send_response(404); self.end_headers(); return
            body = generate_latest(REGISTRY)
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; version=0.0.4; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers(); self.wfile.write(body)
        def log_message(self, *_):
            pass
    server = ThreadingHTTPServer((os.getenv('MONITORING_BIND', '127.0.0.1'), 9198), Handler)
    def refresh():
        while True:
            time.sleep(10)
            try:
                collector.update()
            except Exception:
                pass  # Timestamp detects stalled collection, without disclosing exception data.
    threading.Thread(target=refresh, daemon=True).start()
    server.serve_forever()

if __name__ == '__main__':
    main()
