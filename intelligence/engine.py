"""Versioned scenario models; no names, contacts, inferred personality or labels.

Horizon uses common random numbers to compare counterfactual interventions.
CatBoost supplies a frozen time prior; a competing-event model accounts for
response delay, assessment friction and a bounded finite market. Outputs are
scenario probabilities, not empirically calibrated hiring probabilities.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import numpy as np

VERSION = "horizon-1.0.0"
GRAPH_VERSION = "proof-graph-3.0.0"


def number(payload: dict, key: str, default: float, low: float, high: float) -> float:
    value = payload.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(key)
    if not low <= value <= high:
        raise ValueError(key)
    return float(value)


def horizon(payload: dict) -> dict:
    from ml_time_forecasting.service import predict
    mode = payload["mode"]
    if mode not in ("candidate", "employer"):
        raise ValueError("mode")
    task = "candidate_job_search" if mode == "candidate" else "vacancy_fill"
    features = dict(payload["features"])
    changes = payload.get("changes", {})
    if not isinstance(changes,dict) or set(changes) - {"response_days","interview_stages","reward_change_percent","flexibility","proof_gain","skill_focus","horizon_days"}:
        raise ValueError("changes")
    response_days = number(changes, "response_days", 3, .25, 14)
    stages = number(changes, "interview_stages", 3, 1, 7)
    reward = number(changes, "reward_change_percent", 0, 0 if mode == "employer" else -20, 40 if mode == "employer" else 0)
    flexibility = number(changes, "flexibility", float(features["remote_flexibility"]), .25, 1)
    proof = number(changes, "proof_gain", 0, 0, .35)
    skill_focus = number(changes, "skill_focus", 0, 0, 3)
    trials = int(number(payload, "trials", 1024, 128, 4096))
    horizon_days = int(number(changes, "horizon_days", 60, 14, 180))
    seed = int(number(payload, "seed", 20261009, 1, 2**31 - 1))
    baseline_days = max(2.0, predict(task, features))
    changed = dict(features)
    if mode == "employer":
        changed["salary_competitiveness"] = min(1.7, features["salary_competitiveness"] * (1 + reward / 100))
        changed["remote_flexibility"] = max(features["remote_flexibility"], flexibility)
        changed["relevant_candidates"] = min(8000, features["relevant_candidates"] * (1 + .3 * max(0, flexibility - features["remote_flexibility"])))
        changed["stack_complexity"] = max(1, features["stack_complexity"] - skill_focus)
        changed["skill_coverage"] = min(1, features["skill_coverage"] + .04 * skill_focus)
        pool = features["relevant_candidates"]
    else:
        changed["salary_alignment"] = min(1.6, features["salary_alignment"] / (1 + reward / 100))
        changed["qualification_signal"] = min(1, features["qualification_signal"] + proof)
        changed["skill_match"] = min(1, features["skill_match"] + proof / 2)
        changed["profile_completeness"] = min(1, features["profile_completeness"] + proof / 2)
        changed["remote_flexibility"] = max(features["remote_flexibility"], flexibility)
        pool = features["relevant_vacancies"]
    scenario_days = max(2.0, predict(task, changed))
    # Zero interventions produce an exactly identical curve.
    friction = (response_days / 3) ** .14 * (stages / 3) ** .12
    scenario_days *= friction
    rng = np.random.default_rng(seed)
    shared_shock = rng.lognormal(-.5 * .3**2, .3, trials)
    waiting = rng.weibull(1.6, trials)
    competition = rng.random(trials)
    # A sparse/empty pool is allowed to produce censoring, never invented people.
    reachable = 1 - math.exp(-max(0, pool) / 5)
    improved_pool = changed.get("relevant_candidates", changed.get("relevant_vacancies", 0))
    scenario_reachable = 1 - math.exp(-max(0, improved_pool) / 5)
    base_time = baseline_days * shared_shock * waiting / math.gamma(1 + 1 / 1.6)
    scenario_time = scenario_days * shared_shock * waiting / math.gamma(1 + 1 / 1.6)
    base_time[competition > reachable] = np.inf
    scenario_time[competition > scenario_reachable] = np.inf

    def summarize(times: np.ndarray) -> dict:
        observed = times[np.isfinite(times)]
        # Include unsuccessful paths in quantiles. A conditional median among
        # successful trials would conceal a majority who never find a match.
        ordered = np.sort(times)
        quantiles = [ordered[min(len(ordered)-1, math.ceil(q*len(ordered))-1)] for q in (.1,.5,.9)]
        return {
            "p10_days": round(float(quantiles[0]), 1) if np.isfinite(quantiles[0]) else None,
            "median_days": round(float(quantiles[1]), 1) if np.isfinite(quantiles[1]) else None,
            "p90_days": round(float(quantiles[2]), 1) if np.isfinite(quantiles[2]) else None,
            "completion_probability": round(float(np.mean(times <= horizon_days)), 4),
            "unreachable_share": round(float(np.mean(~np.isfinite(times))), 4),
            "curve": [{"day": int(day), "probability": round(float(np.mean(times <= day)), 4)} for day in sorted(set(range(0, horizon_days + 1, max(1, horizon_days // 20))) | {horizon_days})],
        }

    baseline, scenario = summarize(base_time), summarize(scenario_time)
    median_before, median_after = baseline["median_days"], scenario["median_days"]
    gain = round(median_before - median_after, 1) if median_before and median_after else 0
    interventions = []
    for label, patch in (
        ("Быстрая обратная связь", {"response_days": 1}),
        ("Два содержательных этапа вместо трёх", {"interview_stages": 2}),
        ("Более гибкий формат", {"flexibility": 1}),
        ("Увеличить вознаграждение на 10%" if mode == "employer" else "Подтвердить ключевые навыки", {"reward_change_percent": 10} if mode == "employer" else {"proof_gain": .2}),
    ):
        if payload.get("explain", True):
            option = horizon({**payload, "changes": {**changes, **patch}, "explain": False})
            value = option["scenario"]["median_days"]
            if value is not None:
                interventions.append({"action": label, "changes": patch, "median_days": value, "gain_days": round((median_after or baseline_days) - value, 1)})
    interventions.sort(key=lambda item: (-item["gain_days"], item["action"]))
    return {
        "version": VERSION, "mode": mode, "trials": trials, "seed": seed,
        "horizon_days": horizon_days, "baseline": baseline, "scenario": scenario,
        "gain_days": gain, "gain_percent": round(100 * gain / median_before, 1) if median_before else 0,
        "target_achievable": bool(median_before and median_after and median_after <= median_before * .9),
        "interventions": [item for item in interventions if item["gain_days"] > 0],
        "bottlenecks": [label for condition, label in [(pool < 5, "Небольшой доступный рынок"), (response_days > 3, "Длительное ожидание обратной связи"), (stages > 3, "Много этапов отбора"), (features.get("skill_coverage", features.get("skill_match", 1)) < .6, "Неполное покрытие ключевых навыков")] if condition],
        "assumptions": {"time_prior": "frozen-catboost", "competition": "finite-pool", "uncertainty": "scenario-distribution", "changes_applied": changes},
        "empty_market": pool <= 0,
    }


def proof_graph(payload: dict) -> dict:
    """Bipartite evidence→skill→role graph with normalized walk propagation."""
    evidence = payload.get("evidence", [])
    skills = {str(skill).strip().lower() for skill in payload.get("skills", []) if str(skill).strip()}
    roles = payload.get("roles", [])
    nodes, edges = [], []
    # Repeated proofs of the same source class are correlated: max, not sum.
    # Independent source classes combine by noisy-OR after temporal decay.
    from datetime import datetime, timezone
    now = datetime.fromisoformat(payload["as_of"].replace("Z", "+00:00")) if payload.get("as_of") else datetime.now(timezone.utc)
    by_source = {}
    visible = []
    for item in evidence:
        if item.get("hidden") or item.get("disputed"):
            continue
        if item.get("valid_until") and datetime.fromisoformat(item["valid_until"].replace("Z","+00:00")) <= now:
            continue
        visible.append(item)
        node_id = "e:" + item["id"]
        nodes.append({"id": node_id, "kind": "evidence", "label": item["title"], "status": item["status"], "source_id": item["id"]})
        weight = min(.95, max(0, float(item.get("weight", 0))))
        issued = item.get("issued_at")
        if issued:
            age = max(0, (now-datetime.fromisoformat(issued.replace("Z","+00:00"))).total_seconds()/86400)
            weight *= math.exp(-math.log(2)*age/(180 if item.get("source")=="qualification" else 90))
        if item.get("status")=="declared": weight=0
        nodes[-1]["strength"]=weight
        source_class = {"qualification":"qualification","sandbox":"execution","arena":"execution"}.get(item.get("source"),item.get("source","unknown"))
        for skill in item.get("skills", []):
            key = str(skill).strip().lower()
            if not key: continue
            skills.add(key)
            by_source.setdefault(key,{})[source_class] = max(by_source.get(key,{}).get(source_class,0),weight)
            edges.append({"from": node_id, "to": "s:" + key, "weight": round(weight, 6), "relation": "supports"})
    support = {skill: 1-math.prod(1-w for w in by_source.get(skill,{}).values()) for skill in skills}
    for skill in sorted(skills):
        nodes.append({"id": "s:" + skill, "kind": "skill", "label": skill, "strength": round(support.get(skill, 0), 3)})
    opportunities = []
    for role in roles:
        required = {skill.lower() for skill in role["skills"]}
        covered = required & {s for s in skills if support.get(s,0)>=.5}
        if not (required & skills):
            continue
        node_id = "r:" + role["id"]
        nodes.append({"id": node_id, "kind": "role", "label": role["label"], "required_skills": sorted(required)})
        for skill in sorted(covered):
            edges.append({"from": "s:" + skill, "to": node_id, "weight": round(.2 + .8 * support.get(skill, 0), 3), "relation": "transfers_to"})
        opportunities.append({"id": role["id"], "label": role["label"], "coverage": round(len(covered) / max(1, len(required)), 3), "evidence_strength": round(sum(support.get(skill, 0) for skill in covered) / max(1, len(required)), 3), "transferable_skills": sorted(covered), "missing_skills": sorted(required - covered)})
    # Personalized PageRank on the real topology (including reverse links), not
    # a string-matching score relabelled as a graph model.
    ids = [node["id"] for node in nodes]
    adjacency = {node: [] for node in ids}
    for edge in edges:
        adjacency[edge["from"]].append((edge["to"], edge["weight"]))
        adjacency[edge["to"]].append((edge["from"], edge["weight"]))
    if ids:
        seeds = {node: max(.01, float(nodes[i].get("strength", .7 if node.startswith("e:") else .01))) for i, node in enumerate(ids)}
        z = sum(seeds.values())
        prior = {node: seeds[node] / z for node in ids}
        rank = prior.copy()
        for _ in range(40):
            following = {node: .15 * prior[node] for node in ids}
            dangling = 0
            for node, destinations in adjacency.items():
                total = sum(weight for _, weight in destinations)
                if total:
                    for destination, weight in destinations:
                        following[destination] += .85 * rank[node] * weight / total
                else:
                    dangling += .85 * rank[node]
            for node in ids:
                following[node] += dangling * prior[node]
            rank = following
        for opportunity in opportunities:
            opportunity["graph_score"] = round(rank.get("r:" + opportunity["id"], 0), 6)
        opportunities.sort(key=lambda item: (-item["evidence_strength"], -item["graph_score"], -item["coverage"], item["id"]))
    from intelligence.graph_neural import infer
    try:
        neural=infer({'nodes':nodes,'edges':edges})
    except (ValueError, OSError, KeyError):
        neural={'status':'model_integrity_unavailable','version':'typed-graphsage-1.0.0','nodes':[],
                'automatic_grade_promotion':False,'automatic_skill_verification':False}
    if neural['status']=='trained':
        learned={node['id']:node['routing_score'] for node in neural['nodes']}
        for opportunity in opportunities:
            opportunity['pagerank_baseline']=opportunity.get('graph_score',0)
            opportunity['neural_routing_score']=learned.get('r:'+opportunity['id'],0)
            opportunity['graph_score']=opportunity['neural_routing_score']
        # A learned surrogate never overrides missing evidence or role requirements.
        opportunities.sort(key=lambda item:(-item['evidence_strength'],-item['coverage'],-item['graph_score'],item['id']))
    return {"version": GRAPH_VERSION, "nodes": nodes, "edges": edges, "opportunities": opportunities[:8], "evidence": visible, "evidence_inventory": evidence, "neural":neural,"algorithm": "typed-graphsage-with-auditable-evidence" if neural['status']=='trained' else 'personalized-pagerank-fallback', "sensitive_features_used": []}


def career_route(payload: dict) -> dict:
    graph = proof_graph(payload)
    preferences = payload.get("preferences", {})
    target = preferences.get("target_role", "")
    by_id = {role["id"]: role for role in payload.get("roles", [])}
    options = [option for option in graph["opportunities"] if not by_id.get(option["id"], {}).get("leadership_level") or preferences.get("growth")=="leadership" and float(payload.get("features",{}).get("experience_years",0))>=5]
    options.sort(key=lambda item:(-item["coverage"],-item["evidence_strength"],-item["graph_score"],item["id"]))
    chosen = next((item for item in options if item["id"] == target), options[0] if options else None)
    if target:
        role = next((r for r in payload.get("roles", []) if r["id"] == target), None)
        if role:
            available = {n["label"].lower() for n in graph["nodes"] if n.get("kind")=="skill" and float(n.get("strength",0))>=.5}
            required = {s.lower() for s in role["skills"]}
            chosen = {"id": role["id"], "label": role["label"], "coverage": len(available & required) / max(1,len(required)), "transferable_skills": sorted(available & required), "missing_skills": sorted(required - available)}
    label = chosen["label"] if chosen else "Первый профессиональный проект"
    missing = chosen["missing_skills"] if chosen else ["Python", "SQL"]
    weekly_hours = min(20, max(2, float(preferences.get("weekly_hours", 5))))
    milestones = [
        {"day": 14, "title": "Проверить направление", "actions": [f"Выберите целевую роль: {label}", "Разберите 5 требований актуальных вакансий", f"Выделите {int(weekly_hours)} часов в неделю на небольшой проект"], "deliverable": "Описание цели и демонстрация первого решения", "status": "planned"},
        {"day": 30, "title": "Создать проверяемое доказательство", "actions": ["Выполните практическую задачу в ProofLab", "Добавьте тесты, README и разбор принятых решений", "Закройте пробелы: " + ", ".join(missing[:3])], "deliverable": "Proof pack: код, тесты, review, объяснение", "status": "planned"},
        {"day": 90, "title": "Проверить маршрут на рынке", "actions": ["Сравните условия 5 релевантных предложений", "Обновите целевое резюме проверенными результатами", "Повторите Horizon и сравните сценарии"], "deliverable": "Целевое резюме и измеримый план поиска", "status": "planned"},
    ]
    style = []
    for key, labels in {"collaboration": {"team": "Важны совместные решения и обратная связь", "independent": "Важны автономия и ясные границы ответственности"}, "pace": {"stable": "Предпочтителен предсказуемый темп", "dynamic": "Интересны разнообразные задачи"}, "growth": {"expert": "Приоритет — профессиональная глубина", "leadership": "Интересны координация и управление", "explore": "Приоритет — проба новых направлений"}}.items():
        if preferences.get(key) in labels:
            style.append(labels[preferences[key]])
    effect = horizon({"mode":"candidate","features":payload["features"],"changes":{"proof_gain":.2},"explain":False}) if payload.get("features") else None
    return {"version": VERSION, "target": chosen, "alternatives": options[:3], "milestones": milestones, "working_preferences": style, "psychological_type_inferred": False, "preferences_source": "voluntary-self-report", "next_question": "Какие задачи придают вам энергию, а какие вы хотели бы встречать реже?", "effects": effect, "graph": graph}


def strategy(payload: dict) -> dict:
    items = payload.get("vacancies", [])
    if len(items) > 50:
        raise ValueError("vacancy_limit")
    budget = number(payload, "extra_budget", 0, 0, 100000000)
    rows = []
    for item in items:
        base = horizon({"mode": "employer", "features": item["features"], "trials": 256, "explain": False})
        improved = horizon({"mode": "employer", "features": item["features"], "changes": {"response_days": 1, "interview_stages": 2}, "trials": 256, "explain": False})
        reward = horizon({"mode": "employer", "features": item["features"], "changes": {"reward_change_percent": 10, "response_days": 1, "interview_stages": 2}, "trials": 256, "explain": False})
        before = base["scenario"]["median_days"]
        after = improved["scenario"]["median_days"]
        cost = round(item["salary"] * .1)
        gain = max(0, (after or 0) - (reward["scenario"]["median_days"] or after or 0))
        rows.append({"vacancy_id": item["id"], "title": item["title"], "median_days": before, "process_days": after, "reward_days": reward["scenario"]["median_days"], "completion_probability": base["scenario"]["completion_probability"], "extra_monthly_cost": cost, "gain_per_1000": gain / max(1, cost) * 1000, "allocated": False, "empty_market": base["empty_market"], "bottlenecks": base["bottlenecks"]})
    # Deterministic marginal-benefit allocation, never recommending cuts.
    remaining = budget
    for row in sorted(rows, key=lambda row: (-row["gain_per_1000"], row["vacancy_id"])):
        if row["gain_per_1000"] > 0 and 0 < row["extra_monthly_cost"] <= remaining:
            row["allocated"] = True
            remaining -= row["extra_monthly_cost"]
    return {"version": VERSION, "vacancies": rows, "budget": budget, "allocated_budget": round(budget - remaining), "remaining_budget": round(remaining), "method": "marginal-benefit", "priority": sorted(rows, key=lambda row: (row["completion_probability"], -(row["median_days"] or 999)))[:5], "recommendations": ["Дайте кандидату ответ в течение рабочего дня", "Объедините повторяющиеся этапы в два содержательных интервью", "Инвестируйте бюджет в дефицитные вакансии с максимальным ожидаемым эффектом"]}
