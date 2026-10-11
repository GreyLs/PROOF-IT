use crate::{
    AppState,
    auth::{Actor, new_id},
    error::{AppError, Result},
    matching::valid_spec,
};
use axum::{
    Json,
    extract::{Path, Query, State},
};
use serde::Deserialize;
use serde_json::{Value, json};

pub fn salary(from: i32, to: i32) -> Result<()> {
    if from <= 0 || to < from || to > 100_000_000 {
        Err(AppError::bad(
            "Укажите обе границы зарплаты в рублях: 0 < от ≤ до",
        ))
    } else {
        Ok(())
    }
}
#[derive(Deserialize)]
pub struct Offer {
    pub candidate_id: String,
    pub resume_id: Option<String>,
    pub vacancy_id: Option<String>,
    pub title: String,
    pub description: String,
    pub salary_from: i32,
    pub salary_to: i32,
    pub idempotency_key: String,
}
pub async fn invite(
    State(s): State<AppState>,
    actor: Actor,
    Json(p): Json<Offer>,
) -> Result<Json<Value>> {
    actor.verified_employer(&s).await?;
    salary(p.salary_from, p.salary_to)?;
    if p.title.trim().len() < 3
        || p.title.len() > 250
        || p.description.trim().len() < 10
        || p.description.len() > 15000
        || p.idempotency_key.is_empty()
        || p.idempotency_key.len() > 100
    {
        return Err(AppError::bad(
            "Добавьте название, описание предложения и ключ запроса",
        ));
    }
    let mut tx = s.db.begin().await?;
    sqlx::query("SELECT id FROM candidates WHERE id=$1 FOR SHARE")
        .bind(&p.candidate_id).execute(&mut *tx).await?;
    let candidate:bool=sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM intelligence.resume_category_evidence r WHERE r.candidate_id=$1 AND r.employer_eligible AND ($2::text IS NULL OR r.id=$2))").bind(&p.candidate_id).bind(&p.resume_id).fetch_one(&mut *tx).await?;
    if !candidate {
        return Err(AppError::missing());
    }
    if let Some(id) = &p.vacancy_id {
        let own: bool = sqlx::query_scalar(
            "SELECT EXISTS(SELECT 1 FROM vacancies WHERE id=$1 AND company_id=$2)",
        )
        .bind(id)
        .bind(&actor.subject_id)
        .fetch_one(&s.db)
        .await?;
        if !own {
            return Err(AppError::bad(
                "Можно привязать только вакансию своей компании",
            ));
        }
    }
    let (name, contact): (String, String) =
        sqlx::query_as("SELECT name,contact FROM companies WHERE id=$1")
            .bind(&actor.subject_id)
            .fetch_one(&s.db)
            .await?;
    if contact.trim().is_empty() {
        return Err(AppError::bad(
            "Сначала укажите способ связи в профиле компании",
        ));
    }
    let id = new_id("I");
    // A historical profile has no resume FK; its virtual ID cannot reference
    // a different candidate and was checked by the projection above.
    let resume_id = p.resume_id.as_ref().filter(|id| **id != format!("Rlegacy_{}", p.candidate_id)).cloned();
    let result:Value=sqlx::query_scalar("INSERT INTO invitations(id,company_id,candidate_id,resume_id,vacancy_id,title,description,salary_from,salary_to,contact,company_name,idempotency_key) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12) ON CONFLICT(company_id,idempotency_key) DO UPDATE SET idempotency_key=EXCLUDED.idempotency_key RETURNING to_jsonb(invitations)")
        .bind(&id).bind(&actor.subject_id).bind(&p.candidate_id).bind(&resume_id).bind(&p.vacancy_id).bind(&p.title).bind(&p.description).bind(p.salary_from).bind(p.salary_to).bind(contact).bind(name).bind(&p.idempotency_key).fetch_one(&mut *tx).await?;
    if result["candidate_id"] != json!(p.candidate_id)
        || result["resume_id"] != json!(resume_id)
        || result["vacancy_id"] != json!(p.vacancy_id)
        || result["title"] != json!(p.title)
        || result["description"] != json!(p.description)
        || result["salary_from"] != json!(p.salary_from)
        || result["salary_to"] != json!(p.salary_to)
    {
        return Err(AppError::conflict(
            "Этот ключ запроса уже использован для другого предложения",
        ));
    }
    let conversation_id = crate::conversations::ensure_thread(
        &mut tx,
        result["candidate_id"].as_str().unwrap_or_default(),
        result["company_id"].as_str().unwrap_or_default(),
        result["vacancy_id"].as_str(),
        result["resume_id"].as_str(),
        "invitation",
    )
    .await?;
    sqlx::query(
        "INSERT INTO audit_events(actor_id,action,entity_id) VALUES($1,'invitation.sent',$2)",
    )
    .bind(&actor.id)
    .bind(result["id"].as_str().unwrap_or(&id))
    .execute(&mut *tx)
    .await?;
    tx.commit().await?;
    Ok(Json(
        json!({"invitation":result,"conversation_id":conversation_id}),
    ))
}
pub async fn invitations(State(s): State<AppState>, actor: Actor) -> Result<Json<Value>> {
    let query = if actor.role == "candidate" {
        "SELECT to_jsonb(i) FROM invitations i WHERE candidate_id=$1 ORDER BY created_at DESC LIMIT 300"
    } else {
        "SELECT to_jsonb(i)||jsonb_build_object('candidate_name',c.display_name) FROM invitations i JOIN candidates c ON c.id=i.candidate_id WHERE i.company_id=$1 ORDER BY i.created_at DESC LIMIT 300"
    };
    let items: Vec<Value> = sqlx::query_scalar(query)
        .bind(&actor.subject_id)
        .fetch_all(&s.db)
        .await?;
    Ok(Json(json!({"items":items})))
}
#[derive(Deserialize)]
pub struct Status {
    pub status: String,
    pub share_with_ats: Option<bool>,
}
pub async fn respond(
    State(s): State<AppState>,
    actor: Actor,
    Path(id): Path<String>,
    Json(p): Json<Status>,
) -> Result<Json<Value>> {
    actor.require("candidate")?;
    if !["viewed", "accepted", "declined"].contains(&p.status.as_str()) {
        return Err(AppError::bad("Недопустимый статус приглашения"));
    }
    let mut tx = s.db.begin().await?;
    let old: Option<String> = sqlx::query_scalar(
        "SELECT status FROM invitations WHERE id=$1 AND candidate_id=$2 FOR UPDATE",
    )
    .bind(&id)
    .bind(&actor.subject_id)
    .fetch_optional(&mut *tx)
    .await?;
    let old = old.ok_or_else(AppError::missing)?;
    if old != p.status && !matches!(old.as_str(), "sent" | "viewed") {
        return Err(AppError::conflict("На это приглашение уже дан ответ"));
    }
    let result:Value=sqlx::query_scalar("UPDATE invitations SET status=$2,responded_at=CASE WHEN $2 IN ('accepted','declined') THEN coalesce(responded_at,now()) ELSE responded_at END WHERE id=$1 RETURNING to_jsonb(invitations)").bind(&id).bind(&p.status).fetch_one(&mut *tx).await?;
    if p.status == "accepted" && p.share_with_ats == Some(true) {
        if let Some(vacancy_id) = result["vacancy_id"].as_str() {
            crate::talantix::enqueue(
                &mut tx,
                result["company_id"].as_str().unwrap_or_default(),
                &actor.subject_id,
                vacancy_id,
                "invitation.accepted",
                &id,
            )
            .await?;
        }
    }
    sqlx::query("INSERT INTO audit_events(actor_id,action,entity_id,details) VALUES($1,'invitation.responded',$2,$3)").bind(&actor.id).bind(&id).bind(json!({"from":old,"to":p.status})).execute(&mut *tx).await?;
    tx.commit().await?;
    Ok(Json(
        json!({"invitation":result,"contacts_released":p.status=="accepted"}),
    ))
}
#[derive(Deserialize, Default)]
pub struct VacancyQuery {
    pub company_id: Option<String>,
    pub specialization: Option<String>,
    pub grade: Option<String>,
    pub mine: Option<bool>,
    pub q: Option<String>,
    pub limit: Option<i64>,
    pub offset: Option<i64>,
}
pub async fn vacancies(
    State(s): State<AppState>,
    actor: Actor,
    Query(q): Query<VacancyQuery>,
) -> Result<Json<Value>> {
    if q.mine == Some(true) {
        actor.verified_employer(&s).await?;
    }
    let company = if q.mine == Some(true) {
        actor.subject_id
    } else {
        String::new()
    };
    let items:Vec<Value>=sqlx::query_scalar("SELECT to_jsonb(v)||jsonb_build_object('company_name',c.name,'application_count',(SELECT count(*) FROM applications a WHERE a.vacancy_id=v.id AND a.status<>'withdrawn')) FROM vacancies v JOIN companies c ON c.id=v.company_id WHERE (v.status='published' OR v.company_id=$1) AND ($1='' OR v.company_id=$1) AND ($2='' OR v.specialization=$2) AND ($3='' OR v.grade=$3) AND ($4='' OR v.title ILIKE '%'||$4||'%') AND ($7='' OR v.company_id=$7) ORDER BY v.created_at DESC,v.id LIMIT $5 OFFSET $6")
        .bind(company).bind(q.specialization.unwrap_or_default()).bind(q.grade.unwrap_or_default()).bind(q.q.unwrap_or_default()).bind(q.limit.unwrap_or(60).clamp(1,500)).bind(q.offset.unwrap_or(0).max(0)).bind(q.company_id.unwrap_or_default()).fetch_all(&s.db).await?;
    Ok(Json(json!({"items":items})))
}
#[derive(Deserialize, Default)]
pub struct RecommendationQuery {
    pub resume_id: Option<String>,
    pub limit: Option<i64>,
}
/// Candidate-side counterpart of the employer search. Each result is explicit
/// about which resume target it matches, so a person with several roles never
/// sends an accidental application from the wrong resume.
pub async fn recommendations(
    State(s): State<AppState>,
    actor: Actor,
    Query(q): Query<RecommendationQuery>,
) -> Result<Json<Value>> {
    actor.require("candidate")?;
    let limit = q.limit.unwrap_or(24).clamp(1, 100);
    let items:Vec<Value>=sqlx::query_scalar("WITH pairs AS (SELECT r.id AS resume_id,r.target_position,r.specialization AS resume_spec,r.declared_grade,r.skills,r.expected_salary,coalesce(t.passed,false) AS test_passed,v.id AS vacancy_id,v.title,v.description,v.specialization,v.grade,v.skills AS vacancy_skills,v.salary_from,v.salary_to,v.work_format,v.status,v.origin,v.synthetic,v.source_ref,c.name AS company_name,(SELECT count(DISTINCT fsp_fold(x)) FROM unnest(r.skills) x WHERE fsp_fold(x)=ANY(ARRAY(SELECT fsp_fold(y) FROM unnest(v.skills) y))) AS common_skills FROM resume_profiles r JOIN candidates ca ON ca.id=r.candidate_id JOIN vacancies v ON v.status='published' JOIN companies c ON c.id=v.company_id LEFT JOIN qualification_tests t ON t.resume_id=r.id WHERE r.candidate_id=$1 AND r.status<>'archived' AND ($2::text IS NULL OR r.id=$2)), scored AS (SELECT *,CASE WHEN resume_spec=specialization AND (grade='' OR declared_grade=grade) AND expected_salary<=salary_to AND (cardinality(vacancy_skills)=0 OR common_skills>=least(4,cardinality(vacancy_skills))) THEN 3 WHEN resume_spec=specialization AND ((grade='' OR declared_grade=grade) OR (expected_salary<=salary_to AND (CASE declared_grade WHEN 'junior' THEN 0 WHEN 'middle' THEN 1 ELSE 2 END)>=(CASE grade WHEN 'junior' THEN 0 WHEN 'middle' THEN 1 ELSE 2 END))) THEN 2 WHEN resume_spec=specialization THEN 1 ELSE 0 END AS relevance FROM pairs) SELECT jsonb_build_object('resume_id',resume_id,'target_position',target_position,'relevance',relevance,'matched_skills',common_skills,'test_passed',test_passed,'vacancy',jsonb_build_object('id',vacancy_id,'title',title,'description',description,'specialization',specialization,'grade',grade,'skills',vacancy_skills,'salary_from',salary_from,'salary_to',salary_to,'work_format',work_format,'status',status,'origin',origin,'synthetic',synthetic,'source_ref',source_ref,'company_name',company_name),'reasons',jsonb_build_array(CASE WHEN relevance=3 THEN CASE WHEN grade='' THEN 'Роль, стек и ожидания совпадают' ELSE 'Роль, уровень, стек и ожидания совпадают' END WHEN relevance=2 THEN 'Роль совпадает, но детали стоит уточнить' WHEN relevance=1 THEN 'Роль совпадает частично' ELSE 'Смежная вакансия: проверьте требования' END,CASE WHEN expected_salary<=salary_to THEN 'Ожидание укладывается в верхнюю границу зарплаты' ELSE 'Ожидание выше указанной верхней границы' END)) FROM scored ORDER BY relevance DESC,test_passed DESC,common_skills DESC,vacancy_id DESC LIMIT $3")
        .bind(&actor.subject_id).bind(q.resume_id).bind(limit).fetch_all(&s.db).await?;
    Ok(Json(
        json!({"items":items,"policy":"Соответствие резюме вакансии → успешно пройденный тест по этому резюме → совпавшие навыки"}),
    ))
}
#[derive(Deserialize)]
pub struct VacancyInput {
    pub title: String,
    pub description: String,
    pub specialization: String,
    pub grade: String,
    pub skills: Vec<String>,
    pub salary_from: i32,
    pub salary_to: i32,
    pub work_format: String,
    pub status: String,
}
pub(crate) fn validate_vacancy(p: &VacancyInput) -> Result<()> {
    salary(p.salary_from, p.salary_to)?;
    if !valid_spec(&p.specialization)
        || !crate::matching::valid_vacancy_grade(&p.specialization, &p.grade)
        || p.title.trim().len() < 3
        || p.title.len() > 250
        || p.description.trim().len() < 10
        || p.description.len() > 20000
        || p.skills.len() > 60
        || p.skills.iter().any(|s| s.len() > 100)
        || p.work_format.len() > 100
        || !["draft", "published", "closed"].contains(&p.status.as_str())
    {
        return Err(AppError::bad(
            "Проверьте название, описание, специализацию, уровень роли и статус вакансии",
        ));
    }
    Ok(())
}
pub async fn vacancy_create(
    State(s): State<AppState>,
    actor: Actor,
    Json(p): Json<VacancyInput>,
) -> Result<Json<Value>> {
    actor.verified_employer(&s).await?;
    validate_vacancy(&p)?;
    let id = new_id("V");
    let mut tx = s.db.begin().await?;
    sqlx::query("SELECT id FROM companies WHERE id=$1 FOR UPDATE")
        .bind(&actor.subject_id)
        .fetch_one(&mut *tx)
        .await?;
    let count: i64 = sqlx::query_scalar(
        "SELECT count(*) FROM vacancies WHERE company_id=$1 AND status<>'closed'",
    )
    .bind(&actor.subject_id)
    .fetch_one(&mut *tx)
    .await?;
    if count >= 50 && p.status != "closed" {
        return Err(AppError::conflict(
            "У компании может быть до 50 активных вакансий",
        ));
    }
    let v:Value=sqlx::query_scalar("INSERT INTO vacancies(id,company_id,title,description,specialization,grade,skills,salary_from,salary_to,work_format,status) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) RETURNING to_jsonb(vacancies)")
        .bind(id).bind(actor.subject_id).bind(p.title).bind(p.description).bind(p.specialization).bind(p.grade).bind(p.skills).bind(p.salary_from).bind(p.salary_to).bind(p.work_format).bind(p.status).fetch_one(&mut *tx).await?;
    tx.commit().await?;
    Ok(Json(json!({"vacancy":v})))
}
pub async fn vacancy_update(
    State(s): State<AppState>,
    actor: Actor,
    Path(id): Path<String>,
    Json(p): Json<VacancyInput>,
) -> Result<Json<Value>> {
    actor.verified_employer(&s).await?;
    validate_vacancy(&p)?;
    let mut tx = s.db.begin().await?;
    sqlx::query("SELECT id FROM companies WHERE id=$1 FOR UPDATE")
        .bind(&actor.subject_id)
        .fetch_one(&mut *tx)
        .await?;
    let old: Option<String> =
        sqlx::query_scalar("SELECT status FROM vacancies WHERE id=$1 AND company_id=$2")
            .bind(&id)
            .bind(&actor.subject_id)
            .fetch_optional(&mut *tx)
            .await?;
    if old.is_none() {
        return Err(AppError::missing());
    }
    if old.as_deref() == Some("closed") && p.status != "closed" {
        let n: i64 = sqlx::query_scalar(
            "SELECT count(*) FROM vacancies WHERE company_id=$1 AND status<>'closed'",
        )
        .bind(&actor.subject_id)
        .fetch_one(&mut *tx)
        .await?;
        if n >= 50 {
            return Err(AppError::conflict(
                "У компании может быть до 50 активных вакансий",
            ));
        }
    }
    let v:Value=sqlx::query_scalar("UPDATE vacancies SET title=$3,description=$4,specialization=$5,grade=$6,skills=$7,salary_from=$8,salary_to=$9,work_format=$10,status=$11,updated_at=now() WHERE id=$1 AND company_id=$2 RETURNING to_jsonb(vacancies)")
        .bind(id).bind(actor.subject_id).bind(p.title).bind(p.description).bind(p.specialization).bind(p.grade).bind(p.skills).bind(p.salary_from).bind(p.salary_to).bind(p.work_format).bind(p.status).fetch_optional(&mut *tx).await?.ok_or_else(AppError::missing)?;
    tx.commit().await?;
    Ok(Json(json!({"vacancy":v})))
}
#[derive(Deserialize)]
pub struct Apply {
    pub message: String,
    pub share_with_ats: Option<bool>,
    pub resume_id: Option<String>,
}
pub async fn apply(
    State(s): State<AppState>,
    actor: Actor,
    Path(id): Path<String>,
    Json(p): Json<Apply>,
) -> Result<Json<Value>> {
    actor.require("candidate")?;
    if p.message.len() > 10000 {
        return Err(AppError::bad("Сообщение слишком длинное"));
    }
    let mut tx = s.db.begin().await?;
    // Every application must carry an immutable target resume. If a client did
    // not select one (older UI), choose the closest active target by role,
    // then by completed role test and recency. This prevents an employer from
    // receiving an application with no readable professional context.
    let resume_id: Option<String> = if let Some(resume_id) = p.resume_id.as_deref() {
        sqlx::query_scalar(
            "SELECT id FROM resume_profiles WHERE id=$1 AND candidate_id=$2 AND status<>'archived'",
        )
        .bind(resume_id)
        .bind(&actor.subject_id)
        .fetch_optional(&mut *tx)
        .await?
    } else {
        sqlx::query_scalar("SELECT r.id FROM resume_profiles r JOIN vacancies v ON v.id=$1 LEFT JOIN qualification_tests q ON q.resume_id=r.id WHERE r.candidate_id=$2 AND r.status<>'archived' ORDER BY (r.specialization=v.specialization) DESC,coalesce(q.passed,false) DESC,r.updated_at DESC LIMIT 1")
            .bind(&id).bind(&actor.subject_id).fetch_optional(&mut *tx).await?
    };
    let resume_id =
        resume_id.ok_or_else(|| AppError::bad("Для отклика добавьте целевое резюме"))?;
    let valid:bool=sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM vacancies WHERE id=$1 AND status='published') AND EXISTS(SELECT 1 FROM candidates WHERE id=$2 AND consent_processing AND NOT employment_blocked)").bind(&id).bind(&actor.subject_id).fetch_one(&mut *tx).await?;
    if !valid {
        return Err(AppError::bad(
            "Вакансия недоступна или отсутствует согласие на обработку профиля",
        ));
    }
    let item:Value=sqlx::query_scalar("INSERT INTO applications(id,vacancy_id,candidate_id,resume_id,message) VALUES($1,$2,$3,$4,$5) ON CONFLICT(vacancy_id,candidate_id) DO UPDATE SET status=CASE WHEN applications.status='withdrawn' THEN 'sent' ELSE applications.status END,resume_id=EXCLUDED.resume_id,message=EXCLUDED.message RETURNING to_jsonb(applications)").bind(new_id("A")).bind(id).bind(&actor.subject_id).bind(&resume_id).bind(p.message).fetch_one(&mut *tx).await?;
    let company_id: String = sqlx::query_scalar("SELECT company_id FROM vacancies WHERE id=$1")
        .bind(item["vacancy_id"].as_str().unwrap_or_default())
        .fetch_one(&mut *tx)
        .await?;
    let conversation_id = crate::conversations::ensure_thread(
        &mut tx,
        &actor.subject_id,
        &company_id,
        item["vacancy_id"].as_str(),
        item["resume_id"].as_str(),
        "application",
    )
    .await?;
    if p.share_with_ats == Some(true) {
        crate::talantix::enqueue(
            &mut tx,
            &company_id,
            &actor.subject_id,
            item["vacancy_id"].as_str().unwrap_or_default(),
            "application.created",
            item["id"].as_str().unwrap_or_default(),
        )
        .await?;
    }
    sqlx::query("INSERT INTO audit_events(actor_id,action,entity_id,details) VALUES($1,'application.contact_consent',$2,$3)")
        .bind(&actor.id).bind(item["id"].as_str().unwrap_or(""))
        .bind(json!({"vacancy_id":item["vacancy_id"],"ats_hand_off":p.share_with_ats==Some(true)}))
        .execute(&mut *tx).await?;
    tx.commit().await?;
    Ok(Json(
        json!({"application":item,"conversation_id":conversation_id}),
    ))
}
fn normalized(value: &str) -> String {
    value.trim().to_lowercase()
}

