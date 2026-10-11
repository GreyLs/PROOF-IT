//! Owned assessment sessions, bounded telemetry and controlled item publication.
use crate::{
    AppState,
    auth::{Actor, new_id},
    error::{AppError, Result},
    intelligence::compute,
};
use axum::{
    Json, Router,
    extract::{Path, Query, State},
    http::{HeaderMap, HeaderValue, header},
    response::{IntoResponse, Redirect, Response},
    routing::{get, post},
};
use serde::Deserialize;
use serde_json::{Value, json};

pub fn routes() -> Router<AppState> {
    Router::new()
        .route("/catalog", get(catalog))
        .route("/attempts", get(list).post(start))
        .route("/attempts/{id}/answer", post(answer))
        .route("/attempts/{id}/signals", post(signals))
        .route("/attempts/{id}/abandon", post(abandon))
        .route("/bank", get(bank))
        .route("/drafts", get(drafts).post(draft))
        .route("/drafts/generate", post(generate))
        .route("/drafts/{id}/review", post(review))
        .route("/drafts/{id}/calibrate", post(calibrate))
        .route("/drafts/{id}/activate", post(activate))
        .route("/oidc", get(oidc_status).post(oidc_start))
        .route("/oidc/callback", get(oidc_finish))
        .route("/integrity/code", post(code_integrity))
        .route("/need-preview", post(need_preview))
}
async fn catalog(_a: Actor) -> Result<Json<Value>> {
    Ok(Json(
        compute(&json!({"operation":"professional_catalog"})).await?,
    ))
}
async fn expert(s: &AppState, a: &Actor) -> Result<()> {
    a.verified_employer(s).await?;
    let approved:bool=sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM intelligence.assessment_experts WHERE user_id=$1 AND approved)").bind(&a.id).fetch_one(&s.db).await?;
    if s.demo || approved {
        Ok(())
    } else {
        Err(AppError::forbidden())
    }
}
async fn public_row(mut row: Value) -> Result<Value> {
    row["contract"] =
        compute(&json!({"operation":"professional_public","contract":row["contract"]})).await?;
    Ok(row)
}
async fn list(State(s): State<AppState>, a: Actor) -> Result<Json<Value>> {
    a.require("candidate")?;
    let rows:Vec<Value>=sqlx::query_scalar("SELECT to_jsonb(a) FROM intelligence.professional_attempts a WHERE user_id=$1 ORDER BY created_at DESC LIMIT 20").bind(&a.id).fetch_all(&s.db).await?;
    let mut items = Vec::new();
    for row in rows {
        items.push(public_row(row).await?);
    }
    Ok(Json(json!({"items":items})))
}
#[derive(Deserialize)]
struct Start {
    specialization: String,
    mode: String,
    #[serde(default)]
    extra_time: bool,
}
async fn start(State(s): State<AppState>, a: Actor, Json(p): Json<Start>) -> Result<Json<Value>> {
    a.require("candidate")?;
    if !crate::matching::valid_spec(&p.specialization)
        || !matches!(p.mode.as_str(), "full" | "express")
    {
        return Err(AppError::bad("Выберите направление и формат"));
    }
    crate::security::throttle(&s, &format!("professional-start:{}", a.id), 10).await?;
    let mut tx = s.db.begin().await?;
    let _: String = sqlx::query_scalar("SELECT id FROM users WHERE id=$1 FOR UPDATE")
        .bind(&a.id)
        .fetch_one(&mut *tx)
        .await?;
    let existing:Option<Value>=sqlx::query_scalar("SELECT to_jsonb(a) FROM intelligence.professional_attempts a WHERE user_id=$1 AND status='active' ORDER BY created_at DESC LIMIT 1").bind(&a.id).fetch_optional(&mut *tx).await?;
    if let Some(row) = existing {
        tx.commit().await?;
        return Ok(Json(public_row(row).await?));
    }
    let count:i64=sqlx::query_scalar("SELECT count(*) FROM intelligence.professional_attempts WHERE user_id=$1 AND mode=$2 AND created_at>now()-interval '24 hours'").bind(&a.id).bind(&p.mode).fetch_one(&mut *tx).await?;
    if count >= if p.mode == "express" { 5 } else { 3 } {
        return Err(AppError::conflict(
            "Сегодня уже достаточно попыток. Продолжите завтра",
        ));
    }
    let exposure: Vec<(String, i64)> = sqlx::query_as(
        "SELECT item_id,count(*) FROM intelligence.professional_responses GROUP BY item_id",
    )
    .fetch_all(&mut *tx)
    .await?;
    let exposure: serde_json::Map<String, Value> =
        exposure.into_iter().map(|(k, n)| (k, json!(n))).collect();
    let quarantined:Vec<String>=sqlx::query_scalar("SELECT family FROM intelligence.professional_responses WHERE created_at>now()-interval '7 days' AND NOT pilot GROUP BY family HAVING count(*)>=50 AND (sum(correct::int)-sum(expected_correct))/sqrt(greatest(1,sum(expected_correct*(1-expected_correct))))>4").fetch_all(&mut *tx).await?;
    let pilots:Vec<Value>=sqlx::query_scalar("SELECT content||jsonb_build_object('id',id,'status',status,'calibration',calibration) FROM intelligence.item_drafts WHERE specialization=$1 AND status IN ('pilot','active') ORDER BY updated_at DESC LIMIT 12").bind(&p.specialization).fetch_all(&mut *tx).await?;
    let seed = u32::from_le_bytes(uuid::Uuid::new_v4().as_bytes()[..4].try_into().unwrap());
    let assigned=compute(&json!({"operation":"form_assign","identity":a.id,"scope":p.specialization,"version":"role-parameter-forms-v1"})).await?;
    let mut contract=compute(&json!({"operation":"professional_create","mode":p.mode,"specialization":p.specialization,"seed":seed,"form_variant":assigned["variant"],"independent_forms":true,"quarantined":quarantined,"exposure":exposure,"pilots":pilots})).await?;
    if p.extra_time {
        if let Some(bank) = contract["bank"].as_array_mut() {
            for q in bank {
                q["time_limit_seconds"] =
                    json!(q["time_limit_seconds"].as_i64().unwrap_or(120) * 2);
            }
        }
    }
    let id = new_id("PC");
    let row:Value=sqlx::query_scalar("INSERT INTO intelligence.professional_attempts(id,user_id,specialization,mode,contract) VALUES($1,$2,$3,$4,$5) RETURNING to_jsonb(professional_attempts)").bind(id).bind(&a.id).bind(&p.specialization).bind(p.mode).bind(contract).fetch_one(&mut *tx).await?;
    tx.commit().await?;
    Ok(Json(public_row(row).await?))
}
#[derive(Deserialize)]
struct Answer {
    question_id: String,
    answer: i64,
    revision: i32,
}
async fn answer(
    State(s): State<AppState>,
    a: Actor,
    Path(id): Path<String>,
    Json(p): Json<Answer>,
) -> Result<Json<Value>> {
    a.require("candidate")?;
    let row:Option<Value>=sqlx::query_scalar("SELECT to_jsonb(a)||jsonb_build_object('elapsed_ms',greatest(0,(extract(epoch FROM(now()-item_started_at))*1000)::bigint)) FROM intelligence.professional_attempts a WHERE id=$1 AND user_id=$2").bind(&id).bind(&a.id).fetch_optional(&s.db).await?;
    let row = row.ok_or_else(AppError::missing)?;
    if row["status"] != "active" || row["revision"] != p.revision {
        return Err(AppError::conflict("Этот ответ уже обработан"));
    }
    let output=compute(&json!({"operation":"professional_step","contract":row["contract"],"question_id":p.question_id,"answer":p.answer,"elapsed_ms":row["elapsed_ms"]})).await?;
    let mut tx = s.db.begin().await?;
    let updated:Option<Value>=sqlx::query_scalar("UPDATE intelligence.professional_attempts SET contract=$4||jsonb_build_object('events',contract->'events'),result=$5,status=$6,revision=revision+1,item_started_at=now(),updated_at=now() WHERE id=$1 AND user_id=$2 AND revision=$3 AND status='active' RETURNING to_jsonb(professional_attempts)").bind(&id).bind(&a.id).bind(p.revision).bind(&output["contract"]).bind(&output["result"]).bind(if output["completed"]==true{"completed"}else{"active"}).fetch_optional(&mut *tx).await?;
    let mut row = updated.ok_or_else(|| AppError::conflict("Этот ответ уже обработан"))?;
    let o = &output["observation"];
    sqlx::query("INSERT INTO intelligence.professional_responses(attempt_id,item_id,family,topic,correct,expected_correct,theta_before,elapsed_ms,pilot) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)").bind(&id).bind(o["question_id"].as_str()).bind(o["family"].as_str()).bind(o["topic"].as_str()).bind(o["correct"].as_bool()).bind(o["expected_correct"].as_f64()).bind(o["theta_before"].as_f64()).bind(o["elapsed_ms"].as_i64()).bind(o["pilot"].as_bool()).execute(&mut *tx).await?;
    if output["completed"] == true {
        // Include telemetry committed concurrently with the final answer.
        let final_result =
            compute(&json!({"operation":"professional_result","contract":row["contract"]})).await?;
        sqlx::query("UPDATE intelligence.professional_attempts SET result=$2 WHERE id=$1")
            .bind(&id)
            .bind(&final_result)
            .execute(&mut *tx)
            .await?;
        if final_result["review_required"]==true {
            sqlx::query("INSERT INTO intelligence.review_cases(id,user_id,artifact_id,task_key,evidence) VALUES($1,$2,$3,$4,$5) ON CONFLICT(user_id,artifact_id) DO NOTHING").bind(new_id("RC")).bind(&a.id).bind(&id).bind("professional-response-pattern").bind(&final_result).execute(&mut *tx).await?;
        }
        row["result"] = final_result;
        crate::intelligence::record(
            &mut tx,
            &a.id,
            "professional_assessment",
            &json!({"attempt_id":id,"specialization":row["specialization"],"mode":row["mode"]}),
            &row["result"],
        )
        .await?;
    }
    tx.commit().await?;
    row["contract"] = output["public"].clone();
    Ok(Json(row))
}
#[derive(Deserialize)]
struct Signal {
    kind: String,
    count: Option<i32>,
}
async fn signals(
    State(s): State<AppState>,
    a: Actor,
    Path(id): Path<String>,
    Json(p): Json<Signal>,
) -> Result<Json<Value>> {
    a.require("candidate")?;
    if ![
        "copy",
        "paste",
        "visibility_hidden",
        "print_screen",
        "fullscreen_exit",
    ]
    .contains(&p.kind.as_str())
    {
        return Err(AppError::bad("Неизвестный сигнал"));
    }
    let count = p.count.unwrap_or(1);
    if !(1..=20).contains(&count) {
        return Err(AppError::bad("Некорректное число событий"));
    }
    let mut tx = s.db.begin().await?;
    let mut contract:Value=sqlx::query_scalar("SELECT contract FROM intelligence.professional_attempts WHERE id=$1 AND user_id=$2 AND status='active' FOR UPDATE").bind(&id).bind(&a.id).fetch_optional(&mut *tx).await?.ok_or_else(AppError::missing)?;
    let events = contract["events"]
        .as_array_mut()
        .ok_or_else(AppError::missing)?;
    if events.len() >= 60 {
        return Err(AppError::conflict("Достаточно сигналов для проверки"));
    }
    events.push(json!({"kind":p.kind,"count":count}));
    sqlx::query(
        "UPDATE intelligence.professional_attempts SET contract=$3 WHERE id=$1 AND user_id=$2",
    )
    .bind(&id)
    .bind(&a.id)
    .bind(contract)
    .execute(&mut *tx)
    .await?;
    sqlx::query("INSERT INTO intelligence.integrity_signals(user_id,attempt_id,kind,count) VALUES($1,$2,$3,$4)").bind(&a.id).bind(&id).bind(p.kind).bind(count).execute(&mut *tx).await?;
    tx.commit().await?;
    Ok(Json(json!({"recorded":true,"automatic_penalty":false})))
}
async fn abandon(
    State(s): State<AppState>,
    a: Actor,
    Path(id): Path<String>,
) -> Result<Json<Value>> {
    a.require("candidate")?;
    let n=sqlx::query("UPDATE intelligence.professional_attempts SET status='abandoned',updated_at=now() WHERE id=$1 AND user_id=$2 AND status='active'").bind(id).bind(a.id).execute(&s.db).await?;
    if n.rows_affected() == 0 {
        return Err(AppError::missing());
    }
    Ok(Json(json!({"status":"abandoned"})))
}
async fn bank(State(s): State<AppState>, a: Actor) -> Result<Json<Value>> {
    expert(&s, &a).await?;
    let items:Vec<Value>=sqlx::query_scalar("SELECT jsonb_build_object('item_id',item_id,'responses',count(*),'correct_rate',avg(correct::int),'expected_rate',avg(expected_correct),'drift_z',(sum(correct::int)-sum(expected_correct))/sqrt(greatest(1,sum(expected_correct*(1-expected_correct))))) FROM intelligence.professional_responses GROUP BY item_id ORDER BY count(*) DESC LIMIT 150").fetch_all(&s.db).await?;
    let mut result = compute(&json!({"operation":"professional_catalog"})).await?;
    result["items"] = json!(items);
    Ok(Json(result))
}
async fn drafts(State(s): State<AppState>, a: Actor) -> Result<Json<Value>> {
    expert(&s, &a).await?;
    let rows:Vec<Value>=sqlx::query_scalar("SELECT to_jsonb(d) FROM intelligence.item_drafts d WHERE author_id=$1 OR status='draft' OR reviewer_id=$1 ORDER BY created_at DESC LIMIT 50").bind(&a.id).fetch_all(&s.db).await?;
    Ok(Json(json!({"items":rows})))
}
#[derive(Deserialize)]
struct Draft {
    specialization: String,
    content: Value,
}
async fn draft(State(s): State<AppState>, a: Actor, Json(p): Json<Draft>) -> Result<Json<Value>> {
    expert(&s, &a).await?;
    if !crate::matching::valid_spec(&p.specialization) {
        return Err(AppError::bad("Выберите направление"));
    }
    crate::security::throttle(&s, &format!("item-draft:{}", a.id), 10).await?;
    let mut input = p.content;
    if !input.is_object() {
        return Err(AppError::bad("Укажите объект задания"));
    }
    input["operation"] = json!("item_validate");
    let content = compute(&input).await?;
    let row:Value=sqlx::query_scalar("INSERT INTO intelligence.item_drafts(id,author_id,specialization,content) VALUES($1,$2,$3,$4) RETURNING to_jsonb(item_drafts)").bind(new_id("PD")).bind(&a.id).bind(p.specialization).bind(content).fetch_one(&s.db).await?;
    Ok(Json(row))
}
#[derive(Deserialize)]
struct Generate {
    specialization: String,
    topic: String,
}
async fn generate(
    State(s): State<AppState>,
    a: Actor,
    Json(p): Json<Generate>,
) -> Result<Json<Value>> {
    expert(&s, &a).await?;
    if !crate::matching::valid_spec(&p.specialization)
        || !(3..=120).contains(&p.topic.chars().count())
    {
        return Err(AppError::bad("Выберите направление и тему"));
    }
    crate::intelligence::enqueue(
        &s,
        &a,
        "item_draft",
        json!({"operation":"item_draft","specialization":p.specialization,"topic":p.topic}),
        None,
    )
    .await
}
#[derive(Deserialize)]
struct Review {
    decision: String,
    note: String,
    content: Option<Value>,
}
async fn review(
    State(s): State<AppState>,
    a: Actor,
    Path(id): Path<String>,
    Json(p): Json<Review>,
) -> Result<Json<Value>> {
    expert(&s, &a).await?;
    if !matches!(p.decision.as_str(), "pilot" | "rejected")
        || !(10..=1000).contains(&p.note.chars().count())
    {
        return Err(AppError::bad("Укажите решение и обоснование"));
    }
    let content = if let Some(mut v) = p.content {
        if !v.is_object() {
            return Err(AppError::bad("Укажите объект задания"));
        }
        v["operation"] = json!("item_validate");
        Some(compute(&v).await?)
    } else {
        None
    };
    let row:Option<Value>=sqlx::query_scalar("UPDATE intelligence.item_drafts SET status=$3,reviewer_id=$2,review_note=$4,content=coalesce($5,content),version=version+1,updated_at=now() WHERE id=$1 AND status='draft' AND author_id<>$2 RETURNING to_jsonb(item_drafts)").bind(&id).bind(&a.id).bind(p.decision).bind(p.note).bind(content).fetch_optional(&s.db).await?;
    let row = row.ok_or_else(|| {
        AppError::conflict(
            "Проверку проводит другой эксперт; черновик уже проверен или принадлежит вам",
        )
    })?;
    Ok(Json(row))
}
async fn calibrate(
    State(s): State<AppState>,
    a: Actor,
    Path(id): Path<String>,
) -> Result<Json<Value>> {
    expert(&s, &a).await?;
    let draft:Option<Value>=sqlx::query_scalar("SELECT to_jsonb(d) FROM intelligence.item_drafts d WHERE id=$1 AND status='pilot' AND reviewer_id=$2").bind(&id).bind(&a.id).fetch_optional(&s.db).await?;
    draft.ok_or_else(AppError::missing)?;
    let bins:Vec<Value>=sqlx::query_scalar("SELECT jsonb_build_object('theta',floor(theta_before*2)/2.0,'total',count(*),'correct',sum(correct::int)) FROM intelligence.professional_responses WHERE item_id=$1 AND pilot GROUP BY floor(theta_before*2) ORDER BY floor(theta_before*2)").bind(&id).fetch_all(&s.db).await?;
    let result = compute(&json!({"operation":"item_calibrate","bins":bins})).await?;
    sqlx::query("UPDATE intelligence.item_drafts SET calibration=$2,updated_at=now() WHERE id=$1 AND status='pilot'").bind(&id).bind(&result).execute(&s.db).await?;
    Ok(Json(result))
}
async fn activate(
    State(s): State<AppState>,
    a: Actor,
    Path(id): Path<String>,
) -> Result<Json<Value>> {
    expert(&s, &a).await?;
    let row:Option<Value>=sqlx::query_scalar("UPDATE intelligence.item_drafts SET status='active',version=version+1,updated_at=now() WHERE id=$1 AND reviewer_id=$2 AND author_id<>$2 AND status='pilot' AND calibration IS NOT NULL AND (calibration->>'responses')::int>=120 RETURNING to_jsonb(item_drafts)").bind(id).bind(a.id).fetch_optional(&s.db).await?;
    Ok(Json(row.ok_or_else(|| {
        AppError::conflict("Сначала завершите калибровку пилотного задания")
    })?))
}
pub async fn export_owned(s: &AppState, owner: &str) -> Result<Value> {
    let attempts:Vec<Value>=sqlx::query_scalar("SELECT to_jsonb(a)-'contract' FROM intelligence.professional_attempts a WHERE user_id=$1 ORDER BY created_at").bind(owner).fetch_all(&s.db).await?;
    let signals: Vec<Value> = sqlx::query_scalar(
        "SELECT to_jsonb(i) FROM intelligence.integrity_signals i WHERE user_id=$1 ORDER BY id",
    )
    .bind(owner)
    .fetch_all(&s.db)
    .await?;
    let link: Option<Value> =
        sqlx::query_scalar("SELECT to_jsonb(l) FROM intelligence.oidc_links l WHERE user_id=$1")
            .bind(owner)
            .fetch_optional(&s.db)
            .await?;
    Ok(json!({"attempts":attempts,"signals":signals,"fsp_identity":link}))
}

