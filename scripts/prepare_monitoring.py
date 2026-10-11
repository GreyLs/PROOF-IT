"""Generate immutable provisioned dashboard and private first-launch secrets."""
import json
import secrets
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def dashboard():
    panels = []
    definitions = [
        ('Доступность доменов', 'proofit_service_up', 'stat', 'none', '1 = readiness OK; не подтверждает полный пользовательский сценарий.'),
        ('P95 readiness-проб', 'proofit:probe_latency_p95_seconds:5m', 'timeseries', 's', 'Только синтетические health-пробы, не задержка пользовательского API.'),
        ('Успешные вычисления / с', 'rate(proofit_compute_operations_total[5m])', 'timeseries', 'ops', 'Нативный счётчик CPU-сервиса, без cache hits.'),
        ('Ошибки вычислений', 'proofit:compute_error_ratio:5m', 'timeseries', 'percentunit', 'Ошибки / (операции + ошибки + cache hits); не все HTTP-отказы периметра.'),
        ('Попадания в кэш / с', 'rate(proofit_compute_cache_hits_total[5m])', 'timeseries', 'ops', 'Нативные cache hits; не считать как новые вычисления.'),
        ('CPU компьютера', 'proofit_host_cpu_percent / 100', 'timeseries', 'percentunit', 'Вся машина, включая посторонние процессы.'),
        ('Доступная оперативная память', 'proofit_host_memory_available_bytes', 'timeseries', 'bytes', 'Available RAM, не только свободные страницы.'),
        ('Свободное место на диске', 'proofit_host_disk_free_bytes', 'timeseries', 'bytes', 'Раздел, на котором расположен Proofit.'),
        ('Память процессов Proofit', 'proofit_process_resident_memory_bytes', 'timeseries', 'bytes', 'RSS отдельных native-процессов по проверенным PID-файлам.'),
        ('CPU процессов Proofit', 'rate(proofit_process_cpu_seconds_total[5m])', 'timeseries', 'none', 'Использование CPU в эквиваленте ядер, а не процент всей машины.'),
        ('Загрузка соединений PostgreSQL', 'proofit_postgres_cluster_connections / proofit_postgres_max_connections', 'timeseries', 'percentunit', 'Весь кластер / max_connections; статистика opt-in.'),
        ('PostgreSQL: cache hit ratio', 'rate(proofit_postgres_cache_hits_total[5m]) / clamp_min(rate(proofit_postgres_cache_hits_total[5m]) + rate(proofit_postgres_blocks_read_total[5m]), 0.001)', 'timeseries', 'percentunit', 'Буферный кэш выбранной БД; не оценка качества SQL или ОС cache.'),
        ('PostgreSQL: rollback / с', 'rate(proofit_postgres_rollbacks_total[5m])', 'timeseries', 'ops', 'Rollback не обязательно является ошибкой приложения.'),
        ('Свежесть наблюдений', 'time() - proofit_collection_last_success_timestamp_seconds', 'stat', 's', 'Позволяет обнаружить живой exporter с остановленным сбором.'),
        ('Сборщики: готовность', 'label_replace(proofit_database_up,"collector","postgres","","") or label_replace(proofit_cpu_metrics_up,"collector","cpu","","")', 'stat', 'none', 'DB=0 при отключённом DB collector; проверяйте database_enabled.'),
        ('Активные предупреждения', 'ALERTS{alertstate="firing"}', 'table', 'none', 'Маршрутизация в Alertmanager; внешние уведомления подключаются оператором.'),
    ]
    for index, (title, expr, kind, unit, description) in enumerate(definitions):
        defaults = {'unit': unit, 'min': 0}
        if unit == 'percentunit':
            defaults['max'] = 1
        if index in (0, 14):
            defaults['mappings'] = [{'type': 'value', 'options': {'0': {'text': 'DOWN', 'color': 'red'}, '1': {'text': 'OK', 'color': 'green'}}}]
            defaults['thresholds'] = {'mode': 'absolute', 'steps': [{'color': 'red', 'value': None}, {'color': 'green', 'value': 1}]}
        legend = '{{service}}' if index in (0, 1, 8, 9) else ('{{collector}}' if index == 14 else title)
        panels.append({'id': index+1, 'title': title, 'description': description, 'type': kind,
                       'datasource': {'type': 'prometheus', 'uid': 'proofit-prometheus'},
                       'gridPos': {'x': (index % 2)*12, 'y': (index//2)*8, 'w': 12, 'h': 8},
                       'targets': [{'refId': 'A', 'expr': expr, 'legendFormat': legend}],
                       'fieldConfig': {'defaults': defaults, 'overrides': []},
                       'options': {'reduceOptions': {'calcs': ['lastNotNull'], 'fields': '', 'values': False}} if kind == 'stat' else {}})
    return {'uid': 'proofit-operations', 'title': 'Proofit · Operational Control', 'schemaVersion': 41,
            'version': 1, 'tags': ['proofit', 'operations', 'privacy'], 'timezone': 'browser',
            'editable': False, 'refresh': '15s', 'time': {'from': 'now-30m', 'to': 'now'}, 'panels': panels}

def main():
    folder = ROOT / 'runtime/monitoring'
    folder.mkdir(parents=True, exist_ok=True)
    for name in ('exporter-token', 'grafana-password'):
        path = folder / name
        if not path.exists():
            with path.open('x', encoding='ascii') as handle:
                handle.write(secrets.token_urlsafe(48))
    output = ROOT / 'deploy/monitoring/grafana/dashboards/proofit.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(dashboard(), ensure_ascii=False, indent=2), encoding='utf-8')
    print('Monitoring prepared: 16 panels; existing secrets preserved; no secrets printed.')

if __name__ == '__main__':
    main()
