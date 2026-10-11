"""Compute service boundary/cache failure tests; not an external Redis benchmark."""
import pytest
from starlette.testclient import TestClient

from intelligence import service

TOKEN = "boundary-test-token-" + "x" * 48
HEADERS = {"Authorization": "Bearer " + TOKEN}


@pytest.fixture
def compute(monkeypatch):
    monkeypatch.setattr(service, "secret", lambda *args: TOKEN)
    monkeypatch.setattr(service, "REDIS", None)
    monkeypatch.setattr(service, "REDIS_OPEN_UNTIL", 0)
    monkeypatch.setattr(service, "CACHE", {})
    monkeypatch.setattr(service, "load_models", lambda: None)
    monkeypatch.delenv("REDIS_URL", raising=False)
    calls = []
    monkeypatch.setattr(service, "horizon", lambda p: calls.append(p) or {"computed": len(calls)})
    return calls


def test_compute_requires_service_token(compute):
    with TestClient(service.app) as client:
        assert client.post("/operation", json={"operation": "horizon"}).status_code == 401
        assert client.post("/operation", headers={"Authorization": "Bearer incorrect"}, json={"operation": "horizon"}).status_code == 401
    assert not compute


def test_compute_rejects_oversized_stream_without_invoking_engine(compute):
    with TestClient(service.app) as client:
        body = iter([b'{"operation":"horizon","padding":"', b"x" * 512001, b'"}'])
        response = client.post("/operation", headers=HEADERS, content=body)
        assert response.status_code == 413
    assert not compute


def test_compute_local_cache_reuses_identical_features(compute):
    with TestClient(service.app) as client:
        p = {"operation": "horizon", "features": {"pool": 5}}
        first = client.post("/operation", headers=HEADERS, json=p)
        second = client.post("/operation", headers=HEADERS, json=p)
        assert first.json() == second.json() == {"computed": 1}
    assert len(compute) == 1


class UnavailableCache:
    closed = False
    async def ping(self):
        raise OSError("controlled cache outage")
    async def get(self, key):
        raise OSError("controlled cache outage")
    async def aclose(self):
        self.closed = True


def test_configured_redis_outage_does_not_prevent_start_or_calculation(compute, monkeypatch):
    from redis.asyncio import Redis
    cache = UnavailableCache()
    monkeypatch.setenv("REDIS_URL", "redis://unavailable.invalid:6379/0")
    monkeypatch.setattr(Redis, "from_url", lambda *args, **kwargs: cache)
    with TestClient(service.app) as client:
        assert client.get("/health").status_code == 200
        result = client.post("/operation", headers=HEADERS, json={"operation": "horizon"})
        assert result.status_code == 200 and result.json() == {"computed": 1}
        assert service.REDIS_OPEN_UNTIL > 0
    assert cache.closed


def test_redis_runtime_outage_bypasses_cache_but_keeps_computing(compute, monkeypatch):
    monkeypatch.setattr(service, "REDIS", UnavailableCache())
    with TestClient(service.app) as client:
        for value in (1, 2):
            result = client.post("/operation", headers=HEADERS, json={"operation": "horizon"})
            assert result.status_code == 200 and result.json() == {"computed": value}
    assert len(compute) == 2
