import pytest
from prometheus_client import CollectorRegistry, generate_latest
from scripts.monitoring_exporter import Collector, authorized, parse_counters, SERVICES
from scripts.prepare_monitoring import dashboard

def test_token_gate():
    assert authorized('Bearer ' + 'a'*48, 'a'*48)
    assert not authorized(None, 'a'*48)
    assert not authorized('Bearer ' + 'b'*48, 'a'*48)
    assert not authorized('Bearer ', '')
    assert not authorized('Bearer недопустимый', 'a'*48)

def test_native_counter_allowlist():
    data = b'proofit_intelligence_operations 3\nproofit_intelligence_errors 1\nproofit_intelligence_cache_hits 2\nproofit_intelligence_duration_seconds 0.5\nsecret_email 7\n'
    assert parse_counters(data) == {'operations_total': 3, 'errors_total': 1, 'cache_hits_total': 2, 'processing_seconds_total': .5}

@pytest.mark.parametrize('value', ['nan', 'inf', '-1'])
def test_invalid_counter_rejected(value):
    with pytest.raises(ValueError):
        parse_counters(('proofit_intelligence_operations '+value).encode())

def test_missing_native_counter_rejected():
    with pytest.raises(ValueError):
        parse_counters(b'proofit_intelligence_operations 1')

def test_no_stale_or_user_identifiers():
    collector = Collector('localhost:1717')
    collector.snapshot = {'services': {key: 1 for key in SERVICES}, 'collected_at': 123, 'cpu_metrics_up': 0}
    registry = CollectorRegistry(); registry.register(collector)
    output = generate_latest(registry).decode()
    assert 'proofit_collection_last_success_timestamp_seconds 123.0' in output
    assert 'proofit_compute_operations_total' not in output
    assert not any(word in output for word in ('candidate_id', 'vacancy_id', 'email', 'password', 'token'))
    assert output.count('proofit_service_up{') == 9

def test_dashboard_fixed_datasource_and_probe_semantics():
    value = dashboard()
    assert len(value['panels']) == 16
    assert len({panel['id'] for panel in value['panels']}) == 16
    assert all(panel['datasource']['uid'] == 'proofit-prometheus' for panel in value['panels'])
    assert 'не задержка пользовательского API' in value['panels'][1]['description']

def test_database_disabled_is_explicit():
    collector = Collector('localhost:1717')
    collector.snapshot = {'database_enabled': 0, 'database_up': 0}
    registry = CollectorRegistry(); registry.register(collector)
    output = generate_latest(registry).decode()
    assert 'proofit_database_enabled 0.0' in output
    assert 'proofit_postgres_connections' not in output
