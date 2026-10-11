"""Capture actual Rust checks without a load test or model substitution."""
import json
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    run = subprocess.run(
        ["cargo", "test", "--locked"], cwd=ROOT, capture_output=True, text=True
    )
    output = run.stdout + run.stderr
    totals = re.findall(
        r"test result: \w+\. (\d+) passed; (\d+) failed; (\d+) ignored; (\d+) measured; (\d+) filtered out",
        output,
    )
    counts = [sum(int(row[i]) for row in totals) for i in range(5)]
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "command": "cargo test --locked",
        "exit_code": run.returncode,
        "tests_passed": counts[0],
        "tests_failed": counts[1],
        "tests_ignored": counts[2],
        "tests_measured": counts[3],
        "tests_filtered_out": counts[4],
        "passed": run.returncode == 0 and bool(totals) and counts[1] == 0,
        "capacity_test_run": False,
        "output": output,
    }
    (ROOT / "validation/reports/current/rust.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in report.items() if k != "output"}))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
