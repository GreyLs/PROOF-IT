//! Private CatBoost inference adapter. Feature assembly and authorization stay
//! in Rust; the localhost Python service only evaluates already assembled data.
use crate::{
    AppState,
    auth::Actor,
    error::{AppError, Result},
};
use axum::{
    Json,
    extract::{Path, State},
};
use serde_json::{Value, json};
use std::time::Duration;

fn grade_pressure(grade: &str) -> i32 {
    match grade {
        "senior" => 2,
        "middle" => 1,
        _ => 0,
    }
}
fn remote_flexibility(value: &str) -> f64 {
    let value = value.to_lowercase();
    if value.contains("удал") {
        1.0
    } else if value.contains("гибрид") {
        0.65
    } else {
        0.25
    }
}
fn clamp(value: f64, low: f64, high: f64) -> f64 {
    value.max(low).min(high)
}
fn average_overlap<'a>(required: &[String], market: impl Iterator<Item = &'a [String]>) -> f64 {
    if required.is_empty() {
        return 1.0;
    }
    let required: std::collections::HashSet<String> =
        required.iter().map(|skill| skill.to_lowercase()).collect();
    let mut total = 0.0;
    let mut rows = 0usize;
    for skills in market {
        let matched = skills
            .iter()
            .map(|skill| skill.to_lowercase())
            .collect::<std::collections::HashSet<_>>()
            .intersection(&required)
            .count();
        total += matched as f64 / required.len() as f64;
        rows += 1;
    }
    if rows == 0 { 0.0 } else { total / rows as f64 }
}

async fn infer(s: &AppState, task: &str, features: Value) -> Result<Value> {
    let client = reqwest::Client::builder()
        .connect_timeout(Duration::from_secs(1))
        .timeout(Duration::from_secs(3))
        .no_proxy()
        .build()
        .map_err(|_| AppError::unavailable("Прогноз временно недоступен"))?;
    let response = client
        .post(format!("{}/predict", s.forecast_url))
        .json(&json!({"task":task,"features":features}))
        .send()
        .await
        .map_err(|_| AppError::unavailable("Прогноз временно недоступен"))?;
    if !response.status().is_success() {
        return Err(AppError::unavailable("Прогноз временно недоступен"));
    }
    response
        .json()
        .await
        .map_err(|_| AppError::unavailable("Прогноз временно недоступен"))
}

pub async fn vacancy_features(s: &AppState, actor: &Actor, id: &str) -> Result<Value> {
    actor.verified_employer(&s).await?;
    let row: Option<(String, String, String, Vec<String>, i32, i32, String, f64)> = sqlx::query_as("SELECT v.company_id,v.specialization,v.grade,v.skills,v.salary_from,v.salary_to,v.work_format,c.market_rating::float8 FROM vacancies v JOIN companies c ON c.id=v.company_id WHERE v.id=$1").bind(&id).fetch_optional(&s.db).await?;
    let Some((
        company_id,
        specialization,
        grade,
        skills,
        salary_from,
        salary_to,
        work_format,
        company_rating,
    )) = row
    else {
        return Err(AppError::missing());
    };
    if company_id != actor.subject_id {
        return Err(AppError::forbidden());
    }
    let relevant: i64 = sqlx::query_scalar("SELECT count(DISTINCT r.candidate_id) FROM intelligence.resume_category_evidence r WHERE r.employer_eligible AND r.specialization=$1 AND (CASE r.confirmed_grade WHEN 'junior' THEN 0 WHEN 'middle' THEN 1 ELSE 2 END)>=(CASE $2 WHEN 'junior' THEN 0 WHEN 'middle' THEN 1 ELSE 2 END)").bind(&specialization).bind(&grade).fetch_one(&s.db).await?;
    let median: Option<f64> = sqlx::query_scalar("SELECT CASE WHEN count(DISTINCT r.candidate_id)>=5 THEN percentile_cont(0.5) WITHIN GROUP (ORDER BY r.expected_salary)::float8 ELSE NULL END FROM intelligence.resume_category_evidence r WHERE r.employer_eligible AND r.specialization=$1 AND r.confirmed_grade=$2 AND r.expected_salary>0").bind(&specialization).bind(&grade).fetch_one(&s.db).await?;
    let market_salary = median.unwrap_or(((salary_from + salary_to) as f64 / 2.0).max(1.0));
    let market_skills: Vec<(Vec<String>,)> = sqlx::query_as("SELECT r.skills FROM intelligence.resume_category_evidence r WHERE r.employer_eligible AND r.specialization=$1").bind(&specialization).fetch_all(&s.db).await?;
    let coverage = average_overlap(&skills, market_skills.iter().map(|row| row.0.as_slice()));
    let features = json!({"relevant_candidates":relevant,"salary_competitiveness":clamp(((salary_from+salary_to) as f64/2.0)/market_salary,0.5,1.7),"company_rating":company_rating,"stack_complexity":skills.len().max(1),"skill_coverage":clamp(coverage,0.0,1.0),"seniority_pressure":grade_pressure(&grade),"remote_flexibility":remote_flexibility(&work_format)});
    Ok(features)
}

