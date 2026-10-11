//! Intelligence domain: ownership, evidence controls, ledger and durable jobs.
//! Stateless workers lease jobs with SKIP LOCKED and fence completion by worker
//! id. Computation and code execution live in independent internal services.
use crate::{
    AppState,
    auth::{Actor, new_id},
    error::{AppError, Result},
};
use axum::{
    Json, Router,
    extract::{Path, State},
    routing::{get, post},
};
use serde::Deserialize;
use serde_json::{Value, json};
use std::time::Duration;

const VERSION: &str = "horizon-1.0.0";

pub fn routes() -> Router<AppState> {
    Router::new()
        .route("/horizon", post(start_horizon))
        .route("/jobs", get(jobs))
        .route("/jobs/{id}", get(job))
        .route("/preferences", get(preferences).put(save_preferences))
        .route("/graph", get(graph))
        .route("/graph/candidate/{id}", get(candidate_graph))
        .route("/evidence/{id}", axum::routing::put(control_evidence))
        .route("/career-route", post(start_career))
        .route("/strategy", post(start_strategy))
        .route("/match", post(match_explanation))
        .route("/decisions", get(decisions))
        .route("/decisions/{id}/dispute", post(dispute))
        .route("/quality", get(quality))
        .route("/outcomes", post(outcome))
        .route("/arena", get(arena_list).post(arena_create))
        .route("/arena/{id}/run", post(arena_run))
        .route("/arena/{id}/submit", post(arena_submit))
        .route("/arena/{id}/answer", post(arena_answer))
        .nest("/assessment", crate::professional::routes())
        .nest("/evidence-lab", crate::evidence::routes())
        .nest("/providers", crate::providers::routes())
        .nest("/research-lab", crate::research_lab::routes())
}

pub(crate) async fn compute(payload: &Value) -> Result<Value> {
    let token = crate::config::secret("INTELLIGENCE_TOKEN")
        .or_else(|_| {
            std::fs::read_to_string("runtime/intelligence.secret").map_err(anyhow::Error::from)
        })
        .map_err(|_| AppError::unavailable("Horizon временно недоступен"))?;
    let url = std::env::var("INTELLIGENCE_URL").unwrap_or_else(|_| "http://127.0.0.1:8092".into());
    let response = reqwest::Client::builder()
        .no_proxy()
        .timeout(Duration::from_secs(30))
        .build()
        .map_err(|_| AppError::unavailable("Horizon временно недоступен"))?
        .post(format!("{url}/operation"))
        .bearer_auth(token.trim())
        .json(payload)
        .send()
        .await
        .map_err(|_| AppError::unavailable("Horizon временно недоступен"))?;
    if response.status().as_u16() == 422 {
        return Err(AppError::bad("Проверьте параметры сценария"));
    }
    if !response.status().is_success() {
        return Err(AppError::unavailable("Horizon временно недоступен"));
    }
    response
        .json()
        .await
        .map_err(|_| AppError::unavailable("Не удалось прочитать расчёт"))
}

pub(crate) async fn record(
    tx: &mut sqlx::Transaction<'_, sqlx::Postgres>,
    owner: &str,
    kind: &str,
    input: &Value,
    result: &Value,
) -> Result<String> {
    let id = new_id("HD");
    let input_hash = crate::auth::hash_token(&input.to_string());
    sqlx::query("INSERT INTO intelligence.decisions(id,user_id,kind,version,features,result,input_hash) VALUES($1,$2,$3,$4,$5,$6,$7)")
        .bind(&id).bind(owner).bind(kind).bind(VERSION).bind(input).bind(result).bind(input_hash).execute(&mut **tx).await?;
    sqlx::query("INSERT INTO intelligence.events(user_id,topic,payload) VALUES($1,$2,$3)")
        .bind(owner)
        .bind(format!("{kind}.completed"))
        .bind(json!({"decision_id":id}))
        .execute(&mut **tx)
        .await?;
    Ok(id)
}

pub(crate) async fn enqueue(
    s: &AppState,
    actor: &Actor,
    kind: &str,
    input: Value,
    request_key: Option<String>,
) -> Result<Json<Value>> {
    crate::security::throttle(s, &format!("intelligence-jobs:{}", actor.id), 60).await?;
    let key = request_key.unwrap_or_else(|| new_id("IK"));
    if key.len() > 100 || key.is_empty() {
        return Err(AppError::bad("Некорректный ключ запроса"));
    }
    let mut tx = s.db.begin().await?;
    let _: String = sqlx::query_scalar("SELECT id FROM users WHERE id=$1 FOR UPDATE")
        .bind(&actor.id)
        .fetch_one(&mut *tx)
        .await?;
    let existing: Option<(String, String, String)> = sqlx::query_as(
        "SELECT id,status,kind FROM intelligence.jobs WHERE user_id=$1 AND idempotency_key=$2",
    )
    .bind(&actor.id)
    .bind(&key)
    .fetch_optional(&mut *tx)
    .await?;
    if let Some((id, status, previous_kind)) = existing {
        if previous_kind != kind {
            return Err(AppError::conflict(
                "Этот ключ уже использован другим действием",
            ));
        }
        if status != "failed" {
            tx.commit().await?;
            return Ok(Json(json!({"job_id":id,"status":status})));
        }
    }
    let active: i64 = sqlx::query_scalar("SELECT count(*) FROM intelligence.jobs WHERE user_id=$1 AND status IN ('queued','running')").bind(&actor.id).fetch_one(&mut *tx).await?;
    if active >= 5 {
        return Err(AppError::conflict(
            "Дождитесь завершения ваших текущих расчётов",
        ));
    }
    let id: String = sqlx::query_scalar("INSERT INTO intelligence.jobs(id,user_id,kind,input,idempotency_key) VALUES($1,$2,$3,$4,$5) ON CONFLICT(user_id,idempotency_key) DO UPDATE SET input=CASE WHEN intelligence.jobs.status='failed' THEN EXCLUDED.input ELSE intelligence.jobs.input END,attempts=CASE WHEN intelligence.jobs.status='failed' THEN 0 ELSE intelligence.jobs.attempts END,status=CASE WHEN intelligence.jobs.status='failed' THEN 'queued' ELSE intelligence.jobs.status END,updated_at=now() RETURNING id")
        .bind(new_id("HJ")).bind(&actor.id).bind(kind).bind(input).bind(key).fetch_one(&mut *tx).await?;
    tx.commit().await?;
    Ok(Json(json!({"job_id":id,"status":"queued"})))
}

