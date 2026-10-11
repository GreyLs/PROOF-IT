"""Prefer full local GPU offload and record the execution placement without downtime."""
from __future__ import annotations

import logging
import os

LOG = logging.getLogger(__name__)


def required() -> bool:
    return os.getenv("FSP_REQUIRE_GPU", "true").strip().lower() not in {"0", "false", "no"}


def request_options(**options):
    """Request that every model layer is placed on GPU, not auto-selected by Ollama."""
    return {**options, "num_gpu": 999}


def attest(client, base_url: str, model: str) -> bool:
    """Record whether Ollama placed the request fully on GPU.

    ``size_vram == size`` is reported by Ollama when all model weights are offloaded.
    A CPU fallback must remain available if the accelerator is temporarily down: the
    candidate's request is not discarded solely because a local device changed state.
    """
    if not required():
        return False
    try:
        response = client.get(base_url.rstrip("/") + "/api/ps")
        response.raise_for_status()
        models = response.json().get("models", [])
        active = next(
            (
                item for item in models
                if model in {str(item.get("name", "")), str(item.get("model", ""))}
            ),
            None,
        )
        total = int(active.get("size", 0)) if active else 0
        vram = int(active.get("size_vram", 0)) if active else 0
        threshold = int(os.getenv("FSP_GPU_MIN_OFFLOAD_PERCENT", "100"))
        gpu = total > 0 and vram > 0 and vram * 100 >= total * threshold
    except Exception as exc:
        LOG.warning("LLM GPU attestation unavailable: %s", type(exc).__name__)
        return False
    if not gpu:
        LOG.warning("LLM ran without requested full GPU offload: model=%s vram=%s total=%s", model, vram, total)
        return False
    LOG.info("LLM GPU attested: model=%s vram=%s", model, vram)
    return True