fn application_match(application: &Value) -> Value {
    let vacancy = &application["vacancy"];
    let resume = &application["resume"];
    let candidate = &application["candidate"];
    let resume_spec = resume["specialization"].as_str().unwrap_or("");
    let vacancy_spec = vacancy["specialization"].as_str().unwrap_or("");
    let role_score = if resume_spec == vacancy_spec { 25 } else { 0 };
    let resume_skills = resume["skills"].as_array().cloned().unwrap_or_default();
    let vacancy_skills = vacancy["skills"].as_array().cloned().unwrap_or_default();
    let matched_skills = vacancy_skills
        .iter()
        .filter_map(Value::as_str)
        .filter(|required| {
            resume_skills
                .iter()
                .filter_map(Value::as_str)
                .any(|actual| normalized(actual) == normalized(required))
        })
        .map(str::to_owned)
        .collect::<Vec<_>>();
    let missing_skills = vacancy_skills
        .iter()
        .filter_map(Value::as_str)
        .filter(|required| {
            !matched_skills
                .iter()
                .any(|actual| normalized(actual) == normalized(required))
        })
        .map(str::to_owned)
        .collect::<Vec<_>>();
    let skill_score = if vacancy_skills.is_empty() {
        30
    } else {
        (matched_skills.len() as i32 * 30 / vacancy_skills.len() as i32).min(30)
    };
    let experience_years = resume["experience_years"].as_f64().unwrap_or(0.0);
    let experience_score = if experience_years >= 1.0 { 10 } else { 4 };
    let salary_ok = candidate["expected_salary"].as_i64().unwrap_or(0)
        <= vacancy["salary_to"].as_i64().unwrap_or(0);
    let salary_score = if vacancy["salary_to"].as_i64().unwrap_or(0) <= 0 || salary_ok {
        5
    } else {
        0
    };
    let dialogue = &application["verification"]["expert_dialogue"];
    let dialogue_score = if dialogue["supported"] == true { 15 } else { 0 };
    let test = &application["verification"]["qualification_test"];
    let test_score = if test["passed"] == true { 10 } else { 0 };
    let employment_score = if application["verification"]["employment_confirmed"] == true {
        5
    } else {
        0
    };
    let score = role_score
        + skill_score
        + experience_score
        + salary_score
        + dialogue_score
        + test_score
        + employment_score;
    let resume_details = vec![
        if role_score > 0 {
            "Целевая роль совпадает с вакансией".into()
        } else {
            "Целевая роль отличается: требуется ручная оценка переносимого опыта".into()
        },
        if vacancy_skills.is_empty() {
            "В вакансии не задан обязательный стек".into()
        } else {
            format!(
                "Совпали {} из {} требований стека",
                matched_skills.len(),
                vacancy_skills.len()
            )
        },
        format!(
            "В резюме указано {:.1} лет релевантного опыта",
            experience_years
        ),
    ];
    json!({
        "score":score,
        "label":if score>=75 {"Сильное соответствие"} else if score>=50 {"Есть основания продолжить"} else {"Нужна ручная оценка"},
        "matched_skills":matched_skills,
        "missing_skills":missing_skills,
        "components":[
            {"key":"resume","label":"Опыт и стек из резюме","score":role_score+skill_score+experience_score+salary_score,"max":70,"available":true,"details":resume_details},
            {"key":"dialogue","label":"Экспертный диалог","score":dialogue_score,"max":15,"available":dialogue["available"],"details":if dialogue["available"]==true {vec![if dialogue["supported"]==true {"Соответствие по ответам кандидата подтверждено"} else {"Диалог не подтвердил соответствие"}]} else {vec!["Нет завершённого диалога по этой роли"]}},
            {"key":"test","label":"Тест по целевому резюме","score":test_score,"max":10,"available":test["available"],"details":if test["available"]==true {vec![format!("Результат: {}%",test["score"].as_i64().unwrap_or(0))]} else {vec!["Тест ещё не пройден".to_owned()]}},
            {"key":"employment","label":"Электронная трудовая","score":employment_score,"max":5,"available":application["verification"]["employment_available"],"details":if application["verification"]["employment_confirmed"]==true {vec!["Должности и периоды сверены с резюме"]} else {vec!["Подтверждение отсутствует или требует уточнения"]}}
        ]
    })
}

