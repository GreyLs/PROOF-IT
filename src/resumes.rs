//! Independent, privacy-preserving resume targets and their local qualification tests.
use crate::{
    AppState,
    auth::{Actor, new_id},
    error::{AppError, Result},
    matching,
};
use axum::{
    Json,
    extract::{Path, State},
};
use serde::Deserialize;
use serde_json::{Value, json};

#[derive(Deserialize)]
pub struct ResumeInput {
    pub target_position: String,
    pub specialization: String,
    pub declared_grade: String,
    pub experience_years: f64,
    pub skills: Vec<String>,
    pub about: String,
    pub expected_salary: i32,
    pub work_format: String,
    pub visibility: String,
}
fn validate(p: &ResumeInput) -> Result<()> {
    if p.target_position.trim().chars().count() < 3
        || p.target_position.chars().count() > 250
        || !matching::valid_spec(&p.specialization)
        || !matching::valid_role_grade(&p.specialization, &p.declared_grade)
        || !p.experience_years.is_finite()
        || !(0.0..=80.).contains(&p.experience_years)
        || p.skills.len() > 60
        || p.skills.iter().any(|s| s.chars().count() > 100)
        || p.about.chars().count() > 15_000
        || p.expected_salary < 0
        || p.expected_salary > 100_000_000
        || p.work_format.chars().count() > 100
        || !["private", "employer_searchable"].contains(&p.visibility.as_str())
    {
        return Err(AppError::bad(
            "Проверьте целевую позицию, роль, грейд, стаж, навыки и видимость резюме",
        ));
    }
    Ok(())
}
async fn profile(
    tx: &mut sqlx::Transaction<'_, sqlx::Postgres>,
    candidate: &str,
    id: &str,
) -> Result<Value> {
    sqlx::query_scalar("SELECT to_jsonb(r)||jsonb_build_object('employer_eligible',rg.employer_eligible,'confirmed_grade',rg.confirmed_grade,'category_scope',rg.category_scope,'category_proof_id',rg.category_proof_id,'test',jsonb_build_object('status',q.status,'generation_status',q.generation_status,'score',q.score,'passed',q.passed,'available_at',q.available_at,'attempts',q.attempts,'error',q.error)) FROM resume_profiles r JOIN qualification_tests q ON q.resume_id=r.id JOIN intelligence.resume_category_evidence rg ON rg.id=r.id WHERE r.id=$1 AND r.candidate_id=$2")
        .bind(id).bind(candidate).fetch_optional(&mut **tx).await?.ok_or_else(AppError::missing)
}
pub async fn list(State(s): State<AppState>, actor: Actor) -> Result<Json<Value>> {
    actor.require("candidate")?;
    let items:Vec<Value>=sqlx::query_scalar("SELECT to_jsonb(r)||jsonb_build_object('employer_eligible',rg.employer_eligible,'confirmed_grade',rg.confirmed_grade,'category_scope',rg.category_scope,'category_proof_id',rg.category_proof_id,'test',CASE WHEN q.id IS NULL THEN jsonb_build_object('status','historical','generation_status','none') ELSE jsonb_build_object('status',q.status,'generation_status',q.generation_status,'score',q.score,'passed',q.passed,'available_at',q.available_at,'attempts',q.attempts,'error',q.error) END) FROM resume_profiles r LEFT JOIN qualification_tests q ON q.resume_id=r.id JOIN intelligence.resume_category_evidence rg ON rg.id=r.id WHERE r.candidate_id=$1 ORDER BY r.created_at ASC").bind(&actor.subject_id).fetch_all(&s.db).await?;
    Ok(Json(json!({"max_resumes":3,"items":items})))
}
pub async fn create(
    State(s): State<AppState>,
    actor: Actor,
    Json(p): Json<ResumeInput>,
) -> Result<Json<Value>> {
    actor.require("candidate")?;
    validate(&p)?;
    let mut tx = s.db.begin().await?;
    let consent: Option<(bool, bool)> = sqlx::query_as(
        "SELECT consent_processing,consent_publication FROM candidates WHERE id=$1 FOR UPDATE",
    )
    .bind(&actor.subject_id)
    .fetch_optional(&mut *tx)
    .await?;
    let Some((processing, publication)) = consent else {
        return Err(AppError::missing());
    };
    if p.visibility == "employer_searchable" && (!processing || !publication) {
        return Err(AppError::bad(
            "Для публикации резюме нужны оба согласия в профиле",
        ));
    }
    let count: i64 = sqlx::query_scalar(
        "SELECT count(*) FROM resume_profiles WHERE candidate_id=$1 AND status<>'archived'",
    )
    .bind(&actor.subject_id)
    .fetch_one(&mut *tx)
    .await?;
    if count >= 3 {
        return Err(AppError::conflict(
            "Одновременно можно хранить и публиковать до трёх резюме",
        ));
    }
    let id = new_id("R");
    let test_id = new_id("Q");
    sqlx::query("INSERT INTO resume_profiles(id,candidate_id,target_position,specialization,declared_grade,experience_years,skills,about,expected_salary,work_format,visibility,status) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)")
        .bind(&id).bind(&actor.subject_id).bind(p.target_position.trim()).bind(p.specialization).bind(p.declared_grade).bind(p.experience_years).bind(p.skills).bind(p.about).bind(p.expected_salary).bind(p.work_format).bind(&p.visibility).bind(if p.visibility=="employer_searchable"{"published"}else{"draft"}).execute(&mut *tx).await?;
    sqlx::query("INSERT INTO qualification_tests(id,resume_id,status,generation_status,seed) VALUES($1,$2,'queued','queued',md5(random()::text||clock_timestamp()::text))").bind(test_id).bind(&id).execute(&mut *tx).await?;
    let item = profile(&mut tx, &actor.subject_id, &id).await?;
    crate::db::audit(
        &s,
        &actor.id,
        "resume.created",
        &id,
        json!({"source":"manual"}),
    )
    .await?;
    tx.commit().await?;
    Ok(Json(json!({"resume":item})))
}
pub async fn update(
    State(s): State<AppState>,
    actor: Actor,
    Path(id): Path<String>,
    Json(p): Json<ResumeInput>,
) -> Result<Json<Value>> {
    actor.require("candidate")?;
    validate(&p)?;
    let mut tx = s.db.begin().await?;
    let consent: Option<(bool, bool)> = sqlx::query_as(
        "SELECT consent_processing,consent_publication FROM candidates WHERE id=$1 FOR UPDATE",
    )
    .bind(&actor.subject_id)
    .fetch_optional(&mut *tx)
    .await?;
    let Some((processing, publication)) = consent else {
        return Err(AppError::missing());
    };
    if p.visibility == "employer_searchable" && (!processing || !publication) {
        return Err(AppError::bad(
            "Для публикации резюме нужны оба согласия в профиле",
        ));
    }
    let snapshot:Option<(String,String,String,Option<chrono::DateTime<chrono::Utc>>)>=sqlx::query_as("SELECT r.specialization,r.declared_grade,q.status,q.grade_changed_at FROM resume_profiles r JOIN qualification_tests q ON q.resume_id=r.id WHERE r.id=$1 AND r.candidate_id=$2 FOR UPDATE OF r,q").bind(&id).bind(&actor.subject_id).fetch_optional(&mut *tx).await?;
    let (old_spec, old_grade, test_status, changed_at) = snapshot.ok_or_else(AppError::missing)?;
    let target_changed = old_spec != p.specialization || old_grade != p.declared_grade;
    if target_changed && test_status == "in_progress" {
        return Err(AppError::conflict(
            "Завершите текущую попытку перед изменением направления или грейда",
        ));
    }
    if target_changed
        && old_spec == p.specialization
        && changed_at.is_some_and(|d| chrono::Utc::now() - d < chrono::Duration::days(90))
    {
        return Err(AppError::conflict(
            "Изменение подтверждённого грейда доступно через 90 дней",
        ));
    }
    let updated:Option<String>=sqlx::query_scalar("UPDATE resume_profiles SET target_position=$3,specialization=$4,declared_grade=$5,experience_years=$6,skills=$7,about=$8,expected_salary=$9,work_format=$10,visibility=$11,status=$12,version=version+1,updated_at=now() WHERE id=$1 AND candidate_id=$2 RETURNING id")
        .bind(&id).bind(&actor.subject_id).bind(p.target_position.trim()).bind(&p.specialization).bind(&p.declared_grade).bind(p.experience_years).bind(p.skills).bind(p.about).bind(p.expected_salary).bind(p.work_format).bind(&p.visibility).bind(if p.visibility=="employer_searchable"{"published"}else{"draft"}).fetch_optional(&mut *tx).await?;
    if updated.is_none() {
        return Err(AppError::missing());
    }
    // Editing salary, text or visibility must not reset a cooldown or move proof to another role.
    if target_changed {
        sqlx::query("UPDATE qualification_tests SET status='queued',generation_status='queued',questions='[]',contract=NULL,revision=0,score=NULL,passed=false,certified_grade=CASE WHEN certified_specialization=$2 THEN certified_grade ELSE NULL END,certified_skills=CASE WHEN certified_specialization=$2 THEN certified_skills ELSE '[]'::jsonb END,target_specialization=$2,target_grade=$3,available_at=CASE WHEN status='cooldown' AND $2=target_specialization AND $3=target_grade THEN available_at ELSE now() END,seed=md5(random()::text||clock_timestamp()::text),error=NULL,updated_at=now() WHERE resume_id=$1").bind(&id).bind(&p.specialization).bind(&p.declared_grade).execute(&mut *tx).await?;
    }
    let item = profile(&mut tx, &actor.subject_id, &id).await?;
    tx.commit().await?;
    Ok(Json(json!({"resume":item})))
}
pub async fn remove(
    State(s): State<AppState>,
    actor: Actor,
    Path(id): Path<String>,
) -> Result<Json<Value>> {
    actor.require("candidate")?;
    let changed=sqlx::query("UPDATE resume_profiles SET status='archived',visibility='private',updated_at=now() WHERE id=$1 AND candidate_id=$2 AND status<>'archived'").bind(&id).bind(&actor.subject_id).execute(&s.db).await?.rows_affected();
    if changed != 1 {
        return Err(AppError::missing());
    };
    Ok(Json(json!({"archived":true})))
}
async fn due(s: &AppState, resume: &str) -> Result<()> {
    sqlx::query("UPDATE qualification_tests SET status='ready',updated_at=now() WHERE resume_id=$1 AND status='cooldown' AND generation_status='ready' AND available_at<=now()").bind(resume).execute(&s.db).await?;
    Ok(())
}
async fn owned_test(s: &AppState, actor: &Actor, resume: &str) -> Result<Value> {
    actor.require("candidate")?;
    due(s, resume).await?;
    sqlx::query_scalar("SELECT jsonb_build_object('resume_id',r.id,'target_position',r.target_position,'specialization',r.specialization,'declared_grade',r.declared_grade,'test_id',q.id,'status',q.status,'generation_status',q.generation_status,'score',q.score,'passed',q.passed,'available_at',q.available_at,'attempts',q.attempts,'started_at',q.started_at,'finished_at',q.finished_at,'error',q.error,'questions',q.questions,'last_attempt',q.last_attempt,'expert_review_requested',EXISTS(SELECT 1 FROM qualification_expert_reviews er WHERE er.qualification_test_id=q.id)) FROM qualification_tests q JOIN resume_profiles r ON r.id=q.resume_id WHERE r.id=$1 AND r.candidate_id=$2 AND r.status<>'archived'").bind(resume).bind(&actor.subject_id).fetch_optional(&s.db).await?.ok_or_else(AppError::missing)
}
/// Candidate-initiated appeal.  The immutable snapshot is stored both in the
/// database queue and as a local JSON file under storage/expert-validation for
/// an authorised FSP expert to inspect outside the candidate flow.
pub async fn test_dispute(
    State(s): State<AppState>,
    actor: Actor,
    Path(id): Path<String>,
) -> Result<Json<Value>> {
    let row = owned_test(&s, &actor, &id).await?;
    let attempt = row["last_attempt"].clone();
    if !attempt.is_object()
        || attempt["questions"]
            .as_array()
            .is_none_or(|items| items.is_empty())
    {
        return Err(AppError::conflict(
            "Сначала завершите тест: для проверки нужен итог попытки",
        ));
    }
    let existing: Option<String> = sqlx::query_scalar(
        "SELECT id FROM qualification_expert_reviews WHERE qualification_test_id=$1",
    )
    .bind(row["test_id"].as_str())
    .fetch_optional(&s.db)
    .await?;
    if let Some(review_id) = existing {
        return Ok(Json(
            json!({"review_requested":true,"review_id":review_id,"message":"Эта попытка уже находится в папке «На экспертную валидацию»."}),
        ));
    }
    let review_id = new_id("QR");
    let folder_key = format!("expert-validation/{review_id}.json");
    let snapshot = json!({
        "review_id":review_id,
        "created_at":chrono::Utc::now(),
        "candidate_id":actor.subject_id,
        "resume":{
            "id":row["resume_id"],
            "target_position":row["target_position"],
            "specialization":row["specialization"],
            "declared_grade":row["declared_grade"],
        },
        "qualification_test_id":row["test_id"],
        "attempt":attempt,
    });
    let path = s.storage.join(&folder_key);
    if let Some(parent) = path.parent() {
        tokio::fs::create_dir_all(parent).await?;
    }
    let encoded = serde_json::to_vec_pretty(&snapshot)
        .map_err(|_| AppError::bad("Не удалось подготовить пакет экспертной проверки"))?;
    tokio::fs::write(&path, encoded).await?;
    let mut tx = s.db.begin().await?;
    let inserted = sqlx::query("INSERT INTO qualification_expert_reviews(id,qualification_test_id,candidate_id,resume_id,folder_key,snapshot) VALUES($1,$2,$3,$4,$5,$6) ON CONFLICT(qualification_test_id) DO NOTHING")
        .bind(&review_id).bind(row["test_id"].as_str()).bind(&actor.subject_id).bind(row["resume_id"].as_str()).bind(&folder_key).bind(&snapshot).execute(&mut *tx).await?;
    if inserted.rows_affected() != 1 {
        let _ = tokio::fs::remove_file(&path).await;
        tx.rollback().await?;
        return Ok(Json(
            json!({"review_requested":true,"message":"Эта попытка уже находится в папке «На экспертную валидацию»."}),
        ));
    }
    crate::db::audit(
        &s,
        &actor.id,
        "qualification.expert_review_requested",
        row["test_id"].as_str().unwrap_or(""),
        json!({"resume_id":id,"review_id":review_id}),
    )
    .await?;
    tx.commit().await?;
    Ok(Json(
        json!({"review_requested":true,"review_id":review_id,"message":"Тест, ответы и ключи переданы в папку «На экспертную валидацию»."}),
    ))
}
#[derive(Deserialize)]
pub struct Participation {
    pub event_name: String,
    pub discipline: String,
    pub event_date: Option<String>,
    pub result: String,
    pub source_url: String,
}
pub async fn participation_list(State(s): State<AppState>, actor: Actor) -> Result<Json<Value>> {
    actor.require("candidate")?;
    let items:Vec<Value>=sqlx::query_scalar("SELECT to_jsonb(f) FROM fsp_participations f WHERE candidate_id=$1 ORDER BY event_date DESC NULLS LAST,created_at DESC").bind(&actor.subject_id).fetch_all(&s.db).await?;
    Ok(Json(
        json!({"items":items,"notice":"Участие становится сигналом для подбора только после подтверждения ФСП."}),
    ))
}
pub async fn participation_create(
    State(s): State<AppState>,
    actor: Actor,
    Json(p): Json<Participation>,
) -> Result<Json<Value>> {
    actor.require("candidate")?;
    if p.event_name.trim().chars().count() < 3
        || p.event_name.chars().count() > 250
        || p.discipline.chars().count() > 250
        || p.result.chars().count() > 500
        || p.source_url.chars().count() > 1000
    {
        return Err(AppError::bad("Проверьте сведения о мероприятии ФСП"));
    };
    if let Some(date) = &p.event_date {
        chrono::NaiveDate::parse_from_str(date, "%Y-%m-%d")
            .map_err(|_| AppError::bad("Дата мероприятия должна быть в формате ГГГГ-ММ-ДД"))?;
    };
    let id = new_id("F");
    let item:Value=sqlx::query_scalar("INSERT INTO fsp_participations(id,candidate_id,event_name,discipline,event_date,result,source_url) VALUES($1,$2,$3,$4,$5::date,$6,$7) ON CONFLICT(candidate_id,event_name,event_date,result) DO UPDATE SET source_url=EXCLUDED.source_url,updated_at=now() RETURNING to_jsonb(fsp_participations)").bind(&id).bind(&actor.subject_id).bind(p.event_name.trim()).bind(p.discipline.trim()).bind(p.event_date.filter(|x|!x.is_empty())).bind(p.result.trim()).bind(p.source_url.trim()).fetch_one(&s.db).await?;
    Ok(Json(
        json!({"participation":item,"message":"Сведения сохранены как заявленные. Влияние на подтверждение появится после сверки с реестром ФСП."}),
    ))
}
