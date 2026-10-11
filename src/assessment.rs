//! Read-only historical assessment records. Quiz endpoints are retired.
use crate::{AppState, auth::Actor, error::Result};
use axum::{Json, extract::State};
use serde_json::{Value, json};
pub async fn history(State(s): State<AppState>, actor: Actor) -> Result<Json<Value>> {
    actor.require("candidate")?;
    let rows:Vec<Value>=sqlx::query_scalar("SELECT jsonb_build_object('id',id,'specialization',specialization,'grade',grade,'status',status,'score',score,'created_at',created_at,'finished_at',finished_at,'synthetic',synthetic,'feedback',feedback,'blueprint_version',blueprint_version) FROM assessments WHERE candidate_id=$1 ORDER BY created_at DESC LIMIT 100").bind(&actor.subject_id).fetch_all(&s.db).await?;
    Ok(Json(
        json!({"items":rows,"methodology":{"method":crate::cases::VERSION,"max_project_questions":3,"individual_cases":3,"max_case_characters":800,"grade_change_cooldown_days":90,"note":"Грейд подтверждается после разбора проекта и трёх кейсов. Исторические синтетические баллы не являются результатами этой оценки. Сопоставимость шкалы требует независимой проверки."}}),
    ))
}
