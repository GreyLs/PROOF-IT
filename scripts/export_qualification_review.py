"""Export candidate-visible questions for expert review; answer keys are excluded."""
from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
url = os.getenv("WORKER_DATABASE_URL") or os.getenv("DATABASE_URL")
if not url:
    raise SystemExit("database URL missing")

with psycopg.connect(url) as conn:
    rows = conn.execute(
        """
        SELECT r.target_position, r.declared_grade, q.questions, q.generation_status, q.status
          FROM qualification_tests q JOIN resume_profiles r ON r.id=q.resume_id
         WHERE r.target_position IN ('Senior Data Scientist', 'Middle Data Scientist')
           AND q.generation_status='ready'
         ORDER BY r.created_at DESC
        """
    ).fetchall()

tests = []
for role, grade, stored, generation_status, status in rows:
    questions = stored.get("questions", [])
    tests.append({
        "target_position": role,
        "declared_grade": grade,
        "generation_status": generation_status,
        "status": status,
        "questions": [
            {"number": n, "prompt": q["prompt"], "options": q["options"]}
            for n, q in enumerate(questions, 1)
        ],
    })
out = ROOT / "runtime" / "qualification-tests-expert-review.json"
out.write_text(json.dumps({"tests": tests}, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({
    "artifact": str(out),
    "tests": [(x["target_position"], len(x["questions"])) for x in tests],
}, ensure_ascii=True))
