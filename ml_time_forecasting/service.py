"""Private localhost inference service for the two time-to-outcome CatBoost models."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from catboost import CatBoostRegressor

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "ml_time_forecasting" / "artifacts"
MODELS: dict[str, tuple[CatBoostRegressor, list[str]]] = {}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def load_models() -> None:
    _predict_values.cache_clear()
    metrics = json.loads((ARTIFACTS / "model_manifest.json").read_text(encoding="utf-8"))
    for task, data in metrics["tasks"].items():
        model = CatBoostRegressor()
        model.load_model(str(ARTIFACTS / data["model"]))
        MODELS[task] = (model, data["features"])


@lru_cache(maxsize=4096)
def _predict_values(task: str, values: tuple[float, ...]) -> float:
    model, _ = MODELS[task]
    return round(float(model.predict([list(values)], thread_count=1)[0]), 1)


def predict(task: str, features: dict[str, Any]) -> float:
    model, names = MODELS[task]
    values = tuple(float(features[name]) for name in names)
    return _predict_values(task, values)


def vacancy_response(features: dict[str, Any]) -> dict[str, Any]:
    days = predict("vacancy_fill", features)
    target = max(1, round(days * 0.9))
    scenarios = [
        ("Увеличить верхнюю границу вознаграждения примерно на 10%", {"salary_competitiveness": clamp(float(features["salary_competitiveness"]) * 1.1, 0.5, 1.7)}),
        ("Расширить воронку: гибридный или удалённый формат и более широкий поиск", {"relevant_candidates": float(features["relevant_candidates"]) * 1.35, "remote_flexibility": 1.0}),
        ("Сократить обязательный стек до ключевых навыков", {"stack_complexity": max(1, float(features["stack_complexity"]) - 2), "skill_coverage": clamp(float(features["skill_coverage"]) + 0.12, 0.0, 1.0)}),
    ]
    options = [(days, "Сохраняйте текущие условия: изменения вознаграждения или стека пока не сокращают рассчитанный срок.")]
    for text, changed in scenarios:
        candidate = dict(features); candidate.update(changed)
        option_days = predict("vacancy_fill", candidate)
        options.append((option_days, text))
    best_days, recommendation = min(options, key=lambda value: value[0])
    return {"forecast_days": round(days), "forecast_weeks": round(days / 7, 1), "target_reduction_percent": 10,
            "target_days": target, "recommended_days": round(best_days), "recommendation": recommendation,
            "estimated_reduction_percent": round(max(0,(days-best_days)/days*100),1), "target_achievable": round(best_days)<=target,
            "drivers": {"relevant_candidates": round(float(features["relevant_candidates"])), "salary_competitiveness": round(float(features["salary_competitiveness"]), 2), "company_rating": round(float(features["company_rating"]), 1)}}


def candidate_response(features: dict[str, Any]) -> dict[str, Any]:
    days = predict("candidate_job_search", features)
    target = max(1, round(days * 0.9))
    scenarios = [
        ("Скорректировать ожидаемое вознаграждение примерно на 10% к медиане предложений", {"salary_alignment": clamp(float(features["salary_alignment"]) * 1.1, 0.5, 1.6)}),
        ("Подтвердить ключевые навыки и заполнить профиль до конца", {"profile_completeness": 1.0, "qualification_signal": 1.0, "skill_match": clamp(float(features["skill_match"]) + 0.12, 0.0, 1.0)}),
        ("Расширить охват: рассмотреть больше релевантных предложений", {"relevant_vacancies": float(features["relevant_vacancies"]) * 1.35, "application_activity": float(features["application_activity"]) + 4}),
    ]
    options = [(days, "Сохраняйте текущие ожидания: рассмотренные изменения пока не сокращают рассчитанный срок.")]
    for text, changed in scenarios:
        candidate = dict(features); candidate.update(changed)
        option_days = predict("candidate_job_search", candidate)
        options.append((option_days, text))
    best_days, recommendation = min(options, key=lambda value: value[0])
    return {"forecast_days": round(days), "forecast_weeks": round(days / 7, 1), "target_reduction_percent": 10,
            "target_days": target, "recommended_days": round(best_days), "recommendation": recommendation,
            "estimated_reduction_percent": round(max(0,(days-best_days)/days*100),1), "target_achievable": round(best_days)<=target,
            "drivers": {"relevant_vacancies": round(float(features["relevant_vacancies"])), "salary_alignment": round(float(features["salary_alignment"]), 2), "profile_completeness": round(float(features["profile_completeness"]), 2)}}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_: Any) -> None:
        return

    def reply(self, status: int, data: dict[str, Any]) -> None:
        encoded = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers(); self.wfile.write(encoded)

    def do_GET(self) -> None:
        if self.path == "/health":
            self.reply(HTTPStatus.OK, {"status": "ok", "models": sorted(MODELS)})
        else:
            self.reply(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/predict":
            self.reply(HTTPStatus.NOT_FOUND, {"error": "not found"}); return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 16_384: raise ValueError("invalid request length")
            payload = json.loads(self.rfile.read(length))
            task = payload["task"]; features = payload["features"]
            if task == "vacancy_fill": data = vacancy_response(features)
            elif task == "candidate_job_search": data = candidate_response(features)
            else: raise ValueError("unknown task")
            self.reply(HTTPStatus.OK, data)
        except (KeyError, TypeError, ValueError) as error:
            self.reply(HTTPStatus.BAD_REQUEST, {"error": str(error)})
        except Exception:
            self.reply(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "forecast unavailable"})


def main() -> None:
    load_models()
    address = os.environ.get("FORECAST_BIND_ADDR", "127.0.0.1:8090")
    host, port = address.rsplit(":", 1)
    ThreadingHTTPServer((host, int(port)), Handler).serve_forever()


if __name__ == "__main__":
    main()
