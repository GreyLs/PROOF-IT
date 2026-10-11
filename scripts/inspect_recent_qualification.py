"""Print non-secret status for the latest local qualification-test records."""
from __future__ import annotations

import json
import os

import psycopg
from dotenv import load_dotenv

load_dotenv(".env")
url = os.getenv("WORKER_DATABASE_URL") or os.getenv("DATABASE_URL")
if not url:
    raise SystemExit("database URL missing")

with psycopg.connect(url) as conn:
    rows = conn.execute(
        """
        SELECT q.id, r.id, r.target_position, r.declared_grade,
               q.status, q.generation_status, q.error,
               r.about
          FROM qualification_tests q
          JOIN resume_profiles r ON r.id = q.resume_id
         WHERE r.target_position IN ('Senior Data Scientist', 'Middle Data Scientist')
         ORDER BY r.created_at DESC
         LIMIT 10
        """
    ).fetchall()
print(json.dumps(rows, ensure_ascii=True, default=str))
