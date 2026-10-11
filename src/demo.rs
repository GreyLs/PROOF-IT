//! Password-authenticated synthetic test accounts; no guest session issuance.
use crate::{AppState, auth::{Actor, new_id}, error::{AppError, Result}};
use axum::{Json, extract::State};
use serde_json::{Value, json};

const CANDIDATE_LOGIN: &str = "candidate@demo.proofit.invalid";
const EMPLOYER_LOGIN: &str = "employer@demo.proofit.invalid";
// Public, synthetic-only credentials. Not operator, identity-provider or production secrets.
const DEMO_PASSWORD: &str = "Proofit-Demo-2026!";

fn enabled(s: &AppState) -> Result<()> {
    if s.demo && !s.security.production { Ok(()) } else { Err(AppError::missing()) }
}
async fn seed_pair(s: &AppState, workspace: &str) -> Result<()> {
    enabled(s)?;
    let candidate = format!("{workspace}_candidate");
    let company = format!("{workspace}_company");
    let cu = format!("{workspace}_cu");
    let eu = format!("{workspace}_eu");
    let password = DEMO_PASSWORD.to_string();
    let hash = tokio::task::spawn_blocking(move || crate::auth::password_hash(&password))
        .await.map_err(|_| AppError::unavailable("Повторите позже"))?
        .map_err(|_| AppError::unavailable("Повторите позже"))?;
    let mut tx = s.db.begin().await?;
    sqlx::query("INSERT INTO candidates(id,display_name,specialization,declared_grade,experience_years,skills,about,expected_salary,consent_processing,consent_publication,synthetic) VALUES($1,'Демо-кандидат · синтетический профиль','backend_python','middle',4,ARRAY['Python','SQL','PostgreSQL','Docker'],'Синтетический профиль для проверки сквозного сценария. Оценки ещё не подтверждены.',180000,true,false,true)")
        .bind(&candidate).execute(&mut *tx).await?;
    sqlx::query("INSERT INTO companies(id,name,description,contact,verification_status,synthetic) VALUES($1,'Proofit Demo Labs','Синтетическая компания: вакансии и отклики доступны в связанных демо-кабинетах.','Встроенные сообщения','verified',true)")
        .bind(&company).execute(&mut *tx).await?;
    for (uid, role, subject, email) in [
        (&cu,"candidate",&candidate,CANDIDATE_LOGIN),
        (&eu,"employer",&company,EMPLOYER_LOGIN),
    ] {
        sqlx::query("INSERT INTO users(id,email,password_hash,role,email_verified,subject_id,synthetic,is_guest) VALUES($1,$2,$3,$4,true,$5,true,false)")
            .bind(uid).bind(email).bind(&hash).bind(role).bind(subject).execute(&mut *tx).await?;
    }
    for (i,title,spec,skills,salary) in [
        (0,"Python Backend Engineer · демо","backend_python",vec!["Python","SQL","PostgreSQL","Docker"],180000),
        (1,"Frontend Engineer · демо","frontend_development",vec!["TypeScript","React","CSS"],170000),
    ] {
        let rid = format!("{workspace}_resume_{i}");
        sqlx::query("INSERT INTO resume_profiles(id,candidate_id,target_position,specialization,declared_grade,experience_years,skills,about,expected_salary,visibility,status) VALUES($1,$2,$3,$4,'middle',4,$5,'Синтетическое целевое резюме. Данные доступны работодателю только после отклика или публикации.',$6,'private','draft')")
            .bind(&rid).bind(&candidate).bind(title).bind(spec).bind(&skills).bind(salary).execute(&mut *tx).await?;
        sqlx::query("INSERT INTO qualification_tests(id,resume_id,status,generation_status,seed) VALUES($1,$2,'ready','ready',$3)")
            .bind(format!("{workspace}_test_{i}")).bind(&rid).bind(new_id("seed_")).execute(&mut *tx).await?;
        sqlx::query("INSERT INTO vacancies(id,company_id,title,description,specialization,grade,skills,salary_from,salary_to,work_format,synthetic,source_ref) VALUES($1,$2,$3,'Синтетическая вакансия для проверки: выберите резюме, отправьте отклик, выйдите и войдите с учетными данными работодателя, чтобы продолжить диалог.',$4,'middle',$5,$6,$7,'удалённо',true,$8)")
            .bind(format!("{workspace}_vacancy_{i}")).bind(&company).bind(title).bind(spec).bind(&skills).bind(salary).bind(salary+80000).bind(workspace).execute(&mut *tx).await?;
    }
    sqlx::query("INSERT INTO demo_workspaces(id,candidate_user_id,employer_user_id,shared,expires_at) VALUES($1,$2,$3,true,'infinity'::timestamptz)")
        .bind(workspace).bind(&cu).bind(&eu).execute(&mut *tx).await?;
    tx.commit().await?;
    Ok(())
}

pub async fn provision_shared(s: &AppState) -> Result<()> {
    enabled(s)?;
    // Called once by the identity service; never overwrite an existing account.
    let exists: bool = sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM demo_workspaces WHERE id='DEMO_SHARED_V1' AND shared)").fetch_one(&s.db).await?;
    if !exists { seed_pair(s,"DEMO_SHARED_V1").await?; }
    Ok(())
}
pub async fn context(State(s): State<AppState>, actor: Actor) -> Result<Json<Value>> {
    enabled(&s)?;
    let item: Option<Value> = sqlx::query_scalar("SELECT jsonb_build_object('id',id,'shared',shared,'candidate_id',(SELECT subject_id FROM users WHERE id=candidate_user_id),'company_id',(SELECT subject_id FROM users WHERE id=employer_user_id)) FROM demo_workspaces WHERE (candidate_user_id=$1 OR employer_user_id=$1) AND expires_at>now()")
        .bind(&actor.id).fetch_optional(&s.db).await?;
    Ok(Json(json!({"workspace":item})))
}
