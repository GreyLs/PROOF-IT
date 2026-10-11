"""Diagnose the local Qwen quality gate for the latest Middle DS resume.

The script is a development-only aid: it reads the synthetic resume, invokes the
same generator used by the isolated processor, and saves only diagnostic metadata.
"""
from __future__ import annotations

import json
import os
import traceback
from pathlib import Path
import sys

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from worker.qualification import generate

load_dotenv(ROOT / ".env")
url = os.getenv("WORKER_DATABASE_URL") or os.getenv("DATABASE_URL")
if not url:
    raise SystemExit("database URL missing")

with psycopg.connect(url) as conn:
    row = conn.execute(
        """
        SELECT r.id AS resume_id, r.target_position, r.specialization, r.declared_grade,
               r.experience_years, r.skills, r.about, q.seed
          FROM qualification_tests q
          JOIN resume_profiles r ON r.id=q.resume_id
         WHERE r.target_position=%s
         ORDER BY r.created_at DESC LIMIT 1
        """
    , (os.getenv("DEBUG_TARGET_POSITION", "Middle Data Scientist"),)).fetchone()
if not row:
    raise SystemExit("middle resume absent")

resume = dict(zip(
    ["resume_id", "target_position", "specialization", "declared_grade", "experience_years", "skills", "about", "seed"], row
))
seed = int(resume.pop("seed")[:8], 16)
os.environ["QUALIFICATION_DEBUG_PATH"] = str(ROOT / "runtime" / "middle-qualification-diagnostic.json")
try:
    result = generate({"resume": resume, "seed": seed})
    payload = {"status": "ready", "result": result}
except Exception as exc:  # Diagnostic artifact contains no candidate PII.
    payload = {
        "status": "failed",
        "error_type": type(exc).__name__,
        "error": str(exc),
        "trace": traceback.format_exc(),
    }
out = ROOT / "runtime" / "middle-qualification-debug.json"
out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"status": payload["status"], "artifact": str(out), "error": payload.get("error")}, ensure_ascii=True))