pub async fn candidate_features(s: &AppState, actor: &Actor, id: &str) -> Result<Value> {
    actor.require("candidate")?;
    let row: Option<(String, String, String, f64, Vec<String>, i32, String, String, bool)> = sqlx::query_as("SELECT r.specialization,r.declared_grade,r.about,r.experience_years,r.skills,r.expected_salary,r.work_format,r.status,coalesce(q.passed,false) FROM resume_profiles r LEFT JOIN qualification_tests q ON q.resume_id=r.id WHERE r.id=$1 AND r.candidate_id=$2").bind(&id).bind(&actor.subject_id).fetch_optional(&s.db).await?;
    let Some((
        specialization,
        grade,
        about,
        experience,
        skills,
        expected_salary,
        work_format,
        status,
        passed,
    )) = row
    else {
        return Err(AppError::missing());
    };
    let market: Vec<(Vec<String>, i32)> = sqlx::query_as("SELECT v.skills,v.salary_to FROM vacancies v WHERE v.status='published' AND v.specialization=$1 AND (CASE v.grade WHEN 'junior' THEN 0 WHEN 'middle' THEN 1 ELSE 2 END)<=(CASE $2 WHEN 'junior' THEN 0 WHEN 'middle' THEN 1 ELSE 2 END)").bind(&specialization).bind(&grade).fetch_all(&s.db).await?;
    let vacancies = market.len() as i64;
    let mut salaries: Vec<i32> = market.iter().map(|row| row.1).collect();
    salaries.sort_unstable();
    let salary_median = salaries
        .get(salaries.len().saturating_sub(1) / 2)
        .map(|value| *value as f64);
    let skill_match = average_overlap(&skills, market.iter().map(|row| row.0.as_slice()));
    let activity: i64 = sqlx::query_scalar("SELECT count(*) FROM applications WHERE candidate_id=$1 AND created_at>=now()-interval '30 days'").bind(&actor.subject_id).fetch_one(&s.db).await?;
    let completeness = ((if about.trim().len() >= 120 {
        0.35
    } else {
        0.12
    }) + (skills.len().min(12) as f64 / 12.0) * 0.45
        + if status == "published" { 0.20 } else { 0.05 })
    .min(1.0);
    let salary_alignment = if expected_salary <= 0 {
        0.9
    } else {
        clamp(
            salary_median.unwrap_or(expected_salary as f64) / expected_salary as f64,
            0.5,
            1.6,
        )
    };
    let features = json!({"relevant_vacancies":vacancies,"salary_alignment":salary_alignment,"skill_match":clamp(skill_match,0.0,1.0),"profile_completeness":completeness,"qualification_signal":if passed {1} else {0},"experience_years":experience,"application_activity":activity,"remote_flexibility":remote_flexibility(&work_format)});
    Ok(features)
}

pub async fn vacancy_fill(
    State(s): State<AppState>,
    actor: Actor,
    Path(id): Path<String>,
) -> Result<Json<Value>> {
    let features = vacancy_features(&s, &actor, &id).await?;
    let prediction = infer(&s, "vacancy_fill", features).await?;
    Ok(Json(json!({"vacancy_id":id,"forecast":prediction})))
}
pub async fn candidate_job_search(
    State(s): State<AppState>,
    actor: Actor,
    Path(id): Path<String>,
) -> Result<Json<Value>> {
    let features = candidate_features(&s, &actor, &id).await?;
    let prediction = infer(&s, "candidate_job_search", features).await?;
    Ok(Json(json!({"resume_id":id,"forecast":prediction})))
}
