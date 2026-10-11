"""Parameterized tasks, adaptive posterior and explicit trust boundaries."""
from __future__ import annotations

import hashlib
import math
import random

import numpy as np

VERSION = "arena-1.0.0"


def adaptive_bank(seed: int) -> list[dict]:
    rng = random.Random(seed)
    bank = []
    # Families probe actual engineering operations; new numbers are generated
    # deterministically for each attempt. Difficulty is an authored hypothesis.
    for difficulty in (-2, -1, 0, 1, 2):
        for family in range(6):
            a, b = rng.randint(2, 12), rng.randint(3, 15)
            if family == 0:
                prompt = f"Запрос orders JOIN lines USING(order_id): {a} заказов, по {b} строк на заказ. Сколько строк получится до агрегации count(*)?"
                answer = a * b
                skill = "SQL"
            elif family == 1:
                prompt = f"API получил {a} различных ключей идемпотентности, каждый повторён {b} раз. Сколько побочных эффектов должно быть зафиксировано?"
                answer = a
                skill = "API design"
            elif family == 2:
                prompt = f"API обрабатывает {a*b} записей пакетами по {a}. Сколько пакетов требуется при однократной обработке каждой записи?"
                answer = b
                skill = "Algorithms"
            elif family == 3:
                prompt = f"У классификатора TP={a*b}, FP={a}, FN={b}. Укажите recall в процентах, округлив до целого."
                answer = math.floor(100 * a * b / (a * b + b) + .5)
                skill = "ML evaluation"
            elif family == 4:
                prompt = f"Есть {a} реплик, у каждой {b} соединений с БД. PgBouncer допускает {a*b+5} соединений upstream. Сколько соединений остаётся в резерве?"
                answer = 5
                skill = "System design"
            else:
                prompt = f"Consumer получает {a} уникальных событий, каждое доставлено {b} раз. Используется транзакционный inbox с UNIQUE(event_id). Сколько записей должно быть сохранено?"
                answer = a
                skill = "Reliability"
            bank.append({"id": f"f{family}d{difficulty}", "prompt": prompt, "answer": answer, "difficulty": difficulty, "discrimination": 1.1, "skill": skill})
    return bank


def posterior(bank: list[dict], answers: list[dict]) -> tuple[float, float, list]:
    grid = np.linspace(-3.5, 3.5, 141)
    logp = -.5 * grid**2
    by_id = {item["id"]: item for item in bank}
    for answer in answers:
        item = by_id[answer["id"]]
        prob = .1 + .9 / (1 + np.exp(-item["discrimination"] * (grid - item["difficulty"])))
        logp += np.log(prob if answer["correct"] else 1 - prob)
    weights = np.exp(logp - logp.max())
    weights /= weights.sum()
    theta = float(np.sum(grid * weights))
    se = float(np.sqrt(np.sum((grid - theta)**2 * weights)))
    return theta, se, weights.tolist()


def next_item(contract: dict) -> dict | None:
    used = {item["id"] for item in contract["answers"]}
    theta, se, _ = posterior(contract["bank"], contract["answers"])
    if len(used) >= 12 or len(used) >= 6 and se <= .55:
        return None
    counts = {}
    for item in contract["bank"]:
        if item["id"] in used:
            counts[item["skill"]] = counts.get(item["skill"], 0) + 1
    def utility(item):
        p = 1 / (1 + math.exp(-item["discrimination"] * (theta - item["difficulty"])))
        information = item["discrimination"] ** 2 * p * (1 - p)
        return information / (1 + counts.get(item["skill"], 0))
    return max((item for item in contract["bank"] if item["id"] not in used), key=utility)


def public_contract(contract: dict) -> dict:
    if contract["kind"] == "adaptive":
        item = next_item(contract)
        theta, se, _ = posterior(contract["bank"], contract["answers"])
        return {"kind": "adaptive", "title": "Адаптивная практика", "answered": len(contract["answers"]), "max_questions": 12, "theta": round(theta, 3), "standard_error": round(se, 3), "question": {"id": item["id"], "prompt": item["prompt"], "skill": item["skill"]} if item else None}
    return {key: contract[key] for key in ("kind", "title", "prompt", "starter_code", "skills", "public_tests") if key in contract}