pub async fn applications(State(s): State<AppState>, actor: Actor) -> Result<Json<Value>> {
    if actor.role == "candidate" {
        let items: Vec<Value> = sqlx::query_scalar("SELECT to_jsonb(a)||jsonb_build_object('title',v.title,'company_name',c.name) FROM applications a JOIN vacancies v ON v.id=a.vacancy_id JOIN companies c ON c.id=v.company_id WHERE a.candidate_id=$1 ORDER BY a.created_at DESC LIMIT 300")
            .bind(actor.subject_id).fetch_all(&s.db).await?;
        return Ok(Json(json!({"items":items})));
    }
    actor.verified_employer(&s).await?;
    let raw: Vec<Value> = sqlx::query_scalar(r#"
        SELECT jsonb_build_object(
          'id',a.id,'status',a.status,'message',a.message,'created_at',a.created_at,
          'vacancy',jsonb_build_object('id',v.id,'title',v.title,'specialization',v.specialization,'grade',v.grade,'skills',v.skills,'salary_to',v.salary_to),
          'candidate',jsonb_build_object('id',c.id,'display_name',c.display_name,'expected_salary',coalesce(r.expected_salary,c.expected_salary),'work_format',coalesce(r.work_format,c.work_format)),
          'resume',jsonb_build_object('id',r.id,'document_id',r.document_id,'target_position',r.target_position,'specialization',r.specialization,'declared_grade',r.declared_grade,'experience_years',r.experience_years,'skills',r.skills,'about',r.about),
          'verification',jsonb_build_object(
            'employment_available',c.employment_document_id IS NOT NULL,
            'employment_confirmed',coalesce(c.employment_check->>'status','')='aligned',
            'qualification_test',jsonb_build_object('available',qt.id IS NOT NULL AND qt.status IN ('passed','cooldown'),'passed',coalesce(qt.passed,false),'score',qt.score),
            'expert_dialogue',jsonb_build_object('available',EXISTS(SELECT 1 FROM expert_dialogues d WHERE d.candidate_id=c.id AND d.specialization=r.specialization AND d.status='completed'),'supported',EXISTS(SELECT 1 FROM expert_dialogues d WHERE d.candidate_id=c.id AND d.specialization=r.specialization AND d.status='completed' AND (d.result->>'decision'='supported' OR d.project_result->>'decision'='supported'))),
            'fsp_event_verified',EXISTS(SELECT 1 FROM fsp_participations fp WHERE fp.candidate_id=c.id AND fp.status IN ('verified','mock_verified'))
          )
        )
        FROM applications a
        JOIN vacancies v ON v.id=a.vacancy_id
        JOIN candidates c ON c.id=a.candidate_id
        LEFT JOIN resume_profiles r ON r.id=a.resume_id
        LEFT JOIN qualification_tests qt ON qt.resume_id=r.id
        WHERE v.company_id=$1
        ORDER BY a.created_at DESC LIMIT 300
    "#).bind(actor.subject_id).fetch_all(&s.db).await?;
    let items = raw.into_iter().map(|mut item| {
        if item["resume"].is_null() || item["resume"]["id"].is_null() {
            item["resume"] = json!({"id":Value::Null,"target_position":"Резюме не выбрано","specialization":"","declared_grade":"","experience_years":0,"skills":[],"about":""});
        }
        item["match"] = application_match(&item);
        item
    }).collect::<Vec<_>>();
    Ok(Json(
        json!({"items":items,"policy":"Соответствие: резюме 70% → экспертный диалог 15% при наличии → тест по выбранному резюме 10% при наличии → подтверждение трудовой 5% при наличии"}),
    ))
}
pub async fn application_status(
    State(s): State<AppState>,
    actor: Actor,
    Path(id): Path<String>,
    Json(p): Json<Status>,
) -> Result<Json<Value>> {
    let result = if actor.role == "candidate" {
        if p.status != "withdrawn" {
            return Err(AppError::forbidden());
        }
        sqlx::query_scalar::<_,Value>("UPDATE applications SET status='withdrawn' WHERE id=$1 AND candidate_id=$2 RETURNING to_jsonb(applications)").bind(id).bind(actor.subject_id).fetch_optional(&s.db).await?
    } else {
        if !["viewed", "interview", "rejected"].contains(&p.status.as_str()) {
            return Err(AppError::bad("Некорректный статус"));
        }
        sqlx::query_scalar::<_,Value>("UPDATE applications a SET status=$3,first_employer_response_at=CASE WHEN a.status='sent' THEN coalesce(a.first_employer_response_at,clock_timestamp()) ELSE a.first_employer_response_at END FROM vacancies v WHERE a.id=$1 AND a.vacancy_id=v.id AND v.company_id=$2 AND a.status<>'withdrawn' RETURNING to_jsonb(a)").bind(id).bind(actor.subject_id).bind(p.status).fetch_optional(&s.db).await?
    };
    Ok(Json(
        json!({"application":result.ok_or_else(AppError::missing)?}),
    ))
}
#[derive(Deserialize)]
pub struct TaskInput {
    pub candidate_id: String,
    pub title: String,
    pub prompt: String,
}
pub async fn task_create(
    State(s): State<AppState>,
    actor: Actor,
    Json(p): Json<TaskInput>,
) -> Result<Json<Value>> {
    actor.verified_employer(&s).await?;
    if p.title.trim().len() < 3
        || p.title.len() > 250
        || p.prompt.trim().len() < 10
        || p.prompt.len() > 10000
    {
        return Err(AppError::bad("Добавьте название и условие задания"));
    }
    let mut tx = s.db.begin().await?;
    // Serialize this company's task creation across all API replicas.
    sqlx::query("SELECT id FROM companies WHERE id=$1 FOR UPDATE")
        .bind(&actor.subject_id)
        .fetch_one(&mut *tx)
        .await?;
    let valid:bool=sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM intelligence.resume_category_evidence WHERE candidate_id=$1 AND employer_eligible)").bind(&p.candidate_id).fetch_one(&mut *tx).await?;
    if !valid {
        return Err(AppError::missing());
    }
    let recent:bool=sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM micro_tasks WHERE company_id=$1 AND candidate_id=$2 AND created_at>now()-interval '7 days')").bind(&actor.subject_id).bind(&p.candidate_id).fetch_one(&mut *tx).await?;
    if recent {
        return Err(AppError::conflict(
            "Одно короткое задание в неделю для кандидата от вашей компании",
        ));
    }
    let item:Value=sqlx::query_scalar("INSERT INTO micro_tasks(id,company_id,candidate_id,title,prompt) VALUES($1,$2,$3,$4,$5) RETURNING to_jsonb(micro_tasks)").bind(new_id("T")).bind(actor.subject_id).bind(p.candidate_id).bind(p.title).bind(p.prompt).fetch_one(&mut *tx).await?;
    tx.commit().await?;
    Ok(Json(json!({"task":item})))
}
#[derive(Deserialize)]
pub struct TaskResponse {
    pub response: Option<String>,
    pub score: Option<i32>,
    pub feedback: Option<String>,
}
pub async fn task_respond(
    State(s): State<AppState>,
    actor: Actor,
    Path(id): Path<String>,
    Json(p): Json<TaskResponse>,
) -> Result<Json<Value>> {
    let mut tx = s.db.begin().await?;
    let item=if actor.role=="candidate"{
        let answer=p.response.ok_or_else(||AppError::bad("Добавьте решение или подход"))?;
        if answer.trim().len()<10||answer.len()>20000{return Err(AppError::bad("Ответ должен содержать от 10 до 20 000 символов"));}
        sqlx::query_scalar::<_,Value>("UPDATE micro_tasks SET response=$3,status='submitted',submitted_at=now() WHERE id=$1 AND candidate_id=$2 AND status='pending' AND contract IS NULL RETURNING to_jsonb(micro_tasks)").bind(&id).bind(&actor.subject_id).bind(answer).fetch_optional(&mut *tx).await?
    }else{
        let score=p.score.ok_or_else(||AppError::bad("Укажите оценку"))?;let feedback=p.feedback.unwrap_or_default();
        if !(0..=100).contains(&score)||feedback.trim().len()<5||feedback.len()>10000{return Err(AppError::bad("Укажите оценку 0–100 и обратную связь"));}
        sqlx::query_scalar::<_,Value>("UPDATE micro_tasks SET score=$3,feedback=$4,status='reviewed',reviewed_at=now() WHERE id=$1 AND company_id=$2 AND status='submitted' AND contract IS NULL RETURNING to_jsonb(micro_tasks)").bind(&id).bind(&actor.subject_id).bind(score).bind(feedback).fetch_optional(&mut *tx).await?
    }.ok_or_else(AppError::missing)?;
    if actor.role == "employer" {
        sqlx::query("UPDATE candidates SET profile_updated_at=now() WHERE id=$1")
            .bind(item["candidate_id"].as_str().unwrap_or(""))
            .execute(&mut *tx)
            .await?;
    }
    tx.commit().await?;
    Ok(Json(json!({"task":item})))
}