#[derive(Deserialize)]
pub struct HorizonInput {
    entity_id: String,
    #[serde(default)]
    changes: Value,
    idempotency_key: Option<String>,
}
pub async fn start_horizon(
    State(s): State<AppState>,
    a: Actor,
    Json(p): Json<HorizonInput>,
) -> Result<Json<Value>> {
    let features = if a.role == "employer" {
        crate::forecasting::vacancy_features(&s, &a, &p.entity_id).await?
    } else {
        crate::forecasting::candidate_features(&s, &a, &p.entity_id).await?
    };
    if !p.changes.is_object() && !p.changes.is_null() {
        return Err(AppError::bad("Некорректные параметры"));
    }
    enqueue(&s, &a, "horizon", json!({"operation":"horizon","mode":a.role,"features":features,"changes":if p.changes.is_null(){json!({})}else{p.changes},"entity_id":p.entity_id}), p.idempotency_key).await
}
pub async fn jobs(State(s): State<AppState>, a: Actor) -> Result<Json<Value>> {
    let items: Vec<Value> = sqlx::query_scalar("SELECT to_jsonb(j)-'input'-'worker_id'-'idempotency_key' FROM intelligence.jobs j WHERE user_id=$1 ORDER BY created_at DESC LIMIT 20").bind(&a.id).fetch_all(&s.db).await?;
    Ok(Json(json!({"items":items})))
}
pub async fn job(
    State(s): State<AppState>,
    a: Actor,
    Path(id): Path<String>,
) -> Result<Json<Value>> {
    let value: Option<Value> = sqlx::query_scalar("SELECT to_jsonb(j)-'input'-'worker_id'-'idempotency_key' FROM intelligence.jobs j WHERE id=$1 AND user_id=$2").bind(id).bind(a.id).fetch_optional(&s.db).await?;
    Ok(Json(value.ok_or_else(AppError::missing)?))
}
pub async fn preferences(State(s): State<AppState>, a: Actor) -> Result<Json<Value>> {
    a.require("candidate")?;
    let value: Option<Value> =
        sqlx::query_scalar("SELECT value FROM intelligence.preferences WHERE user_id=$1")
            .bind(a.id)
            .fetch_optional(&s.db)
            .await?;
    Ok(Json(json!({"preferences":value.unwrap_or(json!({}))})))
}
pub async fn save_preferences(
    State(s): State<AppState>,
    a: Actor,
    Json(p): Json<Value>,
) -> Result<Json<Value>> {
    a.require("candidate")?;
    let Some(map) = p.as_object() else {
        return Err(AppError::bad("Проверьте предпочтения"));
    };
    if map.keys().any(|key| {
        ![
            "target_role",
            "weekly_hours",
            "collaboration",
            "pace",
            "growth",
        ]
        .contains(&key.as_str())
    }) {
        return Err(AppError::bad(
            "Используйте только добровольные рабочие предпочтения",
        ));
    }
    for (key, allowed) in [
        ("collaboration", vec!["", "team", "independent"]),
        ("pace", vec!["", "stable", "dynamic"]),
        ("growth", vec!["", "expert", "leadership", "explore"]),
    ] {
        if p.get(key)
            .is_some_and(|v| !allowed.contains(&v.as_str().unwrap_or("invalid")))
        {
            return Err(AppError::bad("Проверьте предпочтения"));
        }
    }
    if p.get("target_role").is_some_and(|v| {
        !v.as_str()
            .is_some_and(|t| t.is_empty() || crate::matching::valid_spec(t))
    }) {
        return Err(AppError::bad("Выберите направление"));
    }
    if p.get("weekly_hours").is_some_and(|v| {
        !v.as_f64()
            .is_some_and(|n| n.is_finite() && (2.0..=20.0).contains(&n))
    }) {
        return Err(AppError::bad("От 2 до 20 часов в неделю"));
    }
    sqlx::query("INSERT INTO intelligence.preferences(user_id,value) VALUES($1,$2) ON CONFLICT(user_id) DO UPDATE SET value=EXCLUDED.value,updated_at=now()").bind(&a.id).bind(&p).execute(&s.db).await?;
    Ok(Json(json!({"preferences":p})))
}

