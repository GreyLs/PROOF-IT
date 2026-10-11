"""Authenticated microservice: no database credentials, only bounded features."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import hashlib
import hmac
import json
import os
import time

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from intelligence.engine import VERSION, career_route, horizon, proof_graph, strategy
from intelligence import arena, professional, integrity, oidc, needs, certification, twins, passport, providers
from intelligence import github_evidence, role_matrix, experiments, market_models, response_patterns
from intelligence import economic_sources, prospective
from ml_time_forecasting.service import load_models
from worker.config import secret

COUNTERS = {"operations": 0, "errors": 0, "cache_hits": 0, "duration_seconds": 0.0}
SLOTS = asyncio.Semaphore(int(os.getenv("INTELLIGENCE_SLOTS", "2")))
CACHE = {}
REDIS = None
REDIS_OPEN_UNTIL = 0.0


async def cache_command(operation, *args):
    """Cache failure must not disable the stateless calculation service."""
    global REDIS_OPEN_UNTIL
    if not REDIS or time.monotonic() < REDIS_OPEN_UNTIL:
        return None
    try:
        return await getattr(REDIS, operation)(*args)
    except Exception:
        REDIS_OPEN_UNTIL = time.monotonic() + 30
        return None


async def operation(request: Request):
    token = secret("INTELLIGENCE_TOKEN", "")
    supplied = request.headers.get("authorization", "").removeprefix("Bearer ")
    if len(token) < 32 or not hmac.compare_digest(token, supplied):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > 512000:
            return JSONResponse({"error": "input_limit"}, status_code=413)
        raw.extend(chunk)
    started = time.perf_counter()
    try:
        p = json.loads(raw)
        kind = p["operation"]
        if kind=='economic_fetch':
            async with SLOTS:
                result=await economic_sources.fetch(p)
            COUNTERS['operations']+=1
            return JSONResponse(result)
        if kind in ('github_profile','github_repository','github_verify_gist','github_pr','github_head'):
            async with SLOTS:
                result=await github_evidence.operation(p)
            COUNTERS['operations']+=1
            return JSONResponse(result)
        if kind=='provider_fetch':
            result=await providers.fetch(p)
            COUNTERS['operations']+=1
            return JSONResponse(result)
        if kind in ("oidc_start","oidc_finish"):
            result=await (oidc.start(p) if kind=="oidc_start" else oidc.finish(p))
            COUNTERS["operations"]+=1
            return JSONResponse(result)
        fn = {"horizon": horizon, "graph": proof_graph, "career_route": career_route, "strategy": strategy, "arena_create": arena.create, "arena_step": arena.step, "arena_public": lambda p: arena.public_contract(p["contract"]), "professional_create":professional.create,"professional_public":lambda p:professional.public(p["contract"]),"professional_step":professional.step,"professional_catalog":professional.catalog,"item_validate":professional.validate_draft,"item_calibrate":professional.calibrate}.get(kind)
        if kind in ("code_fingerprint","code_similarity"):
            fn=integrity.fingerprint if kind=="code_fingerprint" else integrity.compare
        if kind=="need_parse":fn=needs.parse
        if kind in ('economic_status','prospective_forecast','validation_protocol','parallel_cohort_report','macro_ablation'):
            fn={'economic_status':economic_sources.status,'prospective_forecast':prospective.forecast_report,
                'validation_protocol':prospective.protocol,'parallel_cohort_report':prospective.parallel_report,
                'macro_ablation':prospective.macro_ablation}[kind]
        if kind in ('role_matrix','role_attestation','form_assign','form_equivalence','response_patterns','bilateral','employer_reliability','robust_twin'):
            fn={'role_matrix':role_matrix.matrix,'role_attestation':role_matrix.attestation,
                'form_assign':experiments.assign,'form_equivalence':experiments.equivalence,
                'response_patterns':response_patterns.analyze,'bilateral':market_models.bilateral,
                'employer_reliability':market_models.reliability,'robust_twin':market_models.robust_twin}[kind]
        if kind=="professional_result":fn=lambda p:professional.result(p["contract"])
        if kind=="certification_prepare":fn=certification.prepare
        if kind=="certification_step":fn=certification.step
        if kind=="certification_result":fn=lambda p:certification.decision(p["contract"])
        if kind in ('twin_compatibility','twin_allocation','twin_next_proof','twin_diagnosis','twin_transfer','authorship_defense'):
            fn={'twin_compatibility':twins.compatibility,'twin_allocation':twins.allocation,'twin_next_proof':twins.next_proof,'twin_diagnosis':twins.diagnosis,'twin_transfer':twins.transfer,'authorship_defense':twins.authorship}[kind]
        if kind in ('passport_issue','passport_verify','passport_public'):
            fn={'passport_issue':passport.issue,'passport_verify':passport.verify,'passport_public':passport.public}[kind]
        if fn is None:
            raise ValueError("operation")
        key = hashlib.sha256(json.dumps(p, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        cached = CACHE.get(key)
        if REDIS:
            # Numeric/context cache only; no identity or authorization caching.
            value = await cache_command("get", "proofit:compute:" + key)
            cached = (time.monotonic() + 60, json.loads(value)) if value else None
        if cached and cached[0] > time.monotonic():
            COUNTERS["cache_hits"] += 1
            return JSONResponse(cached[1])
        async with SLOTS:
            result = await asyncio.to_thread(fn, p)
        if len(CACHE) >= 256:
            CACHE.pop(next(iter(CACHE)))
        CACHE[key] = (time.monotonic() + 60, result)
        if REDIS:
            await cache_command("setex", "proofit:compute:" + key, 60, json.dumps(result, ensure_ascii=False))
        COUNTERS["operations"] += 1
        return JSONResponse(result)
    except (ValueError, TypeError, KeyError):
        COUNTERS["errors"] += 1
        return JSONResponse({"error": "invalid_features"}, status_code=422)
    except Exception:
        COUNTERS["errors"] += 1
        return JSONResponse({"error": "temporarily_unavailable"}, status_code=503)
    finally:
        COUNTERS["duration_seconds"] += time.perf_counter() - started


async def health(_):
    return JSONResponse({"status": "ok", "version": VERSION, "redis": REDIS is not None})


async def metrics(_):
    return Response("\n".join(f"proofit_intelligence_{name} {value}" for name, value in COUNTERS.items()) + "\n", media_type="text/plain")


@asynccontextmanager
async def lifespan(_):
    global REDIS
    load_models()
    if os.getenv("REDIS_URL"):
        from redis.asyncio import Redis
        REDIS = Redis.from_url(os.environ["REDIS_URL"], socket_connect_timeout=2, socket_timeout=2)
        # A configured but temporarily unreachable cache must not prevent boot.
        await cache_command("ping")
    yield
    if REDIS:
        await REDIS.aclose()


app = Starlette(lifespan=lifespan, routes=[Route("/health", health), Route("/metrics", metrics), Route("/operation", operation, methods=["POST"])])
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.getenv("INTELLIGENCE_HOST", "127.0.0.1"), port=int(os.getenv("INTELLIGENCE_PORT", "8092")), access_log=False)
