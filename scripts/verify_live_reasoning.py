"""Capture the existing acceptance test against real Qwen, including failures."""
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    started = time.perf_counter()
    result = subprocess.run(
        ["cargo", "test", "--locked", "live_reasoning_regressions", "--", "--ignored", "--nocapture"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
    )
    cases = []
    for line in result.stdout.splitlines():
        if line.startswith("LIVE_GOLD "):
            _, number, raw = line.split(" ", 2)
            cases.append({"case": int(number), "evaluation": json.loads(raw)})
    report = {
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "command": "cargo test --locked live_reasoning_regressions -- --ignored --nocapture",
        "model": "qwen3:8b", "elapsed_seconds": round(time.perf_counter()-started, 3),
        "cases": cases, "expected_cases": 4, "exit_code": result.returncode,
        "passed": result.returncode == 0 and len(cases) == 4,
        "method": "Existing fixed acceptance cases; two correct and two unsafe answers. Rubric assertions unchanged. Actual local Qwen inference, not a mocked response.",
    }
    out = ROOT / "validation/reports/current"
    out.mkdir(parents=True, exist_ok=True)
    (out / "live-reasoning.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "live-reasoning.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k != "cases"}, ensure_ascii=False))
    if not report["passed"]:
        raise SystemExit(result.returncode or 1)

if __name__ == "__main__":
    main()
