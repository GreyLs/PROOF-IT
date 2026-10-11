"""Reproducibly generate training data, cross-validate, and train two CatBoost models.

The training labels are generated from a disclosed structural market simulator:
they combine supply, compensation, skill coverage, seniority and employer/candidate
signals with bounded heteroscedastic noise.  The data are synthetic by design, so
the reported metrics measure reconstruction of this simulated process and must not
be interpreted as a claim about future production hiring outcomes.
"""
from __future__ import annotations

import csv
import json
import math
import random
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev

from catboost import CatBoostRegressor

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "ml_time_forecasting" / "artifacts"
SEED = 20261008
FOLDS = 5
ROWS_PER_TASK = 10_000

VACANCY_FEATURES = (
    "relevant_candidates", "salary_competitiveness", "company_rating",
    "stack_complexity", "skill_coverage", "seniority_pressure", "remote_flexibility",
)
CANDIDATE_FEATURES = (
    "relevant_vacancies", "salary_alignment", "skill_match", "profile_completeness",
    "qualification_signal", "experience_years", "application_activity", "remote_flexibility",
)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def r2_score(actual: list[float], predicted: list[float]) -> float:
    centre = mean(actual)
    total = sum((value - centre) ** 2 for value in actual)
    residual = sum((value - guess) ** 2 for value, guess in zip(actual, predicted))
    return 1.0 - residual / total if total else 0.0


def rmse(actual: list[float], predicted: list[float]) -> float:
    return math.sqrt(mean((value - guess) ** 2 for value, guess in zip(actual, predicted)))


def vacancy_rows(rng: random.Random, count: int) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    for _ in range(count):
        candidates = min(380, max(0, int(rng.lognormvariate(3.35, 0.88))))
        salary = clamp(rng.gauss(1.0, 0.22), 0.55, 1.65)
        rating = clamp(rng.gauss(4.15, 0.48), 2.6, 5.0)
        complexity = rng.randint(2, 16)
        coverage = clamp(rng.betavariate(4.5, 2.4), 0.12, 1.0)
        seniority = rng.choices([0, 1, 2], weights=[0.34, 0.42, 0.24])[0]
        remote = rng.choices([0.25, 0.65, 1.0], weights=[0.2, 0.38, 0.42])[0]
        # Structural label: an interpretable market-response curve plus modest noise.
        days = (
            69.0
            - 10.8 * math.log1p(candidates)
            - 20.5 * salary
            - 5.3 * rating
            + 1.7 * complexity
            - 12.0 * coverage
            + 7.0 * seniority
            - 4.4 * remote
            + 4.2 * max(0.0, 0.95 - salary) * seniority
            + rng.gauss(0, 1.55 + 0.08 * complexity)
        )
        rows.append({
            "relevant_candidates": float(candidates), "salary_competitiveness": salary,
            "company_rating": rating, "stack_complexity": float(complexity),
            "skill_coverage": coverage, "seniority_pressure": float(seniority),
            "remote_flexibility": remote, "target_days": clamp(days, 9.0, 150.0),
        })
    return rows


def candidate_rows(rng: random.Random, count: int) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    for _ in range(count):
        vacancies = min(240, max(0, int(rng.lognormvariate(3.05, 0.83))))
        alignment = clamp(rng.gauss(0.98, 0.24), 0.50, 1.55)
        skill_match = clamp(rng.betavariate(4.2, 2.8), 0.08, 1.0)
        completeness = clamp(rng.betavariate(5.0, 1.8), 0.15, 1.0)
        qualified = float(rng.choices([0, 1], weights=[0.44, 0.56])[0])
        experience = clamp(rng.gammavariate(2.2, 2.0), 0.0, 22.0)
        activity = float(rng.randint(0, 20))
        remote = rng.choices([0.25, 0.65, 1.0], weights=[0.2, 0.38, 0.42])[0]
        days = (
            115.0
            - 6.5 * math.log1p(vacancies)
            - 22.0 * alignment
            - 17.0 * skill_match
            - 13.0 * completeness
            - 6.0 * qualified
            - 1.2 * experience
            - 0.85 * activity
            - 4.0 * remote
            + 12.0 * max(0.0, 0.92 - alignment)
            # The observation noise is deliberately lower than the structural
            # market signal so a model can be validated rather than rewarded
            # for fitting noise.
            + rng.gauss(0, 0.62 + 0.018 * vacancies)
        )
        rows.append({
            "relevant_vacancies": float(vacancies), "salary_alignment": alignment,
            "skill_match": skill_match, "profile_completeness": completeness,
            "qualification_signal": qualified, "experience_years": experience,
            "application_activity": activity, "remote_flexibility": remote,
            "target_days": clamp(days, 8.0, 170.0),
        })
    return rows


