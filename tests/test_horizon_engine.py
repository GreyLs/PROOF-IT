"""Small functional/statistical checks; deliberately not a capacity/load test."""
import copy
import math

import pytest

from intelligence import arena
from intelligence.engine import career_route, horizon, proof_graph, strategy
from ml_time_forecasting.service import load_models


@pytest.fixture(scope="module", autouse=True)
def models():
    load_models()


EMPLOYER = {"relevant_candidates": 80, "salary_competitiveness": .9, "company_rating": 4, "stack_complexity": 5, "skill_coverage": .65, "seniority_pressure": 1, "remote_flexibility": .65}
CANDIDATE = {"relevant_vacancies": 50, "salary_alignment": .8, "skill_match": .6, "profile_completeness": .7, "qualification_signal": 0, "experience_years": 3, "application_activity": 5, "remote_flexibility": .65}


@pytest.mark.parametrize("mode,features", [("employer", EMPLOYER), ("candidate", CANDIDATE)])
def test_no_intervention_is_exact_baseline(mode, features):
    result = horizon({"mode": mode, "features": features, "explain": False})
    assert result["baseline"] == result["scenario"]
    assert result["gain_days"] == 0


@pytest.mark.parametrize("mode,features", [("employer", EMPLOYER), ("candidate", CANDIDATE)])
def test_horizon_determinism_intervals_and_cdf(mode, features):
    payload = {"mode": mode, "features": features, "changes": {"response_days": 1, "interview_stages": 2}, "explain": False}
    result = horizon(payload)
    assert result == horizon(payload)
    assert result["scenario"]["p10_days"] <= result["scenario"]["median_days"] <= result["scenario"]["p90_days"]
    curve = result["scenario"]["curve"]
    assert [point["probability"] for point in curve] == sorted(point["probability"] for point in curve)
    assert result["scenario"]["completion_probability"] >= result["baseline"]["completion_probability"]
    assert result["gain_days"] >= 0


def test_empty_market_has_no_success_or_invented_median():
    result = horizon({"mode": "employer", "features": {**EMPLOYER, "relevant_candidates": 0}, "explain": False})
    assert result["empty_market"]
    assert result["baseline"]["median_days"] is None
    assert result["baseline"]["completion_probability"] == 0


@pytest.mark.parametrize("changes", [{"reward_change_percent": -10}, {"response_days": 0}, {"interview_stages": 100}, {"flexibility": math.nan}, {"proof_gain": True}])
def test_invalid_or_salary_decrease_rejected(changes):
    with pytest.raises(ValueError):
        horizon({"mode": "employer", "features": EMPLOYER, "changes": changes})


def test_graph_hides_disputed_evidence_and_has_actual_edges():
    p = {"skills": ["Python"], "evidence": [{"id": "good", "title": "Executed code", "skills": ["Python"], "status": "executed", "weight": .8}, {"id": "hidden", "title": "Private", "skills": ["SQL"], "status": "executed", "weight": 1, "hidden": True}], "roles": [{"id": "backend", "label": "Backend", "skills": ["Python", "SQL"]}]}
    graph = proof_graph(p)
    assert any(e["from"] == "e:good" for e in graph["edges"])
    assert not any(n["id"] == "e:hidden" for n in graph["nodes"])
    assert graph["opportunities"][0]["graph_score"] > 0
    assert graph["sensitive_features_used"] == []
    assert graph["opportunities"][0]["coverage"] == .5


def test_career_respects_explicit_target_and_only_voluntary_preferences():
    result = career_route({"skills": ["Python"], "evidence": [], "roles": [{"id": "sql", "label": "SQL Analyst", "skills": ["SQL"]}], "preferences": {"target_role": "sql", "growth": "expert", "pace": "stable"}})
    assert result["target"]["id"] == "sql"
    assert [m["day"] for m in result["milestones"]] == [14, 30, 90]
    assert result["psychological_type_inferred"] is False
    assert len(result["working_preferences"]) == 2


def test_career_does_not_infer_leadership_from_technical_skill_overlap():
    result=career_route({"skills":["Python"],"evidence":[],"roles":[{"id":"lead","label":"Team lead","skills":["Python"],"leadership_level":"team"},{"id":"backend","label":"Backend","skills":["Python","SQL"]}],"preferences":{"growth":"expert"}})
    assert result["target"]["id"]=="backend"
    assert all(option["id"]!='lead' for option in result["alternatives"])


def test_portfolio_allocation_never_spends_over_budget():
    result = strategy({"vacancies": [{"id": "one", "title": "Backend", "features": EMPLOYER, "salary": 200000}, {"id": "two", "title": "Backend 2", "features": EMPLOYER, "salary": 300000}], "extra_budget": 25000})
    assert 0 <= result["allocated_budget"] <= 25000
    assert result["allocated_budget"] + result["remaining_budget"] == 25000
    assert all(row["extra_monthly_cost"] >= 0 for row in result["vacancies"])


def test_adaptive_replay_rejected_and_stops():
    contract = arena.create({"kind": "adaptive", "seed": 12})
    for i in range(12):
        public = arena.public_contract(contract)
        assert "bank" not in public and "answer" not in (public.get("question") or {})
        current = arena.next_item(contract)
        if current is None:
            break
        result = arena.step({"contract": contract, "question_id": current["id"], "answer": current["answer"]})
        with pytest.raises(ValueError):
            arena.step({"contract": result["contract"], "question_id": current["id"], "answer": 0})
        contract = result["contract"]
    assert result["completed"]
    assert result["result"]["grade_changed"] is False
    assert result["result"]["score"] == 100
    assert 6 <= result["result"]["questions"] <= 12


@pytest.mark.parametrize("kind", ["python", "sql", "typescript", "incident", "design", "review"])
def test_arena_does_not_publish_hidden_contract(kind):
    contract = arena.create({"kind": kind, "seed": 99})
    assert "hidden_tests" not in arena.public_contract(contract)
    assert "reference_solution" not in arena.public_contract(contract)
    assert contract == arena.create({"kind": kind, "seed": 99})
