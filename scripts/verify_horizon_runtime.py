"""Live feature checks with real Qwen/GPT-OSS/Docker. Not a load test."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from intelligence.arena import create
from scripts.workbench_test_fixture import Fixture
from tests.test_horizon_http import finish
from tests.test_workbench import VACANCY
from worker.workbench import sandbox

ROOT = Path(__file__).resolve().parents[1]


def main():
    report = {"started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "checks": [], "capacity_test_run": False}
    fixture = Fixture()
    try:
        c, cu = fixture.register("candidate")
        e, eu = fixture.register("employer")
        for kind in ("python", "sql", "typescript"):
            contract = create({"kind": kind, "seed": 1729})
            tests = contract["public_tests"] + contract["hidden_tests"]
            correct = asyncio.run(sandbox(contract["reference_solution"], tests, kind))
            wrong = asyncio.run(sandbox("SELECT name,0 FROM accounts ORDER BY name" if kind == "sql" else "function solve(data){return []; }" if kind == "typescript" else "def solve(data): return []", tests, kind))
            assert correct["passed"] == len(tests), (kind, correct)
            assert wrong["passed"] < len(tests), (kind, wrong)
            report["checks"].append({"name": f"{kind}_isolated_contract", "passed": True, "correct_tests": correct["passed"], "total_tests": len(tests), "wrong_solution_tests": wrong["passed"]})
        created = c.post("/intelligence/arena", json={"kind": "typescript"})
        created.raise_for_status()
        arena_id = created.json()["id"]
        code = "function solve(data: {events: {id: string; account: string; amount: number}[]}) { const seen=new Set<string>(), totals=new Map<string,number>(); for(const e of data.events){if(seen.has(e.id))continue;seen.add(e.id);totals.set(e.account,(totals.get(e.account)||0)+e.amount);}return [...totals.keys()].sort().map(account=>({account,total:totals.get(account)})); }"
        started = time.perf_counter()
        submitted = c.post(f"/intelligence/arena/{arena_id}/submit", json={"code": code})
        submitted.raise_for_status()
        for _ in range(360):
            job = c.get("/intelligence/jobs/" + submitted.json()["job_id"]).json()
            if job["status"] == "done":
                break
            if job["status"] == "failed":
                raise AssertionError(job)
            time.sleep(1)
        result = job["result"]
        assert result["passed"] == result["total"] == 7, result
        assert result["review"]["execution"]["model"] == "gpt-oss:20b", result
        assert "hidden_tests" not in json.dumps(result) and "reference_solution" not in json.dumps(result)
        import httpx
        with httpx.Client(trust_env=False,timeout=10) as model_client:
            resident=next(x for x in model_client.get('http://127.0.0.1:11434/api/ps').json()['models'] if x['name']=='qwen3:8b')
            assert resident['size_vram']==resident['size'],resident
        report["checks"].append({"name": "typescript_full_gpt_oss_review", "passed": True, "score": result["score"], "model": result["review"]["execution"]["model"], "elapsed_seconds": round(time.perf_counter()-started, 2), "public_tests": 2, "hidden_tests": 5, "qwen_gpu_restored_percent":100})
        # Actual Qwen engineering review, rather than a keyword-based grade.
        scenario = c.post("/intelligence/arena", json={"kind": "incident"}).json()
        answer = "Сначала остановлю повторные списания безопасным feature flag и сохраню очередь. Сопоставлю event_id и транзакции с дублями, проверю retry и consumer lag. Исправление: UNIQUE(event_id) в inbox, проверка и запись побочного эффекта в одной транзакции; уведомления через outbox. Повтор возвращает сохранённый результат. Проверю concurrent retry, rollback, отсутствие двойной оплаты и восстановление consumer после crash. Контроль: duplicate rate=0, error rate, задержка обработки и backlog; rollout на малой доле с rollback. Накопленные дубли исправлю согласованными компенсационными операциями, без удаления истории."
        submitted = c.post("/intelligence/arena/"+scenario["id"]+"/submit",json={"code":answer})
        submitted.raise_for_status()
        for _ in range(360):
            job = c.get("/intelligence/jobs/"+submitted.json()["job_id"]).json()
            if job["status"] in ("done","failed"):
                break
            time.sleep(1)
        assert job["status"]=="done",job
        assert job["result"]["execution"]["model"]=="qwen3:8b"
        report["checks"].append({"name":"incident_qwen_review","passed":True,"model":"qwen3:8b","score":job["result"]["score"]})
        vacancy=e.post("/vacancies",json=VACANCY);vacancy.raise_for_status();vid=vacancy.json()["vacancy"]["id"]
        response=e.post("/intelligence/horizon",json={"entity_id":vid,"changes":{"reward_change_percent":10,"response_days":1,"interview_stages":2}});response.raise_for_status()
        h=finish(e,response.json()["job_id"])
        report["checks"].append({"name":"employer_live_horizon","passed":True,"trials":h["trials"],"gain_days":h["gain_days"],"probability":h["scenario"]["completion_probability"]})
        portfolio=e.post("/intelligence/strategy",json={"extra_budget":30000});portfolio.raise_for_status()
        plan=finish(e,portfolio.json()["job_id"])
        assert len(plan["vacancies"])==1 and plan["allocated_budget"]<=30000
        report["checks"].append({"name":"employer_live_portfolio","passed":True,"vacancies":1,"allocated_budget":plan["allocated_budget"]})
        report["passed"]=all(x["passed"] for x in report["checks"])
    except Exception as error:
        report["passed"]=False;report["error_type"]=type(error).__name__
        raise
    finally:
        fixture.close()
        (ROOT/"validation/reports/current/horizon-runtime.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps({"passed":report.get("passed"),"checks":len(report["checks"]),"capacity_test_run":False}))


if __name__ == "__main__":
    main()