def matrix(rows: list[dict[str, float]], features: tuple[str, ...]) -> list[list[float]]:
    return [[row[name] for name in features] for row in rows]


def train_task(name: str, rows: list[dict[str, float]], features: tuple[str, ...]) -> dict:
    rng = random.Random(SEED + len(features))
    indices = list(range(len(rows)))
    rng.shuffle(indices)
    fold_size = len(indices) // FOLDS
    scores: list[dict[str, float]] = []
    targets = [row["target_days"] for row in rows]
    X = matrix(rows, features)
    for fold in range(FOLDS):
        lower, upper = fold * fold_size, (fold + 1) * fold_size if fold < FOLDS - 1 else len(indices)
        test = set(indices[lower:upper])
        train_indices = [index for index in indices if index not in test]
        valid_indices = [index for index in indices if index in test]
        model = CatBoostRegressor(
            loss_function="RMSE", iterations=420, depth=7, learning_rate=0.055,
            l2_leaf_reg=5.0, random_seed=SEED + fold, verbose=False,
            allow_writing_files=False, thread_count=4,
        )
        model.fit([X[index] for index in train_indices], [targets[index] for index in train_indices])
        prediction = model.predict([X[index] for index in valid_indices]).tolist()
        truth = [targets[index] for index in valid_indices]
        scores.append({"fold": fold + 1, "r2": r2_score(truth, prediction), "rmse_days": rmse(truth, prediction)})
    final = CatBoostRegressor(
        loss_function="RMSE", iterations=520, depth=7, learning_rate=0.055,
        l2_leaf_reg=5.0, random_seed=SEED, verbose=False, allow_writing_files=False, thread_count=4,
    )
    final.fit(X, targets)
    model_path = OUT / f"{name}.cbm"
    final.save_model(str(model_path))
    csv_path = OUT / f"{name}_synthetic.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=[*features, "target_days"])
        writer.writeheader()
        writer.writerows(rows)
    return {
        "model": model_path.name, "dataset": csv_path.name, "rows": len(rows),
        "features": list(features), "target": "target_days",
        "cv": {"folds": FOLDS, "r2_by_fold": [round(item["r2"], 4) for item in scores],
               "r2_mean": round(mean(item["r2"] for item in scores), 4),
               "r2_std": round(pstdev(item["r2"] for item in scores), 4),
               "rmse_days_mean": round(mean(item["rmse_days"] for item in scores), 3)},
        "feature_importance": {feature: round(float(value), 4) for feature, value in zip(features, final.feature_importances_)},
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    vacancy = train_task("vacancy_fill", vacancy_rows(random.Random(SEED), ROWS_PER_TASK), VACANCY_FEATURES)
    candidate = train_task("candidate_job_search", candidate_rows(random.Random(SEED + 1), ROWS_PER_TASK), CANDIDATE_FEATURES)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(), "seed": SEED,
        "method": "CatBoostRegressor; shuffled 5-fold cross-validation; independent fold evaluation",
        "data_scope": "synthetic market simulator; no personal data or historical hiring outcomes",
        "tasks": {"vacancy_fill": vacancy, "candidate_job_search": candidate},
    }
    evidence=OUT.parents[1]/'validation/reports/current';evidence.mkdir(parents=True,exist_ok=True)
    (evidence / "forecast-training.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    from scripts.build_model_manifest import main as manifest
    manifest()
    print(json.dumps({name: item["cv"] for name, item in report["tasks"].items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
