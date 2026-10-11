"""Repeat controlled ranking accuracy. Not a capacity/load test."""
import json
import time
from pathlib import Path

from scripts import evaluate, verify_candidate_ranking

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT / "validation/reports/current"
    employer_path = out / "employer-ranking.json"
    candidate_path = out / "candidate-ranking.json"
    evaluate.main(employer_path)
    verify_candidate_ranking.main(candidate_path)
    employer = json.loads(employer_path.read_text(encoding="utf-8"))
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    report = {
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "capacity_test_run": False,
        "method": "Controlled labelled functional ranking queries, not concurrent session capacity. Latency is observed during these queries, not production SLO or peak throughput.",
        "employer": {k: employer[k] for k in ("queries", "pairs", "precision_at_5", "ndcg_at_5", "p95_ms")},
        "candidate": {k: candidate[k] for k in ("queries", "provided_gold_pairs", "precision_at_5", "ndcg_at_5", "salary_compatible_top5", "p95_ms")},
        "limitations": "Disclosed synthetic oracle, not independent real-market hiring outcomes.",
    }
    # Preserve the measured values; a failed gate never rewrites them.
    report["passed"] = (
        employer["precision_at_5"] >= 0.99
        and employer["ndcg_at_5"] >= 0.95
        and candidate["precision_at_5"] >= 0.85
        and candidate["ndcg_at_5"] >= 0.90
    )
    report["acceptance_gates"] = {"employer_precision": 0.99, "employer_ndcg": 0.95, "candidate_precision": 0.85, "candidate_ndcg": 0.90}
    (out / "ranking.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
