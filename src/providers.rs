use crate::{
    AppState,
    auth::{Actor, new_id},
    error::{AppError, Result},
    intelligence::compute,
};
use axum::{
    Json, Router,
    extract::{Path, State},
    routing::{get, post},
};
use serde::Deserialize;
use serde_json::{Value, json};
pub fn routes() -> Router<AppState> {
    Router::new()
        .route("/status", get(status))
        .route("/dreamjob/{id}", get(company_reviews))
        .route("/dreamjob", axum::routing::put(link_company))
        .route("/sync/{provider}", post(sync))
}
async fn status(a: Actor) -> Json<Value> {
    Json(
        json!({"owner_role":a.role,"fsp":{"identity":"OIDC + PKCE","registry_configured":std::env::var("FSP_REGISTRY_URL").is_ok()},"dreamjob":{"partner_configured":std::env::var("DREAMJOB_PARTNER_URL").is_ok(),"public_reviews":"https://dreamjob.ru","missing_evidence_effect":0}}),
    )
}
#[derive(Deserialize)]
struct Link {
    employer_id: String,
}
async fn link_company(
    State(s): State<AppState>,
    a: Actor,
    Json(p): Json<Link>,
) -> Result<Json<Value>> {
    a.verified_employer(&s).await?;
    if p.employer_id.len() > 20
        || p.employer_id.is_empty()
        || !p.employer_id.chars().all(|c| c.is_ascii_digit())
    {
        return Err(AppError::bad("Введите числовой ID компании на DreamJob"));
    }
    sqlx::query("UPDATE companies SET dreamjob_employer_id=$2 WHERE id=$1")
        .bind(&a.subject_id)
        .bind(&p.employer_id)
        .execute(&s.db)
        .await?;
    Ok(Json(
        json!({"source_url":format!("https://dreamjob.ru/employers/{}",p.employer_id),"status":"linked_unverified"}),
    ))
}
async fn company_reviews(
    State(s): State<AppState>,
    _a: Actor,
    Path(id): Path<String>,
) -> Result<Json<Value>> {
    let external: Option<String> =
        sqlx::query_scalar("SELECT dreamjob_employer_id FROM companies WHERE id=$1")
            .bind(&id)
            .fetch_optional(&s.db)
            .await?
            .flatten();
    let snapshot:Option<Value>=sqlx::query_scalar("SELECT to_jsonb(p)-'subject_id' FROM intelligence.provider_snapshots p WHERE provider='dreamjob' AND subject_id=$1").bind(&id).fetch_optional(&s.db).await?;
    Ok(Json(
        json!({"snapshot":snapshot,"source_url":external.map(|x|format!("https://dreamjob.ru/employers/{x}")),"status":if snapshot.is_some(){"snapshot_available"}else{"no_verified_rating"},"missing_is_not_negative":true}),
    ))
}
async fn sync(
    State(s): State<AppState>,
    a: Actor,
    Path(provider): Path<String>,
) -> Result<Json<Value>> {
    crate::security::throttle(&s, &format!("provider:{}", a.id), 10).await?;
    let subject = if provider == "dreamjob" {
        a.verified_employer(&s).await?;
        sqlx::query_scalar::<_, Option<String>>(
            "SELECT dreamjob_employer_id FROM companies WHERE id=$1",
        )
        .bind(&a.subject_id)
        .fetch_one(&s.db)
        .await?
        .ok_or_else(|| AppError::bad("Сначала привяжите страницу DreamJob"))?
    } else if provider == "fsp" {
        a.require("candidate")?;
        sqlx::query_scalar::<_, String>(
            "SELECT subject FROM intelligence.oidc_links WHERE user_id=$1",
        )
        .bind(&a.id)
        .fetch_optional(&s.db)
        .await?
        .ok_or_else(|| AppError::bad("Сначала подтвердите профессиональную идентичность"))?
    } else {
        return Err(AppError::bad("Неизвестный провайдер"));
    };
    let out =
        compute(&json!({"operation":"provider_fetch","provider":provider,"subject_id":subject}))
            .await?;
    if out["status"] == "verified" {
        let source = if provider == "dreamjob" {
            out["value"]["source_url"].as_str().unwrap_or("")
        } else {
            "https://fsp-russia.com"
        };
        let mut tx = s.db.begin().await?;
        sqlx::query("INSERT INTO intelligence.provider_snapshots(id,provider,subject_id,value,status,source_url) VALUES($1,$2,$3,$4,'verified',$5) ON CONFLICT(provider,subject_id) DO UPDATE SET value=$4,status='verified',source_url=$5,fetched_at=now()").bind(new_id("PS")).bind(&provider).bind(&a.subject_id).bind(&out["value"]).bind(source).execute(&mut *tx).await?;
        if provider == "fsp" {
            for event in out["value"]["participations"].as_array().unwrap_or(&vec![]) {
                sqlx::query("INSERT INTO fsp_participations(id,candidate_id,event_name,discipline,event_date,result,source_url,status,verified_at) VALUES($1,$2,$3,$4,$5::date,$6,$7,'verified',now()) ON CONFLICT(candidate_id,event_name,event_date,result) DO UPDATE SET source_url=EXCLUDED.source_url,status='verified',verified_at=now()").bind(new_id("F")).bind(&a.subject_id).bind(event["event_name"].as_str()).bind(event["discipline"].as_str()).bind(event["event_date"].as_str()).bind(event["result"].as_str()).bind(event["source_url"].as_str()).execute(&mut *tx).await?;
            }
        }
        tx.commit().await?;
    }
    Ok(Json(out))
}