async fn oidc_status(State(s): State<AppState>, a: Actor) -> Result<Json<Value>> {
    a.require("candidate")?;
    let linked: bool =
        sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM intelligence.oidc_links WHERE user_id=$1)")
            .bind(&a.id)
            .fetch_one(&s.db)
            .await?;
    Ok(Json(
        json!({"enabled":s.demo||std::env::var("FSP_OIDC_ISSUER").is_ok(),"linked":linked,"achievements_verified":false}),
    ))
}
fn oidc_cookie(s: &AppState, value: &str, age: u16) -> Result<HeaderValue> {
    let (name, secure) = if s.base_url.starts_with("https://") {
        ("__Host-proofit_oidc", "; Secure")
    } else {
        ("proofit_oidc", "")
    };
    HeaderValue::from_str(&format!(
        "{name}={value}; Path=/; HttpOnly; SameSite=Lax; Max-Age={age}{secure}"
    ))
    .map_err(|_| AppError::bad("Сессия привязки"))
}
async fn oidc_start(State(s): State<AppState>, a: Actor) -> Result<Response> {
    a.require("candidate")?;
    crate::security::throttle(&s, &format!("oidc-start:{}", a.id), 10).await?;
    let state = format!(
        "{}{}",
        uuid::Uuid::new_v4().simple(),
        uuid::Uuid::new_v4().simple()
    );
    let nonce = new_id("ON");
    let verifier = format!(
        "{}{}",
        uuid::Uuid::new_v4().simple(),
        uuid::Uuid::new_v4().simple()
    );
    let result=compute(&json!({"operation":"oidc_start","demo":s.demo,"state":state,"nonce":nonce,"verifier":verifier,"redirect_uri":format!("{}/api/intelligence/assessment/oidc/callback",s.base_url)})).await?;
    sqlx::query("DELETE FROM intelligence.oidc_states WHERE user_id=$1 AND expires_at<now()")
        .bind(&a.id)
        .execute(&s.db)
        .await?;
    let browser = format!(
        "{}{}",
        uuid::Uuid::new_v4().simple(),
        uuid::Uuid::new_v4().simple()
    );
    sqlx::query("INSERT INTO intelligence.oidc_states(state_hash,user_id,nonce,verifier,browser_binding_hash,expires_at) VALUES($1,$2,$3,$4,$5,now()+interval '5 minutes')").bind(crate::auth::hash_token(&state)).bind(&a.id).bind(nonce).bind(verifier).bind(crate::auth::hash_token(&browser)).execute(&s.db).await?;
    let mut response = Json(result).into_response();
    response
        .headers_mut()
        .insert(header::SET_COOKIE, oidc_cookie(&s, &browser, 300)?);
    Ok(response)
}
#[derive(Deserialize)]
struct Callback {
    state: String,
    code: String,
}
async fn oidc_finish(
    State(s): State<AppState>,
    headers: HeaderMap,
    Query(p): Query<Callback>,
) -> Result<Response> {
    if p.state.len() != 64 || p.code.len() > 4000 {
        return Err(AppError::bad("Некорректный ответ провайдера"));
    }
    let prefix = if s.base_url.starts_with("https://") {
        "__Host-proofit_oidc="
    } else {
        "proofit_oidc="
    };
    let binding = headers
        .get(header::COOKIE)
        .and_then(|v| v.to_str().ok())
        .and_then(|cookies| {
            cookies
                .split(';')
                .find_map(|c| c.trim().strip_prefix(prefix))
        })
        .filter(|v| v.len() == 64)
        .ok_or_else(|| AppError::bad("Возврат необходимо открыть в том же браузере"))?;
    let row:Option<(String,String,String)>=sqlx::query_as("DELETE FROM intelligence.oidc_states WHERE state_hash=$1 AND browser_binding_hash=$2 AND expires_at>now() RETURNING user_id,nonce,verifier").bind(crate::auth::hash_token(&p.state)).bind(crate::auth::hash_token(binding)).fetch_optional(&s.db).await?;
    let (user_id, nonce, verifier) =
        row.ok_or_else(|| AppError::bad("Ссылка подтверждения истекла или уже использована"))?;
    let result=compute(&json!({"operation":"oidc_finish","demo":s.demo,"nonce":nonce,"verifier":verifier,"code":p.code,"redirect_uri":format!("{}/api/intelligence/assessment/oidc/callback",s.base_url)})).await?;
    let mut tx = s.db.begin().await?;
    sqlx::query("DELETE FROM intelligence.oidc_links WHERE user_id=$1")
        .bind(&user_id)
        .execute(&mut *tx)
        .await?;
    let owner:Option<String>=sqlx::query_scalar("INSERT INTO intelligence.oidc_links(user_id,issuer,subject) VALUES($1,$2,$3) ON CONFLICT(issuer,subject) DO NOTHING RETURNING user_id").bind(&user_id).bind(result["issuer"].as_str()).bind(result["subject"].as_str()).fetch_optional(&mut *tx).await?;
    if owner.is_none() {
        return Err(AppError::conflict(
            "Этот ФСП ID уже привязан к другой учётной записи",
        ));
    }
    sqlx::query("INSERT INTO audit_events(actor_id,action,entity_id,details) VALUES($1,'fsp.oidc_linked',$1,$2)").bind(&user_id).bind(json!({"local_demo":result["local_demo"],"achievements_verified":false})).execute(&mut *tx).await?;
    tx.commit().await?;
    let mut response =
        Redirect::to(&format!("{}/#professional-assessment", s.base_url)).into_response();
    response
        .headers_mut()
        .insert(header::SET_COOKIE, oidc_cookie(&s, "", 0)?);
    Ok(response)
}
#[derive(Deserialize)]
struct CodeIntegrity {
    artifact_id: String,
}
async fn code_integrity(
    State(s): State<AppState>,
    a: Actor,
    Json(p): Json<CodeIntegrity>,
) -> Result<Json<Value>> {
    a.require("candidate")?;
    let row:Option<(String,String)>=sqlx::query_as("SELECT submission,kind FROM intelligence.arena_attempts WHERE id=$1 AND user_id=$2 AND status='completed' AND kind IN ('python','sql','typescript')").bind(&p.artifact_id).bind(&a.id).fetch_optional(&s.db).await?;
    let (code, language) = row.ok_or_else(AppError::missing)?;
    let mut output = register_code_proof(&s, &a.id, &p.artifact_id, &code, &language).await?;
    output["artifact_id"] = json!(p.artifact_id);
    Ok(Json(output))
}
pub async fn register_code_proof(
    s: &AppState,
    owner: &str,
    artifact: &str,
    code: &str,
    language: &str,
) -> Result<Value> {
    let scope: Option<Value> = sqlx::query_scalar(
        "SELECT contract FROM intelligence.arena_attempts WHERE id=$1 AND user_id=$2 UNION ALL SELECT t.contract FROM micro_tasks t JOIN users u ON u.subject_id=t.candidate_id WHERE t.id=$1 AND u.id=$2 LIMIT 1",
    )
    .bind(artifact)
    .bind(owner)
    .fetch_optional(&s.db)
    .await?;
    let contract = scope.unwrap_or(json!({}));
    let task_key = format!(
        "{}:{}:{}",
        language,
        contract["family"].as_str().unwrap_or("arena"),
        contract["title"].as_str().unwrap_or("practice")
    );
    let fingerprint=compute(&json!({"operation":"code_fingerprint","code":crate::workbench::redact(code),"language":language,"template":contract["starter_code"].as_str().unwrap_or("")})).await?;
    let others:Vec<Value>=sqlx::query_scalar("SELECT fingerprint FROM intelligence.code_proofs WHERE user_id<>$1 AND task_key=$2 AND language=$3 ORDER BY created_at DESC LIMIT 500").bind(owner).bind(&task_key).bind(language).fetch_all(&s.db).await?;
    let result = compute(
        &json!({"operation":"code_similarity","fingerprint":fingerprint,"references":others}),
    )
    .await?;
    sqlx::query("INSERT INTO intelligence.code_proofs(artifact_id,user_id,fingerprint,task_key,language) VALUES($1,$2,$3,$4,$5) ON CONFLICT(artifact_id) DO UPDATE SET fingerprint=EXCLUDED.fingerprint,task_key=EXCLUDED.task_key,language=EXCLUDED.language").bind(artifact).bind(owner).bind(fingerprint).bind(&task_key).bind(language).execute(&s.db).await?;
    if result["review_recommended"] == true {
        sqlx::query("INSERT INTO intelligence.review_cases(id,user_id,artifact_id,task_key,evidence) VALUES($1,$2,$3,$4,$5) ON CONFLICT(user_id,artifact_id) DO UPDATE SET evidence=EXCLUDED.evidence").bind(new_id("RC")).bind(owner).bind(artifact).bind(task_key).bind(&result).execute(&s.db).await?;
    }
    Ok(result)
}

#[derive(Deserialize)]
struct Need {
    text: String,
}
async fn need_preview(
    State(s): State<AppState>,
    a: Actor,
    Json(p): Json<Need>,
) -> Result<Json<Value>> {
    a.verified_employer(&s).await?;
    if !(3..=4000).contains(&p.text.chars().count()) {
        return Err(AppError::bad("Запрос: от 3 до 4000 символов"));
    }
    let mut text = p.text;
    let mut labels: Vec<_> = crate::matching::taxonomy().iter().enumerate().collect();
    labels.sort_by_key(|(_, role)| std::cmp::Reverse(role.label.len()));
    for (i, role) in &labels {
        let pattern = regex::RegexBuilder::new(&regex::escape(&role.label))
            .case_insensitive(true)
            .build()
            .map_err(|_| AppError::bad("Направление"))?;
        text = pattern
            .replace_all(&text, format!("__ROLE_{i}__"))
            .into_owned();
    }
    text = crate::workbench::redact(&text);
    for (i, role) in labels {
        text = text.replace(&format!("__ROLE_{i}__"), &role.label);
    }
    Ok(Json(
        compute(&json!({"operation":"need_parse","text":text})).await?,
    ))
}
