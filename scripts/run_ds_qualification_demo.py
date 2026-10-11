"""Provision an isolated candidate and exercise per-resume qualification generation.

This script is intentionally local-only: it uses the development mail token and stores
only non-secret run metadata under ``runtime/``.  It is useful for reviewing the exact
candidate-visible questions produced by the current local Qwen model.
"""
from __future__ import annotations

import json
import secrets
import time
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]
BASE = "http://localhost:8080"
OUT = ROOT / "runtime" / "ds-qualification-demo.json"


RESUMES = [
    {
        "target_position": "Senior Data Scientist",
        "specialization": "ml_data_science",
        "declared_grade": "senior",
        "experience_years": 7.5,
        "skills": [
            "Python", "SQL", "Pandas", "scikit-learn", "PyTorch", "MLflow",
            "Airflow", "ClickHouse", "Docker", "A/B-тесты",
        ],
        "about": (
            "За 7,5 лет в Data Science вёл проекты от постановки бизнес-метрики до эксплуатации. "
            "Разработал и запустил в прод модели прогноза спроса, churn и кредитного риска; "
            "отвечал за качество данных, feature store, batch-и real-time scoring, мониторинг дрейфа и проведение аб-экспериментов. "
            "Менторил двух DS, защищал решения перед product, risk и platform-командами. "
            "Критерий успеха: прирост целевой бизнес-метрики при контроле рисков, стабильность модели и воспроизводимость пайплайна."
        ),
        "expected_salary": 420000,
        "work_format": "Гибридный",
        "visibility": "private",
    },
    {
        "target_position": "Middle Data Scientist",
        "specialization": "ml_data_science",
        "declared_grade": "middle",
        "experience_years": 3.5,
        "skills": [
            "Python", "SQL", "Pandas", "scikit-learn", "MLflow", "Airflow",
            "Docker", "Git", "A/B-тесты", "статистика",
        ],
        "about": (
            "3,5 года работы в DS-команде онлайн-сервиса. Выполнял end-to-end задачи: "
            "уточнял цель с product-менеджером, готовил выборки SQL/Python, обучал и валидировал модели, "
            "запускал batch-скоринг с MLflow и Airflow, анализировал качество модели после запуска. "
            "Имею опыт в прогнозе спроса и рекомендациях; коммуницирую ограничения и результаты бизнесу."
        ),
        "expected_salary": 260000,
        "work_format": "Удалённый",
        "visibility": "private",
    },
]


def main() -> None:
    email = f"qa-ds-{secrets.token_hex(5)}@example.test"
    password = secrets.token_urlsafe(24)
    started = time.monotonic()
    with httpx.Client(base_url=BASE + "/api", headers={"Origin": BASE}, timeout=60, trust_env=False) as client:
        meta = client.get("/meta").json()
        if not meta.get("demo"):
            raise SystemExit("This local QA script requires FSP_DEMO_MODE=true")
        registered = client.post("/auth/register", json={
            "email": email, "password": password, "role": "candidate",
            "name": "Демо-кандидат Data Science", "consent_processing": True,
        })
        registered.raise_for_status()
        token = registered.json().get("development_mail", {}).get("token")
        if not token:
            raise SystemExit("Development verification token missing")
        verified = client.post("/auth/verify", json={"token": token})
        verified.raise_for_status()

        created = []
        for resume in RESUMES:
            response = client.post("/resumes", json=resume)
            response.raise_for_status()
            created.append(response.json()["resume"])

        # Poll the candidate-visible endpoint; do not leak answer keys to the artefact.
        results = []
        deadline = time.monotonic() + 720
        remaining = {item["id"]: item for item in created}
        while remaining and time.monotonic() < deadline:
            for resume_id, item in list(remaining.items()):
                response = client.get(f"/resumes/{resume_id}/test")
                response.raise_for_status()
                test = response.json()
                if test["generation_status"] == "ready" and test["status"] == "ready":
                    if len(test["questions"]) != 10 or any(len(q.get("options", [])) != 5 for q in test["questions"]):
                        raise RuntimeError(f"Unexpected public question set structure for {resume_id}")
                    results.append(test)
                    del remaining[resume_id]
                elif test["generation_status"] == "failed":
                    raise RuntimeError(f"Generation failed for {resume_id}: {test.get('error')}")
            if remaining:
                time.sleep(3)
        if remaining:
            raise TimeoutError(f"Qualification generation timed out for {', '.join(remaining)}")

    output = {
        "run": "isolated local QA candidate; account credentials intentionally not retained",
        "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_seconds": round(time.monotonic() - started, 1),
        "candidate_email_hint": email.replace(email.split("@")[0], "qa-ds-…"),
        "tests": results,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "result": "ok", "tests": [{"resume_id": t["resume_id"], "target_position": t["target_position"], "questions": len(t["questions"])} for t in results],
        "elapsed_seconds": output["elapsed_seconds"], "artifact": str(OUT),
    }, ensure_ascii=True))


if __name__ == "__main__":
    main()