async fn graph_input(s: &AppState, candidate: &str, owner: &str, public: bool) -> Result<Value> {
    let resumes: Vec<Value> = sqlx::query_scalar("SELECT jsonb_build_object('id',r.id,'title',r.target_position,'skills',r.skills,'score',r.test_score,'passed',r.qualification_passed,'category_scope',r.category_scope,'status',r.status) FROM intelligence.resume_category_evidence r WHERE r.candidate_id=$1 AND (NOT $2 OR r.employer_eligible) ORDER BY r.id").bind(candidate).bind(public).fetch_all(&s.db).await?;
    let controls: Vec<Value> = sqlx::query_scalar(
        "SELECT to_jsonb(e) FROM intelligence.evidence_controls e WHERE user_id=$1",
    )
    .bind(owner)
    .fetch_all(&s.db)
    .await?;
    let mut evidence = Vec::new();
    let mut skills = std::collections::BTreeSet::new();
    for r in resumes {
        for skill in r["skills"].as_array().unwrap_or(&Vec::new()) {
            if let Some(v) = skill.as_str() {
                skills.insert(v.to_owned());
            }
        }
        evidence.push(json!({"id":format!("resume:{}",r["id"].as_str().unwrap_or("")),"title":r["title"],"skills":r["skills"],"status":"declared","weight":0.0,"score":r["score"],"source":"resume"}));
    }
    let certificates:Vec<Value>=sqlx::query_scalar("SELECT jsonb_build_object('id','cert:'||id,'title','Квалификация: '||specialization||' · '||grade,'skills',skills,'status','verified','weight',0.85,'source','qualification','issued_at',issued_at,'valid_until',valid_until) FROM qualification_certificates q WHERE candidate_id=$1 AND revoked_at IS NULL AND valid_until>now() AND (NOT $2 OR EXISTS(SELECT 1 FROM resume_profiles r WHERE r.id=q.resume_id AND r.visibility='employer_searchable' AND r.status='published')) ORDER BY issued_at DESC LIMIT 100").bind(candidate).bind(public).fetch_all(&s.db).await?;
    evidence.extend(certificates);
    // A task proves its explicit assessed skills, never every declared skill.
    let tasks: Vec<Value> = sqlx::query_scalar("SELECT jsonb_build_object('id','task:'||t.id,'title',t.title,'skills',coalesce(t.contract->'skills','[]'::jsonb),'status','executed','weight',coalesce(t.score,0)::float8/100.0*0.8,'score',t.score,'source','sandbox','issued_at',t.reviewed_at) FROM micro_tasks t WHERE t.candidate_id=$1 AND t.status='reviewed' ORDER BY t.reviewed_at DESC LIMIT 100").bind(candidate).fetch_all(&s.db).await?;
    evidence.extend(tasks);
    let fsp:Vec<Value>=sqlx::query_scalar("SELECT jsonb_build_object('id','fsp:'||p.id,'title','Подтверждённое участие ФСП','skills','[\"Competitive programming\"]'::jsonb,'status','verified','weight',0.35,'source','fsp_registry') FROM fsp_participations p WHERE candidate_id=$1 AND status='verified' ORDER BY verified_at DESC LIMIT 50").bind(candidate).fetch_all(&s.db).await?;
    evidence.extend(fsp);
    let projects:Vec<Value>=sqlx::query_scalar("SELECT jsonb_build_object('id','project:'||d.id,'title','Разбор профессионального проекта','skills','[\"Professional reasoning\"]'::jsonb,'status','reviewed','weight',0.4,'source','expert_dialogue') FROM expert_dialogues d WHERE candidate_id=$1 AND mode='profile' AND status='completed' AND (result->>'decision'='supported' OR project_result->>'decision'='supported') ORDER BY created_at DESC LIMIT 30").bind(candidate).fetch_all(&s.db).await?;
    evidence.extend(projects);
    let arena: Vec<Value> = sqlx::query_scalar("SELECT jsonb_build_object('id','arena:'||a.id,'title',a.contract->>'title','skills',coalesce(a.contract->'skills',a.result->'skills','[]'::jsonb),'status',CASE WHEN a.kind IN ('python','sql','typescript') THEN 'executed' ELSE 'reviewed' END,'weight',coalesce((a.result->>'score')::float8,0)/100.0*CASE WHEN a.kind IN ('python','sql','typescript') THEN 0.8 ELSE 0.4 END,'score',a.result->'score','source','arena','issued_at',a.updated_at) FROM intelligence.arena_attempts a WHERE a.user_id=$1 AND a.status='completed' ORDER BY a.created_at DESC LIMIT 100").bind(owner).fetch_all(&s.db).await?;
    evidence.extend(arena);
    // A confirmed independent integrity decision affects the visual graph as
    // well as the ranking projection. A pending signal alone has no penalty.
    let rejected: Vec<String> = sqlx::query_scalar(
        "SELECT artifact_id FROM intelligence.review_cases WHERE user_id=$1 AND established_violation",
    )
    .bind(owner)
    .fetch_all(&s.db)
    .await?;
    evidence.retain(|e| {
        let id = e["id"].as_str().unwrap_or("");
        let artifact = id
            .strip_prefix("task:")
            .or_else(|| id.strip_prefix("arena:"));
        !artifact.is_some_and(|a| rejected.iter().any(|r| r == a))
    });
    for item in &mut evidence {
        if let Some(control) = controls.iter().find(|c| c["evidence_id"] == item["id"]) {
            item["hidden"] = control["hidden"].clone();
            item["disputed"] = control["disputed"].clone();
        } else {
            item["hidden"] = json!(false);
            item["disputed"] = json!(false);
        }
    }
    if public {
        evidence.retain(|e| e["hidden"] != true && e["disputed"] != true);
    }
    Ok(
        json!({"operation":"graph","skills":skills,"evidence":evidence,"roles":crate::matching::taxonomy()}),
    )
}
pub async fn graph(State(s): State<AppState>, a: Actor) -> Result<Json<Value>> {
    a.require("candidate")?;
    let input = graph_input(&s, &a.subject_id, &a.id, false).await?;
    Ok(Json(compute(&input).await?))
}
pub async fn candidate_graph(
    State(s): State<AppState>,
    a: Actor,
    Path(id): Path<String>,
) -> Result<Json<Value>> {
    a.verified_employer(&s).await?;
    let owner: Option<String> = sqlx::query_scalar("SELECT coalesce((SELECT u.id FROM users u WHERE u.subject_id=c.id AND u.role='candidate' LIMIT 1),'') FROM candidates c WHERE c.id=$1 AND EXISTS(SELECT 1 FROM intelligence.resume_category_evidence r WHERE r.candidate_id=c.id AND r.employer_eligible)").bind(&id).fetch_optional(&s.db).await?;
    let owner = owner.ok_or_else(AppError::missing)?;
    let input = graph_input(&s, &id, &owner, true).await?;
    let mut result = compute(&input).await?;
    result.as_object_mut().unwrap().remove("opportunities");
    Ok(Json(result))
}
#[derive(Deserialize)]
pub struct EvidenceControl {
    #[serde(default)]
    hidden: bool,
    #[serde(default)]
    disputed: bool,
    #[serde(default)]
    reason: String,
}
pub async fn control_evidence(
    State(s): State<AppState>,
    a: Actor,
    Path(id): Path<String>,
    Json(p): Json<EvidenceControl>,
) -> Result<Json<Value>> {
    a.require("candidate")?;
    if p.reason.chars().count() > 1000 {
        return Err(AppError::bad("Сократите объяснение до 1000 символов"));
    }
    let input = graph_input(&s, &a.subject_id, &a.id, false).await?;
    if !input["evidence"]
        .as_array()
        .is_some_and(|items| items.iter().any(|e| e["id"] == id))
    {
        return Err(AppError::missing());
    }
    sqlx::query("INSERT INTO intelligence.evidence_controls(user_id,evidence_id,hidden,disputed,reason) VALUES($1,$2,$3,$4,$5) ON CONFLICT(user_id,evidence_id) DO UPDATE SET hidden=EXCLUDED.hidden,disputed=EXCLUDED.disputed,reason=EXCLUDED.reason,updated_at=now()")
        .bind(&a.id).bind(&id).bind(p.hidden).bind(p.disputed).bind(p.reason).execute(&s.db).await?;
    Ok(Json(
        json!({"id":id,"hidden":p.hidden,"disputed":p.disputed}),
    ))
}
pub async fn start_career(State(s): State<AppState>, a: Actor) -> Result<Json<Value>> {
    a.require("candidate")?;
    let mut input = graph_input(&s, &a.subject_id, &a.id, false).await?;
    let preferences: Option<Value> =
        sqlx::query_scalar("SELECT value FROM intelligence.preferences WHERE user_id=$1")
            .bind(&a.id)
            .fetch_optional(&s.db)
            .await?;
    input["operation"] = json!("career_route");
    input["preferences"] = preferences.unwrap_or(json!({}));
    let resume:Option<String>=sqlx::query_scalar("SELECT id FROM resume_profiles WHERE candidate_id=$1 AND status<>'archived' ORDER BY (specialization=$2) DESC,created_at LIMIT 1").bind(&a.subject_id).bind(input["preferences"]["target_role"].as_str().unwrap_or("")).fetch_optional(&s.db).await?;
    if let Some(id) = resume {
        input["features"] = crate::forecasting::candidate_features(&s, &a, &id).await?;
    }
    enqueue(&s, &a, "career_route", input, None).await
}
#[derive(Deserialize)]
pub struct StrategyInput {
    #[serde(default)]
    extra_budget: f64,
}
pub async fn start_strategy(
    State(s): State<AppState>,
    a: Actor,
    Json(p): Json<StrategyInput>,
) -> Result<Json<Value>> {
    a.verified_employer(&s).await?;
    if !p.extra_budget.is_finite() || !(0.0..=100000000.0).contains(&p.extra_budget) {
        return Err(AppError::bad("Проверьте бюджет"));
    }
    let vacancies: Vec<(String,String,i32,i32)> = sqlx::query_as("SELECT id,title,salary_from,salary_to FROM vacancies WHERE company_id=$1 AND status='published' ORDER BY id LIMIT 50").bind(&a.subject_id).fetch_all(&s.db).await?;
    let mut items = Vec::new();
    for (id, title, low, high) in vacancies {
        let features = crate::forecasting::vacancy_features(&s, &a, &id).await?;
        items.push(json!({"id":id,"title":title,"salary":(low as f64+high as f64)/2.0,"features":features}));
    }
    enqueue(
        &s,
        &a,
        "strategy",
        json!({"operation":"strategy","vacancies":items,"extra_budget":p.extra_budget}),
        None,
    )
    .await
}
#[derive(Deserialize)]
pub struct MatchInput {
    resume_id: String,
    vacancy_id: String,
}
pub async fn match_explanation(
    State(s): State<AppState>,
    a: Actor,
    Json(p): Json<MatchInput>,
) -> Result<Json<Value>> {
    let resume: Option<Value> = sqlx::query_scalar("SELECT to_jsonb(r)-'about'-'document_id' FROM resume_profiles r JOIN intelligence.resume_category_evidence rg ON rg.id=r.id WHERE r.id=$1 AND (($2='candidate' AND r.candidate_id=$3) OR ($2='employer' AND rg.employer_eligible))").bind(&p.resume_id).bind(&a.role).bind(&a.subject_id).fetch_optional(&s.db).await?;
    let vacancy: Option<Value> = sqlx::query_scalar("SELECT to_jsonb(v) FROM vacancies v WHERE id=$1 AND (($2='employer' AND company_id=$3) OR ($2='candidate' AND status='published'))").bind(&p.vacancy_id).bind(&a.role).bind(&a.subject_id).fetch_optional(&s.db).await?;
    let r = resume.ok_or_else(AppError::missing)?;
    let v = vacancy.ok_or_else(AppError::missing)?;
    if a.role == "employer" {
        a.verified_employer(&s).await?;
    }
    let skills: Vec<String> = r["skills"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(|x| x.as_str().map(|s| s.to_lowercase()))
        .collect();
    let required: Vec<String> = v["skills"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(|x| x.as_str().map(|s| s.to_lowercase()))
        .collect();
    let matched: Vec<_> = required
        .iter()
        .filter(|x| skills.contains(x))
        .cloned()
        .collect();
    let missing: Vec<_> = required
        .iter()
        .filter(|x| !skills.contains(x))
        .cloned()
        .collect();
    let coverage = if required.is_empty() {
        1.0
    } else {
        matched.len() as f64 / required.len() as f64
    };
    let salary_ok =
        r["expected_salary"].as_i64().unwrap_or(0) <= v["salary_to"].as_i64().unwrap_or(0);
    let same_role = r["specialization"] == v["specialization"];
    let result = json!({"skill_coverage":coverage,"matched_skills":matched,"missing_skills":missing,"same_direction":same_role,"salary_compatible":salary_ok,"employer_view":{"strengths":matched,"next_step":if missing.is_empty(){"Обсудите рабочие условия и отправьте предложение"}else{"Проверьте недостающие навыки адресным заданием"}},"candidate_view":{"conditions":if salary_ok{"Вилка покрывает текущие ожидания"}else{"Вилка ниже ожиданий: обсудите условия до интервью"},"next_step":"Сравните формат работы, задачи и скорость обратной связи"},"sensitive_features_used":[]});
    let mut tx = s.db.begin().await?;
    let decision=record(&mut tx,&a.id,"match",&json!({"skill_coverage":coverage,"same_direction":same_role,"salary_compatible":salary_ok}),&result).await?;
    tx.commit().await?;
    Ok(Json(json!({"decision_id":decision,"explanation":result})))
}
pub async fn decisions(State(s): State<AppState>, a: Actor) -> Result<Json<Value>> {
    let items:Vec<Value>=sqlx::query_scalar("SELECT to_jsonb(d)-'features' FROM intelligence.decisions d WHERE user_id=$1 ORDER BY created_at DESC LIMIT 30").bind(a.id).fetch_all(&s.db).await?;
    Ok(Json(json!({"items":items})))
}
#[derive(Deserialize)]
pub struct Dispute {
    reason: String,
}
pub async fn dispute(
    State(s): State<AppState>,
    a: Actor,
    Path(id): Path<String>,
    Json(p): Json<Dispute>,
) -> Result<Json<Value>> {
    if !(10..=1000).contains(&p.reason.chars().count()) {
        return Err(AppError::bad("Объясните причину: от 10 до 1000 символов"));
    }
    let n=sqlx::query("UPDATE intelligence.decisions SET status='disputed',dispute_reason=$3 WHERE id=$1 AND user_id=$2").bind(&id).bind(&a.id).bind(p.reason).execute(&s.db).await?;
    if n.rows_affected() == 0 {
        return Err(AppError::missing());
    }
    Ok(Json(json!({"id":id,"status":"disputed"})))
}
pub async fn quality(State(s): State<AppState>, a: Actor) -> Result<Json<Value>> {
    let rows:Vec<Value>=sqlx::query_scalar("SELECT jsonb_build_object('kind',kind,'count',count(*),'disputed',count(*) FILTER(WHERE status='disputed'),'versions',array_agg(DISTINCT version)) FROM intelligence.decisions WHERE user_id=$1 GROUP BY kind").bind(&a.id).fetch_all(&s.db).await?;
    let accuracy:Value=sqlx::query_scalar("SELECT jsonb_build_object('outcomes',count(*),'mae_days',avg(abs(actual_days-predicted_days)),'rmse_days',sqrt(avg(power(actual_days-predicted_days,2))),'interval_coverage',avg(CASE WHEN interval_low IS NOT NULL AND interval_high IS NOT NULL THEN CASE WHEN actual_days BETWEEN interval_low AND interval_high THEN 1.0 ELSE 0.0 END END)) FROM intelligence.outcomes WHERE user_id=$1").bind(&a.id).fetch_one(&s.db).await?;
    Ok(Json(
        json!({"segments":rows,"forecast_accuracy":accuracy,"sensitive_features_used":[],"scenario_probabilities_calibrated":false,"independent_pilot_completed":false,"version":VERSION}),
    ))
}
#[derive(Deserialize)]
pub struct Outcome {
    decision_id: String,
    actual_days: f64,
}
pub async fn outcome(
    State(s): State<AppState>,
    a: Actor,
    Json(p): Json<Outcome>,
) -> Result<Json<Value>> {
    if !p.actual_days.is_finite() || !(0.01..=3650.0).contains(&p.actual_days) {
        return Err(AppError::bad("Укажите фактический срок в днях"));
    }
    let result: Option<Value> = sqlx::query_scalar(
        "SELECT result FROM intelligence.decisions WHERE id=$1 AND user_id=$2 AND kind='horizon'",
    )
    .bind(&p.decision_id)
    .bind(&a.id)
    .fetch_optional(&s.db)
    .await?;
    let r = result.ok_or_else(AppError::missing)?;
    sqlx::query("INSERT INTO intelligence.outcomes(decision_id,user_id,actual_days,predicted_days,interval_low,interval_high) VALUES($1,$2,$3,$4,$5,$6) ON CONFLICT(decision_id) DO UPDATE SET actual_days=EXCLUDED.actual_days").bind(&p.decision_id).bind(&a.id).bind(p.actual_days).bind(r["scenario"]["median_days"].as_f64()).bind(r["scenario"]["p10_days"].as_f64()).bind(r["scenario"]["p90_days"].as_f64()).execute(&s.db).await?;
    Ok(Json(json!({"recorded":true})))
}

#[derive(Deserialize)]
pub struct ArenaCreate {
    kind: String,
}
pub async fn arena_create(
    State(s): State<AppState>,
    a: Actor,
    Json(p): Json<ArenaCreate>,
) -> Result<Json<Value>> {
    a.require("candidate")?;
    crate::security::throttle(&s, &format!("arena-start:{}", a.id), 12).await?;
    let id = new_id("AR");
    let seed = u32::from_le_bytes(uuid::Uuid::new_v4().as_bytes()[..4].try_into().unwrap());
    let mut contract =
        compute(&json!({"operation":"arena_create","kind":p.kind,"seed":seed})).await?;
    if ["python", "sql", "typescript"].contains(&p.kind.as_str()) {
        let mut validation = contract.clone();
        let mut tests = contract["public_tests"]
            .as_array()
            .cloned()
            .unwrap_or_default();
        tests.extend(
            contract["hidden_tests"]
                .as_array()
                .cloned()
                .unwrap_or_default(),
        );
        validation["public_tests"] = json!(tests);
        let checked = crate::workbench::ai(
            &s,
            json!({"operation":"run","contract":validation,"code":contract["reference_solution"]}),
        )
        .await?;
        if checked["passed"] != checked["total"] || checked["total"].as_i64().unwrap_or(0) < 5 {
            return Err(AppError::unavailable(
                "Эталон задания не прошёл проверку; выберите другой формат",
            ));
        }
        contract["reference_validation"] =
            json!({"passed":checked["passed"],"total":checked["total"]});
    }
    let public = compute(&json!({"operation":"arena_public","contract":contract})).await?;
    sqlx::query(
        "INSERT INTO intelligence.arena_attempts(id,user_id,kind,contract) VALUES($1,$2,$3,$4)",
    )
    .bind(&id)
    .bind(&a.id)
    .bind(p.kind)
    .bind(&contract)
    .execute(&s.db)
    .await?;
    Ok(Json(
        json!({"id":id,"contract":public,"status":"active","revision":0}),
    ))
}
pub async fn arena_list(State(s): State<AppState>, a: Actor) -> Result<Json<Value>> {
    a.require("candidate")?;
    let rows:Vec<Value>=sqlx::query_scalar("SELECT to_jsonb(a)-'submission' FROM intelligence.arena_attempts a WHERE user_id=$1 ORDER BY created_at DESC LIMIT 20").bind(&a.id).fetch_all(&s.db).await?;
    let mut items = Vec::new();
    for mut row in rows {
        row["contract"] =
            compute(&json!({"operation":"arena_public","contract":row["contract"]})).await?;
        items.push(row);
    }
    Ok(Json(json!({"items":items})))
}
#[derive(Deserialize)]
pub struct ArenaCode {
    code: String,
}
async fn owned_arena(s: &AppState, a: &Actor, id: &str) -> Result<Value> {
    a.require("candidate")?;
    sqlx::query_scalar(
        "SELECT to_jsonb(a) FROM intelligence.arena_attempts a WHERE id=$1 AND user_id=$2",
    )
    .bind(id)
    .bind(&a.id)
    .fetch_optional(&s.db)
    .await?
    .ok_or_else(AppError::missing)
}
pub async fn arena_run(
    State(s): State<AppState>,
    a: Actor,
    Path(id): Path<String>,
    Json(p): Json<ArenaCode>,
) -> Result<Json<Value>> {
    let row = owned_arena(&s, &a, &id).await?;
    if row["status"] != "active" {
        return Err(AppError::conflict("Практика уже завершена"));
    }
    if p.code.len() > 20000 {
        return Err(AppError::bad("Решение слишком большое"));
    }
    if !["python", "sql", "typescript"].contains(&row["kind"].as_str().unwrap_or("")) {
        return Err(AppError::bad("Для этого формата отправьте текст на ревью"));
    }
    crate::security::throttle(&s, &format!("arena-run:{}", a.id), 40).await?;
    Ok(Json(
        crate::workbench::ai(
            &s,
            json!({"operation":"run","code":p.code,"contract":row["contract"]}),
        )
        .await?,
    ))
}
pub async fn arena_submit(
    State(s): State<AppState>,
    a: Actor,
    Path(id): Path<String>,
    Json(p): Json<ArenaCode>,
) -> Result<Json<Value>> {
    let row = owned_arena(&s, &a, &id).await?;
    if row["status"] != "active" {
        return Err(AppError::conflict("Практика уже завершена"));
    }
    if !(10..=20000).contains(&p.code.len()) {
        return Err(AppError::bad("Решение: от 10 до 20 000 символов"));
    }
    if row["kind"] == "adaptive" {
        return Err(AppError::bad("Ответьте на текущий вопрос"));
    }
    let kind = if ["python", "sql", "typescript"].contains(&row["kind"].as_str().unwrap_or("")) {
        "submit"
    } else {
        "arena_review"
    };
    enqueue(
        &s,
        &a,
        "arena",
        json!({"operation":kind,"contract":row["contract"],"code":p.code,"arena_id":id}),
        Some(format!("arena:{id}")),
    )
    .await
}
#[derive(Deserialize)]
pub struct ArenaAnswer {
    question_id: String,
    answer: f64,
    revision: i32,
}
pub async fn arena_answer(
    State(s): State<AppState>,
    a: Actor,
    Path(id): Path<String>,
    Json(p): Json<ArenaAnswer>,
) -> Result<Json<Value>> {
    let row = owned_arena(&s, &a, &id).await?;
    if row["status"] != "active" || row["revision"] != p.revision {
        return Err(AppError::conflict("Этот ответ уже обработан"));
    }
    let result=compute(&json!({"operation":"arena_step","contract":row["contract"],"question_id":p.question_id,"answer":p.answer})).await?;
    let mut tx = s.db.begin().await?;
    let n=sqlx::query("UPDATE intelligence.arena_attempts SET contract=$4,result=$5,status=$6,revision=revision+1,updated_at=now() WHERE id=$1 AND user_id=$2 AND revision=$3 AND status='active'").bind(&id).bind(&a.id).bind(p.revision).bind(&result["contract"]).bind(&result["result"]).bind(if result["completed"]==true{"completed"}else{"active"}).execute(&mut *tx).await?;
    if n.rows_affected() == 0 {
        return Err(AppError::conflict("Этот ответ уже обработан"));
    }
    if result["completed"] == true {
        record(
            &mut tx,
            &a.id,
            "adaptive_practice",
            &json!({"arena_id":id}),
            &result["result"],
        )
        .await?;
    }
    tx.commit().await?;
    Ok(Json(
        json!({"id":id,"contract":result["public"],"result":result["result"],"status":if result["completed"]==true{"completed"}else{"active"},"revision":p.revision+1}),
    ))
}

pub async fn dispatch(s: AppState) {
    tokio::spawn(crate::evidence::weekly_dispatch(s.clone()));
    // A long GPU review must not occupy the only consumer of short numerical
    // jobs. Dedicated lanes retain one AI task at a time on a shared GPU.
    let cpu_state = s.clone();
    tokio::spawn(async move {
        dispatch_lane(cpu_state, false).await;
    });
    dispatch_lane(s, true).await;
}
async fn dispatch_lane(s: AppState, ai_lane: bool) {
    let worker = new_id("HW");
    loop {
        if let Err(e) = dispatch_one(&s, &worker, ai_lane).await {
            tracing::warn!(status=%e.0,"intelligence dispatch unavailable");
        }
        tokio::time::sleep(Duration::from_millis(350)).await;
    }
}
async fn dispatch_one(s: &AppState, worker: &str, ai_lane: bool) -> Result<()> {
    sqlx::query("UPDATE intelligence.jobs SET status='failed',error='Повторные попытки завершения исчерпаны',updated_at=now() WHERE status='running' AND lease_until<now() AND attempts>=3").execute(&s.db).await?;
    let row:Option<(String,String,String,Value,i32)>=sqlx::query_as("UPDATE intelligence.jobs SET status='running',worker_id=$1,lease_until=now()+interval '6 minutes',attempts=attempts+1,updated_at=now() WHERE id=(SELECT id FROM intelligence.jobs WHERE ((status='queued' AND available_at<=now()) OR (status='running' AND lease_until<now())) AND attempts<3 AND ((kind IN ('arena','item_draft'))=$2) ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING id,user_id,kind,input,attempts").bind(worker).bind(ai_lane).fetch_optional(&s.db).await?;
    let Some((id, owner, kind, input, attempts)) = row else {
        return Ok(());
    };
    let response = if kind == "arena" || kind == "item_draft" {
        crate::workbench::ai(s, input.clone()).await
    } else {
        compute(&input).await
    };
    let response = match response {
        Ok(output) if kind == "item_draft" => {
            match compute(&json!({"operation":"item_validate","prompt":output["prompt"],"options":output["options"],"correct":output["correct"],"rationale":output["rationale"]})).await {
                Ok(mut checked) => {checked["execution"]=output["execution"].clone();Ok(checked)}
                Err(e) => Err(e),
            }
        }
        other => other,
    };
    match response {
        Ok(mut output) => {
            if kind == "arena"
                && ["python", "sql", "typescript"]
                    .contains(&input["contract"]["kind"].as_str().unwrap_or(""))
            {
                if let Ok(indicator) = crate::professional::register_code_proof(
                    s,
                    &owner,
                    input["arena_id"].as_str().unwrap_or(""),
                    input["code"].as_str().unwrap_or(""),
                    input["contract"]["kind"].as_str().unwrap_or("python"),
                )
                .await
                {
                    output["integrity"] = indicator;
                }
            }
            let mut tx = s.db.begin().await?;
            let locked:bool=sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM intelligence.jobs WHERE id=$1 AND status='running' AND worker_id=$2 AND lease_until>now() FOR UPDATE)").bind(&id).bind(worker).fetch_one(&mut *tx).await?;
            if !locked {
                return Ok(());
            }
            if kind == "arena" {
                output["skills"] = input["contract"]["skills"].clone();
                sqlx::query("UPDATE intelligence.arena_attempts SET status='completed',submission=$3,result=$4,revision=revision+1,updated_at=now() WHERE id=$1 AND user_id=$2 AND status='active'").bind(input["arena_id"].as_str()).bind(&owner).bind(input["code"].as_str()).bind(&output).execute(&mut *tx).await?;
            }
            if kind == "item_draft" {
                let draft = new_id("PD");
                sqlx::query("INSERT INTO intelligence.item_drafts(id,author_id,specialization,content) VALUES($1,$2,$3,$4)").bind(&draft).bind(&owner).bind(input["specialization"].as_str()).bind(&output).execute(&mut *tx).await?;
                output["draft_id"] = json!(draft);
            }
            // Ledger excludes code, hidden tests and any executable reference.
            let mut ledger_input = input.clone();
            if let Some(map) = ledger_input.as_object_mut() {
                map.remove("contract");
                map.remove("code");
            }
            let decision = record(&mut tx, &owner, &kind, &ledger_input, &output).await?;
            output["decision_id"] = json!(decision);
            sqlx::query("UPDATE intelligence.jobs SET status='done',result=$3,input=input-'code'-'contract',updated_at=now(),lease_until=NULL WHERE id=$1 AND worker_id=$2").bind(&id).bind(worker).bind(output).execute(&mut *tx).await?;
            tx.commit().await?;
        }
        Err(error) => {
            sqlx::query("UPDATE intelligence.jobs SET status=$3,error=$4,worker_id=NULL,lease_until=NULL,available_at=now()+interval '5 seconds',updated_at=now() WHERE id=$1 AND worker_id=$2").bind(&id).bind(worker).bind(if attempts>=3 || error.0.as_u16()==400{"failed"}else{"queued"}).bind("Не удалось завершить расчёт. Проверьте параметры или повторите позже.").execute(&s.db).await?;
        }
    }
    Ok(())
}

pub async fn export_owned(s: &AppState, owner: &str) -> Result<Value> {
    let decisions: Vec<Value> = sqlx::query_scalar(
        "SELECT to_jsonb(d) FROM intelligence.decisions d WHERE user_id=$1 ORDER BY created_at",
    )
    .bind(owner)
    .fetch_all(&s.db)
    .await?;
    let preferences: Option<Value> =
        sqlx::query_scalar("SELECT value FROM intelligence.preferences WHERE user_id=$1")
            .bind(owner)
            .fetch_optional(&s.db)
            .await?;
    let controls: Vec<Value> = sqlx::query_scalar(
        "SELECT to_jsonb(c) FROM intelligence.evidence_controls c WHERE user_id=$1",
    )
    .bind(owner)
    .fetch_all(&s.db)
    .await?;
    let arena:Vec<Value>=sqlx::query_scalar("SELECT to_jsonb(a)-'contract' FROM intelligence.arena_attempts a WHERE user_id=$1 ORDER BY created_at").bind(owner).fetch_all(&s.db).await?;
    let outcomes: Vec<Value> =
        sqlx::query_scalar("SELECT to_jsonb(o) FROM intelligence.outcomes o WHERE user_id=$1")
            .bind(owner)
            .fetch_all(&s.db)
            .await?;
    let professional = crate::professional::export_owned(s, owner).await?;
    let certificates:Vec<Value>=sqlx::query_scalar("SELECT to_jsonb(q) FROM qualification_certificates q JOIN users u ON u.subject_id=q.candidate_id WHERE u.id=$1 ORDER BY q.issued_at").bind(owner).fetch_all(&s.db).await?;
    let passports:Vec<Value>=sqlx::query_scalar("SELECT to_jsonb(p)-'digest' FROM intelligence.passports p WHERE user_id=$1 ORDER BY issued_at").bind(owner).fetch_all(&s.db).await?;
    let reviews: Vec<Value> = sqlx::query_scalar(
        "SELECT to_jsonb(r) FROM intelligence.review_cases r WHERE user_id=$1 ORDER BY created_at",
    )
    .bind(owner)
    .fetch_all(&s.db)
    .await?;
    let followups:Vec<Value>=sqlx::query_scalar("SELECT to_jsonb(f) FROM intelligence.followups f JOIN invitations i ON i.id=f.invitation_id JOIN users u ON (($2='candidate' AND i.candidate_id=u.subject_id) OR ($2='employer' AND i.company_id=u.subject_id)) WHERE u.id=$1 ORDER BY f.due_at").bind(owner).bind(sqlx::query_scalar::<_,String>("SELECT role FROM users WHERE id=$1").bind(owner).fetch_one(&s.db).await?).fetch_all(&s.db).await?;
    Ok(
        json!({"decisions":decisions,"preferences":preferences,"evidence_controls":controls,"arena":arena,"outcomes":outcomes,"professional":professional,"certificates":certificates,"passports":passports,"integrity_reviews":reviews,"followups":followups}),
    )
}
