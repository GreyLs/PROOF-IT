use crate::{
    AppState,
    auth::Actor,
    error::{AppError, Result},
    matching::valid_spec,
};
use axum::{Json, extract::State};
use serde::Deserialize;
use serde_json::{Value, json};

pub async fn own(State(s): State<AppState>, actor: Actor) -> Result<Json<Value>> {
    let query = if actor.role == "candidate" {
        "SELECT to_jsonb(c) FROM candidates c WHERE id=$1"
    } else {
        "SELECT to_jsonb(c) FROM companies c WHERE id=$1"
    };
    let profile: Value = sqlx::query_scalar(query)
        .bind(&actor.subject_id)
        .fetch_one(&s.db)
        .await?;
    Ok(Json(json!({"profile":profile})))
}
#[derive(Deserialize)]
pub struct ProfileInput {
    pub full_name: String,
    pub email: String,
    pub phone: String,
    pub specialization: String,
    pub declared_grade: String,
    pub industry: String,
    pub experience_years: f64,
    pub skills: Vec<String>,
    pub soft_skills: Vec<String>,
    pub about: String,
    pub expected_salary: i32,
    pub work_format: String,
    pub visibility: String,
    pub consent_processing: bool,
    pub consent_publication: bool,
    pub fsp_id: Option<String>,
    pub version: i32,
}
pub async fn update(
    State(s): State<AppState>,
    actor: Actor,
    Json(p): Json<ProfileInput>,
) -> Result<Json<Value>> {
    actor.require("candidate")?;
    if (!p.specialization.is_empty() && !valid_spec(&p.specialization))
        || !crate::matching::valid_role_grade(&p.specialization, &p.declared_grade)
        || p.expected_salary < 0
        || p.expected_salary > 100_000_000
        || !p.experience_years.is_finite()
        || !(0.0..=80.).contains(&p.experience_years)
    {
        return Err(AppError::bad(
            "Проверьте специализацию, грейд, стаж и зарплату",
        ));
    }
    if p.full_name.len() > 250
        || p.email.len() > 254
        || p.phone.len() > 50
        || p.about.len() > 15000
        || p.skills.len() > 60
        || p.soft_skills.len() > 30
        || p.skills
            .iter()
            .chain(p.soft_skills.iter())
            .any(|x| x.len() > 100)
        || p.work_format.len() > 100
        || p.industry.len() > 150
        || p.fsp_id.as_ref().is_some_and(|x| x.len() > 150)
    {
        return Err(AppError::bad("Превышена допустимая длина поля"));
    }
    if !["private", "employer_searchable"].contains(&p.visibility.as_str()) {
        return Err(AppError::bad("Некорректная видимость"));
    }
    if p.visibility == "employer_searchable" && (!p.consent_processing || !p.consent_publication) {
        return Err(AppError::bad("Для публикации нужны оба согласия"));
    }
    let mut tx = s.db.begin().await?;
    let old:Option<(String,String,Option<String>,String,String,String,bool)>=sqlx::query_as("SELECT specialization,declared_grade,fsp_id,fsp_status,about,full_name,consent_processing FROM candidates WHERE id=$1 AND version=$2 FOR UPDATE").bind(&actor.subject_id).bind(p.version).fetch_optional(&mut *tx).await?;
    let Some((old_spec, old_grade, old_fsp, old_status, old_about, old_name, old_consent)) = old
    else {
        return Err(AppError::conflict(
            "Профиль изменён в другой вкладке. Обновите страницу.",
        ));
    };
    let fsp = p.fsp_id.filter(|x| !x.trim().is_empty());
    let fsp_changed = old_fsp != fsp;
    let status = if fsp_changed {
        if fsp.is_some() {
            "pending"
        } else {
            "not_linked"
        }
    } else {
        &old_status
    };
    // Changing a self-declared specialization cannot carry a validated grade into a new discipline.
    let changed = old_spec != p.specialization;
    // A declared move to another grade must not create a fresh validation path
    // immediately after a previous one. `cooldown` checks this timestamp
    // against the independently confirmed (or historical) grade.
    let grade_changed = old_grade != p.declared_grade;
    let employment_changed = old_about != p.about
        || old_name != p.full_name.trim()
        || (!old_consent && p.consent_processing);
    let mut profile:Value=sqlx::query_scalar("UPDATE candidates SET full_name=$2,email=$3,phone=$4,specialization=$5,declared_grade=$6,industry=$7,experience_years=$8,skills=$9,soft_skills=$10,about=$11,expected_salary=$12,work_format=$13,visibility=$14,consent_processing=$15,consent_publication=$16,fsp_id=$17,fsp_status=$18,fsp_score=CASE WHEN $19 THEN 0 ELSE fsp_score END,achievements=CASE WHEN $19 THEN '[]'::jsonb ELSE achievements END,confirmed_grade=CASE WHEN $20 THEN NULL ELSE confirmed_grade END,test_score=CASE WHEN $20 THEN 0 ELSE test_score END,test_valid_until=CASE WHEN $20 THEN NULL ELSE test_valid_until END,grade_changed_at=CASE WHEN $21 THEN now() ELSE grade_changed_at END,profile_updated_at=now(),version=version+1 WHERE id=$1 RETURNING to_jsonb(candidates)")
        .bind(&actor.subject_id).bind(p.full_name.trim()).bind(p.email.trim()).bind(p.phone.trim()).bind(p.specialization).bind(p.declared_grade).bind(p.industry).bind(p.experience_years).bind(p.skills).bind(p.soft_skills).bind(p.about).bind(p.expected_salary).bind(p.work_format).bind(p.visibility).bind(p.consent_processing).bind(p.consent_publication).bind(fsp).bind(status).bind(fsp_changed).bind(changed).bind(grade_changed).fetch_one(&mut *tx).await?;
    if employment_changed && p.consent_processing && profile["employment_document_id"].is_string() {
        sqlx::query("UPDATE documents SET status='queued',attempts=0,next_attempt_at=now(),progress=0,error=NULL WHERE id=$1 AND status<>'processing'").bind(profile["employment_document_id"].as_str()).execute(&mut *tx).await?;
        profile=sqlx::query_scalar("UPDATE candidates SET employment_check=employment_check || jsonb_build_object('status','queued','message','Резюме изменено: повторяем сверку с выпиской. Предыдущее ограничение сохраняется до согласования сведений.') WHERE id=$1 RETURNING to_jsonb(candidates)").bind(&actor.subject_id).fetch_one(&mut *tx).await?;
    }
    sqlx::query("INSERT INTO audit_events(actor_id,action,entity_id,details) VALUES($1,'profile.consent_updated',$2,$3)").bind(&actor.id).bind(&actor.subject_id).bind(json!({"processing":p.consent_processing,"publication":p.consent_publication})).execute(&mut *tx).await?;
    tx.commit().await?;
    Ok(Json(json!({"profile":profile})))
}
#[derive(Deserialize)]
pub struct CompanyInput {
    pub name: String,
    pub description: String,
    pub industry: String,
    pub contact: String,
}
pub async fn company_update(
    State(s): State<AppState>,
    actor: Actor,
    Json(p): Json<CompanyInput>,
) -> Result<Json<Value>> {
    actor.require("employer")?;
    if p.name.trim().len() < 2
        || p.name.len() > 250
        || p.description.len() > 15000
        || p.contact.trim().is_empty()
        || p.contact.len() > 500
        || p.industry.len() > 150
    {
        return Err(AppError::bad(
            "Проверьте название, описание и контакты компании",
        ));
    }
    let profile:Value=sqlx::query_scalar("UPDATE companies SET name=$2,description=$3,industry=$4,contact=$5,updated_at=now() WHERE id=$1 RETURNING to_jsonb(companies)").bind(&actor.subject_id).bind(p.name.trim()).bind(p.description).bind(p.industry).bind(p.contact).fetch_one(&s.db).await?;
    Ok(Json(json!({"profile":profile})))
}
