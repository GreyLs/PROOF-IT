use crate::AppState;
use serde_json::{Value, json};
use std::{collections::HashMap, path::Path};

pub async fn audit(
    s: &AppState,
    actor: &str,
    action: &str,
    entity: &str,
    details: Value,
) -> crate::error::Result<()> {
    sqlx::query("INSERT INTO audit_events(actor_id,action,entity_id,details) VALUES($1,$2,$3,$4)")
        .bind(actor)
        .bind(action)
        .bind(entity)
        .bind(details)
        .execute(&s.db)
        .await?;
    Ok(())
}
fn read(name: &str) -> anyhow::Result<Vec<HashMap<String, String>>> {
    Ok(csv::Reader::from_path(Path::new("data").join(name))?
        .deserialize()
        .collect::<std::result::Result<_, _>>()?)
}
fn split(s: &str) -> Vec<String> {
    s.split(';')
        .map(str::trim)
        .filter(|x| !x.is_empty())
        .map(str::to_owned)
        .collect()
}

pub async fn seed(s: &AppState) -> anyhow::Result<()> {
    anyhow::ensure!(
        s.demo,
        "Seeding synthetic benchmark requires FSP_DEMO_MODE=true"
    );
    let done: bool =
        sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM system_meta WHERE key='seed_version')")
            .fetch_one(&s.db)
            .await?;
    if done {
        tracing::info!("Seed already present; keeping user changes");
        return Ok(());
    }
    let mut tx = s.db.begin().await?;
    for row in read("employers.csv")? {
        sqlx::query("INSERT INTO companies(id,name,description,industry,contact,synthetic) VALUES($1,$2,$3,$4,$5,true)")
            .bind(&row["company_id"]).bind(&row["company_name"]).bind(&row["company_description"]).bind(&row["industry"]).bind("demo@company.example").execute(&mut *tx).await?;
    }
    sqlx::query("UPDATE companies SET name='Вектор · демокомпания',description='Продуктовая команда: создаём сервисы для спорта и цифрового образования.',contact='team@vector.example' WHERE id='EMP0001'").execute(&mut *tx).await?;
    let mut achievements: HashMap<String, Vec<Value>> = HashMap::new();
    for row in read("fsp_achievements.csv")? {
        achievements.entry(row["candidate_id"].clone()).or_default().push(json!({"event":row["event_name"],"year":row["event_year"],"discipline":row["discipline"],"result":row["result_band"],"status":"mock_verified","source_ref":row["source_ref"],"synthetic":true}));
    }
    for row in read("candidates.csv")? {
        let id = &row["candidate_id"];
        let fsp = row["has_fsp_history"] == "true";
        let achievement = achievements.remove(id).unwrap_or_default();
        sqlx::query("INSERT INTO candidates(id,display_name,specialization,declared_grade,confirmed_grade,experience_years,skills,expected_salary,work_format,visibility,consent_processing,consent_publication,test_score,test_valid_until,grade_changed_at,profile_updated_at,fsp_id,fsp_status,fsp_score,achievements,synthetic) VALUES($1,$2,$3,$4,$4,$5,$6,$7,$8,'employer_searchable',true,true,$9,'2027-01-03T00:00:00Z',now()-interval '91 days',now()-($10*interval '1 day'),$11,$12,$13,$14,true)")
            .bind(id).bind(&row["display_name"]).bind(&row["specialization"]).bind(&row["current_grade"]).bind(row["experience_years"].parse::<f64>()?).bind(split(&row["skills"]))
            .bind(row["expected_salary_from_rub"].parse::<i32>()?).bind(&row["work_format"]).bind(row["test_score_pct"].parse::<i32>()?).bind(row["profile_freshness_days"].parse::<f64>()?)
            .bind(if fsp{Some(format!("MOCK-FSP-{id}"))}else{None}).bind(if fsp{"mock_verified"}else{"not_linked"}).bind(row["fsp_evidence_score"].parse::<i32>()?).bind(json!(achievement)).execute(&mut *tx).await?;
    }
    for row in read("candidates.csv")? {
        if let Some(resume) = row.get("resume_text").filter(|s| !s.is_empty()) {
            sqlx::query("UPDATE candidates SET about=$2,assessment_method='synthetic_scenario',visibility=$3 WHERE id=$1 AND synthetic")
                .bind(&row["candidate_id"]).bind(resume).bind(row.get("profile_visibility").map(String::as_str).unwrap_or("private")).execute(&mut *tx).await?;
        }
    }
    for row in read("vacancies.csv")? {
        let synthetic = row["is_synthetic"] == "true";
        // Leadership is expressed by the specialization itself.  Keep the
        // imported benchmark consistent with the live vacancy rule even when
        // an older CSV still carries a historical junior/middle/senior label.
        let grade = if crate::matching::is_leadership_spec(&row["specialization"]) {
            ""
        } else {
            row["target_grade"].as_str()
        };
        sqlx::query("INSERT INTO vacancies(id,company_id,title,description,specialization,grade,skills,salary_from,salary_to,origin,source_ref,synthetic,created_at) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13::date)")
            .bind(&row["vacancy_id"]).bind(&row["company_id"]).bind(&row["title"])
            .bind(row.get("description").filter(|s|!s.is_empty()).cloned().unwrap_or_else(||format!("{}\n\nПотребность: {}.\n{}",row["title"],row["matching_requirement_profile"],if synthetic{"Калиброванный тестовый сценарий. Не реальное предложение работы."}else{"Снимок официального открытого API «Работа России». Компания обезличена; профессиональные требования дополнены словарём команды."})))
            .bind(&row["specialization"]).bind(grade).bind(split(&row["matching_requirement_profile"]))
            .bind(row["salary_from_rub"].parse::<i32>()?).bind(row["salary_to_rub"].parse::<i32>()?).bind(if synthetic{"calibrated_scenario"}else{"trudvsem_snapshot"}).bind(&row["source_ref"]).bind(synthetic).bind(&row["publication_date"]).execute(&mut *tx).await?;
    }
    for row in read("assessment_attempts.csv")? {
        sqlx::query("INSERT INTO assessments(id,candidate_id,specialization,grade,blueprint_version,seed,items,status,score,finished_at,synthetic) VALUES($1,$2,$3,$4,$5,$6,'[]','completed_seed',$7,now()-interval '91 days',true)")
            .bind(&row["attempt_id"]).bind(&row["candidate_id"]).bind(&row["specialization"]).bind(&row["result_grade"]).bind(&row["blueprint_id"]).bind(&row["unique_parameter_seed"]).bind(row["score_pct"].parse::<i32>()?).execute(&mut *tx).await?;
    }
    // Historical CSV interactions have future timestamps. Keep them as benchmark artifacts;
    // start the live workflow clean so the demo reflects actual transitions and consent.
    for (id, email, role, subject) in [
        (
            "demo-employer",
            "employer@demo.example",
            "employer",
            "EMP0001",
        ),
        (
            "demo-candidate",
            "candidate@demo.example",
            "candidate",
            "PC00057",
        ),
    ] {
        let unusable = crate::auth::password_hash(&crate::auth::new_id("random_"))?;
        sqlx::query("INSERT INTO users(id,email,password_hash,role,email_verified,subject_id,synthetic) VALUES($1,$2,$3,$4,true,$5,true)").bind(id).bind(email).bind(unusable).bind(role).bind(subject).execute(&mut *tx).await?;
    }
    sqlx::query("UPDATE candidates SET full_name='Демо-кандидат',email='candidate@demo.example',about='Демонстрационный профиль. Контакты вымышлены и используются для проверки механики согласия.' WHERE id='PC00057'").execute(&mut *tx).await?;
    sqlx::query("INSERT INTO system_meta(key,value) VALUES('seed_version',$1)").bind(json!({"version":"1.2","revision":"2026-10-06","candidates":read("candidates.csv")?.len(),"vacancies":read("vacancies.csv")?.len(),"source":"user-supplied benchmark + authored leadership scenarios","synthetic_candidates":true})).execute(&mut *tx).await?;
    tx.commit().await?;
    tracing::info!("Seed loaded: specialist and leadership benchmark");
    Ok(())
}
