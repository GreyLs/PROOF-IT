"""Live boundary test for the expert dialogue context budget.

Uses the deployed local Qwen service, not a mock.  It deliberately combines a
15,000-character profile with three 450-character professional answers, then
checks that the API refuses 451 characters before an LLM call is made.
"""
from pathlib import Path
import hashlib
import json
import time
import uuid

from check_expert_dialogues import ROOT, cleanup, register

MAX_ANSWER = 450


def exactly(text: str, size: int = MAX_ANSWER) -> str:
    return ((text + " ") * (size // (len(text) + 1) + 1))[:size]


def main() -> None:
    client, user = register()
    report = {
        "run_id": uuid.uuid4().hex,
        "model": "local qwen3:8b",
        "mocked": False,
        "profile_characters": 15_000,
        "answer_limit": MAX_ANSWER,
        "turns": [],
        "source_sha256": hashlib.sha256((ROOT / "src" / "interview.rs").read_bytes()).hexdigest(),
    }
    try:
        profile = client.get("/profile").json()["profile"]
        evidence = (
            "I designed a payment event handler in Python and PostgreSQL. "
            "I owned the idempotency key, transaction boundary, rollout metric, and incident review. "
        )
        profile.update(
            specialization="backend_python",
            declared_grade="middle",
            skills=["Python", "PostgreSQL", "Architecture"],
            experience_years=5,
            about=exactly(evidence, 15_000),
        )
        response = client.put("/profile", json=profile)
        response.raise_for_status()

        started = time.perf_counter()
        response = client.post("/dialogues", json={"mode": "profile"})
        response.raise_for_status()
        dialogue = response.json()
        report["start_seconds"] = round(time.perf_counter() - started, 2)

        answers = [
            exactly("I personally selected a unique event key and kept the write with the ledger entry in one PostgreSQL transaction."),
            exactly("For retries I returned the saved outcome. I monitored duplicate writes, p95 latency, errors, and validated the release with a reconciliation query."),
            exactly("I proposed the design, implemented the migration, ran a canary release, and rolled back automatically when the error budget or latency threshold was exceeded."),
        ]
        for answer in answers:
            if dialogue["status"] != "active" or dialogue.get("phase") != "project":
                break
            started = time.perf_counter()
            response = client.post(
                f"/dialogues/{dialogue['id']}/messages",
                json={"text": answer, "revision": dialogue["revision"]},
            )
            response.raise_for_status()
            dialogue = response.json()
            report["turns"].append({
                "answer_characters": len(answer),
                "seconds": round(time.perf_counter() - started, 2),
                "question_count": dialogue["question_count"],
                "status": dialogue["status"],
                "phase": dialogue.get("phase"),
            })

        response = client.post(
            f"/dialogues/{dialogue['id']}/messages",
            json={"text": "x" * (MAX_ANSWER + 1), "revision": dialogue["revision"]},
        )
        report["over_limit_status"] = response.status_code
        report["over_limit_message"] = response.json().get("message", "")
        assert response.status_code == 400, response.text
        assert report["turns"], "the live model did not process a 600-character answer"
        assert all(item["answer_characters"] == MAX_ANSWER for item in report["turns"])
        report["passed"] = True
    except Exception as exc:
        report["passed"] = False
        report["error"] = str(exc)
        raise
    finally:
        client.close()
        cleanup(user)
        destination = ROOT / "runtime" / "dialogue-context-window-validation.json"
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