def create(payload: dict) -> dict:
    kind = payload["kind"]
    seed = int(payload.get("seed", 20261009))
    rng = random.Random(seed)
    if kind == "adaptive":
        return {"kind": kind, "title": "Адаптивная практика", "bank": adaptive_bank(seed), "answers": [], "version": VERSION}
    factor = rng.randint(2, 9)
    public = [{"input": {"items": []}, "expected": 0}, {"input": {"items": [2, -1, 3]}, "expected": 4 * factor}]
    hidden = [{"input": {"items": values}, "expected": sum(values) * factor} for values in ([0], [-5, -2], [1] * 20, [999, -999], [rng.randint(-100, 100) for _ in range(31)])]
    if kind in ("python", "typescript"):
        starter = "def solve(data):\n    # data = {\"events\": [{\"id\": str, \"account\": str, \"amount\": int}]}\n    return []" if kind == "python" else "function solve(data: {events: {id: string; account: string; amount: number}[]}): {account: string; total: number}[] {\n  return [];\n}"
        reference = "def solve(data):\n    seen=set(); totals={}\n    for event in data['events']:\n        if event['id'] in seen: continue\n        seen.add(event['id'])\n        key=event['account']; totals[key]=totals.get(key,0)+event['amount']\n    return [{'account':k,'total':totals[k]} for k in sorted(totals)]" if kind == "python" else "function solve(data) { const seen=new Set(), totals=new Map(); for(const event of data.events) {if(seen.has(event.id))continue; seen.add(event.id);totals.set(event.account,(totals.get(event.account)||0)+event.amount);} return [...totals.keys()].sort().map(account=>({account,total:totals.get(account)})); }"
        def case(events, expected):
            return {"input": {"events": events}, "expected": expected}
        def event(key, account, amount):
            return {"id": key, "account": account, "amount": amount}
        public = [case([], []), case([event("a", "x", factor), event("a", "x", 99), event("b", "y", -3)], [{"account": "x", "total": factor}, {"account": "y", "total": -3}])]
        hidden = [case([event("a", "x", 0)], [{"account": "x", "total": 0}]), case([event("a", "z", 5), event("b", "z", -5)], [{"account": "z", "total": 0}]), case([event("same", "x", 4), event("same", "y", 8)], [{"account": "x", "total": 4}]), case([event("a", "b", -factor), event("b", "a", 100), event("c", "b", factor*2)], [{"account": "a", "total": 100}, {"account": "b", "total": factor}]), case([event(str(i), "x", 1) for i in range(101)] + [event("0", "x", 200)], [{"account": "x", "total": 101}])]
        return {"kind": kind, "title": "Идемпотентный ledger событий", "prompt": "Реализуйте solve(data) для событий, доставляемых at-least-once. data.events содержит {id, account, amount}. Засчитывается только первое появление каждого id во всём потоке, включая конфликтующий повтор с другим account/amount. Верните [{account,total}] с балансом каждого обработанного счёта, отсортировав account лексикографически. Нулевые балансы сохраняются. Пустой поток возвращает []. Вход менять нельзя. Ожидаемая сложность O(n + k log k), где k — число счетов.", "starter_code": starter, "reference_solution": reference, "public_tests": public, "hidden_tests": hidden, "skills": ["Python" if kind == "python" else "TypeScript", "Idempotency", "Algorithms"], "version": VERSION}
    if kind == "sql":
        def sql_case(accounts, rows, expected):
            return {"input": {"accounts": accounts, "rows": rows}, "expected": expected}
        public = [sql_case([[1,"a"]], [], [["a",0]]), sql_case([[1,"a"],[2,"b"]], [[1,1,5,"k"],[2,1,99,"k"],[3,2,-3,"j"]], [["a",5],["b",-3]])]
        hidden = [sql_case([], [], []), sql_case([[1,"a"],[2,"b"]], [[1,1,2,"k"],[2,2,99,"k"]], [["a",2],["b",0]]), sql_case([[1,"a"]], [[1,1,5,"k"],[2,1,-5,"j"]], [["a",0]]), sql_case([[1,"a"]], [[1,99,5,"k"]], [["a",0]]), sql_case([[2,"b"],[1,"a"]], [[1,2,-factor,"k"],[2,1,100,"j"],[3,2,factor*2,"m"]], [["a",100],["b",factor]])]
        return {"kind": kind, "title": "SQL ledger: JOIN, дубли и пустые счета", "prompt": "Таблицы accounts(id INTEGER,name TEXT), events(id INTEGER,account_id INTEGER,value INTEGER,event_key TEXT). Событие учитывается только по записи с минимальным id среди одинаковых event_key. Верните name,total для всех accounts, включая счета без событий с total=0. События без существующего account не учитываются. Сортировка по name. Доступен SQLite; только SELECT, CTE и оконные функции.", "starter_code": "SELECT name, 0 AS total FROM accounts ORDER BY name;", "reference_solution": "WITH first_events AS (SELECT *,ROW_NUMBER() OVER(PARTITION BY event_key ORDER BY id) AS rn FROM events) SELECT a.name,COALESCE(SUM(e.value),0) AS total FROM accounts a LEFT JOIN first_events e ON e.account_id=a.id AND e.rn=1 GROUP BY a.id,a.name ORDER BY a.name", "public_tests": public, "hidden_tests": hidden, "skills": ["SQL", "Idempotency", "Data quality"], "version": VERSION}
    prompts = {
        "incident": ("Инцидент: повторная доставка", "После релиза платежи начали дублироваться при повторной доставке событий. Есть очередь at-least-once и PostgreSQL. Опишите диагностику, безопасное сдерживание, идемпотентное исправление, тесты и восстановление. Укажите наблюдаемые метрики и критерий завершения инцидента.", ["Reliability", "PostgreSQL", "Incident response"]),
        "design": ("Системный дизайн: устойчивый найм", "Спроектируйте сервис приглашений при большом числе активных сессий. Контакты открываются только после согласия; повторные запросы не дублируют приглашения. Опишите API, границы транзакций, очереди, кэш, отказ Redis/БД, защиту ПДн, наблюдаемость и план масштабирования.", ["System design", "Privacy", "PostgreSQL"]),
        "review": ("Ревью pull request: гонка состояния", "В PR добавили accept_invitation(id): SELECT status; if status == 'sent': UPDATE status='accepted'; send_email(); return contacts. Проверка владельца отсутствует. Два запроса могут выполняться одновременно. Проведите review: найдите проблемы, предложите исправленный порядок действий, транзакцию/outbox и необходимые тесты.", ["Code review", "Reliability", "Security"]),
    }
    if kind not in prompts:
        raise ValueError("kind")
    title, prompt, skills = prompts[kind]
    return {"kind": kind, "title": title, "prompt": prompt, "skills": skills, "starter_code": "", "public_tests": [], "version": VERSION}


def step(payload: dict) -> dict:
    contract = payload["contract"]
    if contract["kind"] != "adaptive":
        raise ValueError("kind")
    item = next_item(contract)
    if not item or payload["question_id"] != item["id"]:
        raise ValueError("stale_question")
    answer = payload["answer"]
    if isinstance(answer, bool) or not isinstance(answer, (int, float)) or not math.isfinite(answer):
        raise ValueError("answer")
    updated = {**contract, "answers": contract["answers"] + [{"id": item["id"], "correct": abs(answer - item["answer"]) < 1e-8}]}
    current = public_contract(updated)
    complete = current["question"] is None
    theta, se, _ = posterior(updated["bank"], updated["answers"])
    return {"contract": updated, "public": current, "completed": complete, "result": {"score": round(sum(a["correct"] for a in updated["answers"]) / len(updated["answers"]) * 100), "theta": round(theta, 3), "standard_error": round(se, 3), "theta_interval": [round(theta - 1.96 * se, 2), round(theta + 1.96 * se, 2)], "questions": len(updated["answers"]), "version": VERSION, "skills": sorted({x["skill"] for x in updated["bank"] if x["id"] in {a["id"] for a in updated["answers"]}}), "grade_changed": False} if complete else None}
