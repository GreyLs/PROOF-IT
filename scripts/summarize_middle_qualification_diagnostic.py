from __future__ import annotations

import json
from pathlib import Path

path = Path("runtime/middle-qualification-diagnostic.json")
rows = json.loads(path.read_text(encoding="utf-8"))
summary = []
for row in rows:
    result = row.get("result", {})
    summary.append({
        "attempt": row["attempt"],
        "stage": row["stage"],
        "summary": row.get("summary"),
        "review": row.get("review"),
        "questions": [
            {"prompt": q.get("prompt"), "options": q.get("options"), "correct": q.get("correct")}
            for q in result.get("questions", [])[:2]
        ],
    })
print(json.dumps(summary, ensure_ascii=True))
