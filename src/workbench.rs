//! Ownership-gated career advice, vacancy intelligence and executable assessments.
use crate::{
    AppState,
    auth::{Actor, new_id},
    error::{AppError, Result},
};
use axum::{
    Json,
    extract::{Path, State},
};
use serde::Deserialize;
use serde_json::{Value, json};
use std::time::Duration;

static EXECUTOR_SLOTS: tokio::sync::Semaphore = tokio::sync::Semaphore::const_new(2);

pub(crate) async fn ai(s: &AppState, payload: Value) -> Result<Value> {
    let slots = if payload["operation"] == "run" {
        &EXECUTOR_SLOTS
    } else {
        &s.interview_slots
    };
    let _slot = slots.try_acquire().map_err(|_| {
        AppError::unavailable("Ассистент занят. Повторите запрос через несколько секунд.")
    })?;
    let token = crate::config::secret("WORKBENCH_TOKEN")
        .or_else(|_| {
            std::fs::read_to_string("runtime/workbench.secret").map_err(anyhow::Error::from)
        })
        .map_err(|_| AppError::unavailable("Ассистент временно недоступен"))?;
    let url = std::env::var("WORKBENCH_URL").unwrap_or("http://127.0.0.1:8091".into());
    let res = reqwest::Client::builder()
        .no_proxy()
        .timeout(Duration::from_secs(280))
        .build()
        .map_err(|_| AppError::unavailable("Ассистент временно недоступен"))?
        .post(format!("{url}/operation"))
        .bearer_auth(token.trim())
        .json(&payload)
        .send()
        .await
        .map_err(|_| {
            AppError::unavailable("Не удалось завершить расчёт. Можно повторить запрос.")
        })?;
    if !res.status().is_success() {
        return Err(AppError::unavailable(
            "Не удалось завершить проверку. Данные сохранены; повторите запрос.",
        ));
    }
    res.json()
        .await
        .map_err(|_| AppError::unavailable("Некорректный ответ сервиса"))
}
async fn owned(s: &AppState, a: &Actor, id: &str) -> Result<Value> {
    a.verified_employer(s).await?;
    sqlx::query_scalar("SELECT to_jsonb(v) FROM vacancies v WHERE id=$1 AND company_id=$2")
        .bind(id)
        .bind(&a.subject_id)
        .fetch_optional(&s.db)
        .await?
        .ok_or_else(AppError::missing)
}
async fn notice(
    tx: &mut sqlx::Transaction<'_, sqlx::Postgres>,
    subject: &str,
    kind: &str,
    title: &str,
    entity: &str,
    vacancy: Option<&str>,
) -> Result<()> {
    sqlx::query("INSERT INTO notifications(id,user_id,kind,title,entity_id,vacancy_id) SELECT $1,id,$3,$4,$5,$6 FROM users WHERE subject_id=$2").bind(new_id("N")).bind(subject).bind(kind).bind(title).bind(entity).bind(vacancy).execute(&mut **tx).await?;
    Ok(())
}
pub(crate) fn redact(text: &str) -> String {
    static PATTERNS: std::sync::OnceLock<Vec<regex::Regex>> = std::sync::OnceLock::new();
    PATTERNS
        .get_or_init(|| {
            [
                r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
                r"(?:\+7|8)[ ()-]*\d{3}[ ()-]*\d{3}[ -]*\d{2}[ -]*\d{2}",
                r"https?://\S+",
                r"\b[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?\b",
            ]
            .iter()
            .map(|p| regex::Regex::new(p).unwrap())
            .collect()
        })
        .iter()
        .fold(text.to_owned(), |v, p| {
            p.replace_all(&v, "[скрыто]").into_owned()
        })
}
pub async fn notifications(State(s): State<AppState>, a: Actor) -> Result<Json<Value>> {
    let items:Vec<Value>=sqlx::query_scalar("SELECT to_jsonb(n) FROM notifications n WHERE user_id=$1 ORDER BY created_at DESC LIMIT 50").bind(&a.id).fetch_all(&s.db).await?;
    Ok(Json(
        json!({"unread":items.iter().filter(|n|n["read_at"].is_null()).count(),"items":items}),
    ))
}
pub async fn read_notice(
    State(s): State<AppState>,
    a: Actor,
    Path(id): Path<String>,
) -> Result<Json<Value>> {
    let n = sqlx::query(
        "UPDATE notifications SET read_at=coalesce(read_at,now()) WHERE id=$1 AND user_id=$2",
    )
    .bind(id)
    .bind(a.id)
    .execute(&s.db)
    .await?;
    if n.rows_affected() == 0 {
        return Err(AppError::missing());
    }
    Ok(Json(json!({"read":true})))
}
pub async fn career_history(State(s): State<AppState>, a: Actor) -> Result<Json<Value>> {
    a.require("candidate")?;
    let items:Vec<Value>=sqlx::query_scalar("SELECT jsonb_build_object('role',role,'content',content) FROM (SELECT * FROM career_messages WHERE candidate_id=$1 ORDER BY id DESC LIMIT 20) q ORDER BY id").bind(a.subject_id).fetch_all(&s.db).await?;
    Ok(Json(json!({"items":items})))
}
#[derive(Deserialize)]
pub struct Text {
    pub text: String,
}
pub async fn career(
    State(s): State<AppState>,
    a: Actor,
    Json(p): Json<Text>,
) -> Result<Json<Value>> {
    a.require("candidate")?;
    if !(3..=2000).contains(&p.text.chars().count()) {
        return Err(AppError::bad("Сообщение: от 3 до 2000 символов"));
    }
    let profiles:Vec<Value>=sqlx::query_scalar("SELECT jsonb_build_object('target_position',target_position,'skills',skills,'experience_years',experience_years,'about',about) FROM resume_profiles WHERE candidate_id=$1 AND status<>'archived' LIMIT 3").bind(&a.subject_id).fetch_all(&s.db).await?;
    let history = career_history(State(s.clone()), a.clone()).await?.0["items"].clone();
    let clean = redact(&p.text);
    let result = ai(
        &s,
        json!({"operation":"career","text":clean,"profiles":profiles,"history":history}),
    )
    .await?;
    let reply = result["reply"]
        .as_str()
        .filter(|v| !v.trim().is_empty())
        .ok_or_else(|| AppError::unavailable("Не удалось получить консультацию"))?;
    let mut tx = s.db.begin().await?;
    sqlx::query("INSERT INTO career_messages(candidate_id,role,content) VALUES($1,'user',$2),($1,'assistant',$3)").bind(&a.subject_id).bind(clean).bind(reply).execute(&mut *tx).await?;
    tx.commit().await?;
    Ok(Json(json!({"reply":reply})))
}
pub async fn vacancy_draft(
    State(s): State<AppState>,
    a: Actor,
    Json(p): Json<Text>,
) -> Result<Json<Value>> {
    a.verified_employer(&s).await?;
    if !(10..=2000).contains(&p.text.chars().count()) {
        return Err(AppError::bad("Опишите потребность в 10–2000 символах"));
    }
    let market_salary: Option<f64> = sqlx::query_scalar("SELECT percentile_cont(0.5) WITHIN GROUP(ORDER BY (salary_from+salary_to)/2.0)::float8 FROM vacancies WHERE status='published' AND salary_to>0").fetch_one(&s.db).await?;
    let mut draft=ai(&s,json!({"operation":"vacancy","request":redact(&p.text),"taxonomy":crate::matching::taxonomy().iter().map(|x|json!({"id":x.id,"label":x.label})).collect::<Vec<_>>(),"market_salary":market_salary.map(|v|v.round() as i64).unwrap_or(0)})).await?;
    draft["status"] = json!("draft");
    let spec = draft["specialization"].as_str().unwrap_or("");
    if !crate::matching::valid_spec(spec) {
        return Err(AppError::unavailable(
            "Уточните направление роли и повторите запрос",
        ));
    }
    if crate::matching::taxonomy()
        .iter()
        .any(|x| x.id == spec && x.leadership_level.is_some())
    {
        draft["grade"] = json!("");
    }
    let parsed: crate::interactions::VacancyInput = serde_json::from_value(draft.clone())
        .map_err(|_| AppError::unavailable("Уточните запрос для черновика"))?;
    crate::interactions::validate_vacancy(&parsed)?;
    Ok(Json(json!({"draft":draft})))
}
#[derive(Deserialize)]
pub struct Bulk {
    pub items: Vec<crate::interactions::VacancyInput>,
}
pub async fn bulk_vacancies(
    State(s): State<AppState>,
    a: Actor,
    Json(p): Json<Bulk>,
) -> Result<Json<Value>> {
    a.verified_employer(&s).await?;
    if p.items.is_empty() || p.items.len() > 50 {
        return Err(AppError::bad("Загрузите от 1 до 50 вакансий"));
    }
    for row in &p.items {
        crate::interactions::validate_vacancy(row)?;
    }
    let mut tx = s.db.begin().await?;
    sqlx::query("SELECT id FROM companies WHERE id=$1 FOR UPDATE")
        .bind(&a.subject_id)
        .fetch_one(&mut *tx)
        .await?;
    let active: i64 = sqlx::query_scalar(
        "SELECT count(*) FROM vacancies WHERE company_id=$1 AND status<>'closed'",
    )
    .bind(&a.subject_id)
    .fetch_one(&mut *tx)
    .await?;
    if active + p.items.iter().filter(|v| v.status != "closed").count() as i64 > 50 {
        return Err(AppError::conflict(
            "У компании может быть до 50 активных вакансий. Закройте завершённые.",
        ));
    }
    let mut items = Vec::<Value>::new();
    for v in p.items {
        items.push(sqlx::query_scalar("INSERT INTO vacancies(id,company_id,title,description,specialization,grade,skills,salary_from,salary_to,work_format,status) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) RETURNING to_jsonb(vacancies)").bind(new_id("V")).bind(&a.subject_id).bind(v.title).bind(v.description).bind(v.specialization).bind(v.grade).bind(v.skills).bind(v.salary_from).bind(v.salary_to).bind(v.work_format).bind(v.status).fetch_one(&mut *tx).await?);
    }
    tx.commit().await?;
    Ok(Json(
        json!({"imported":items.len(),"items":items,"max_active":50}),
    ))
}
fn percentile(v: &[f64], q: f64) -> f64 {
    if v.is_empty() {
        return 0.0;
    }
    let i = q * (v.len() - 1) as f64;
    v[i.floor() as usize] + (v[i.ceil() as usize] - v[i.floor() as usize]) * i.fract()
}
pub async fn vacancy_market(
    State(s): State<AppState>,
    a: Actor,
    Path(id): Path<String>,
) -> Result<Json<Value>> {
    let v = owned(&s, &a, &id).await?;
    let spec = v["specialization"].as_str().unwrap_or("");
    let grade = v["grade"].as_str().unwrap_or("");
    let rows:Vec<(String,String,i32,Vec<String>,bool)>=sqlx::query_as("SELECT DISTINCT ON(c.id) c.id,r.declared_grade,coalesce(nullif(r.expected_salary,0),c.expected_salary),r.skills,coalesce(q.passed,false) FROM resume_profiles r JOIN candidates c ON c.id=r.candidate_id LEFT JOIN qualification_tests q ON q.resume_id=r.id WHERE r.specialization=$1 AND r.status='published' AND r.visibility='employer_searchable' AND c.consent_processing AND c.consent_publication AND NOT c.employment_blocked AND (CASE r.declared_grade WHEN 'junior' THEN 0 WHEN 'middle' THEN 1 ELSE 2 END)>=(CASE $2 WHEN 'junior' THEN 0 WHEN 'middle' THEN 1 ELSE 2 END) ORDER BY c.id,coalesce(q.passed,false) DESC,r.updated_at DESC").bind(spec).bind(if grade.is_empty(){"junior"}else{grade}).fetch_all(&s.db).await?;
    let required: Vec<String> = v["skills"]
        .as_array()
        .map(|v| {
            v.iter()
                .filter_map(Value::as_str)
                .map(|x| x.to_lowercase())
                .collect()
        })
        .unwrap_or_default();
    let relevant: Vec<_> = rows
        .iter()
        .filter(|r| {
            required.is_empty()
                || required
                    .iter()
                    .filter(|s| r.3.iter().any(|x| x.to_lowercase() == **s))
                    .count()
                    * 2
                    >= required.len()
        })
        .collect();
    let mut salary: Vec<f64> = relevant
        .iter()
        .filter(|r| r.2 > 0)
        .map(|r| r.2 as f64)
        .collect();
    salary.sort_by(f64::total_cmp);
    let market:Option<f64>=sqlx::query_scalar("SELECT percentile_cont(0.5) WITHIN GROUP(ORDER BY (salary_from+salary_to)/2.0)::float8 FROM vacancies WHERE specialization=$1 AND ($2='' OR grade=$2) AND status='published' AND id<>$3").bind(spec).bind(grade).bind(&id).fetch_one(&s.db).await?;
    let median = percentile(&salary, 0.5);
    let enough = salary.len() >= 5;
    let employers = market.unwrap_or(median);
    let benchmark = if enough && employers > 0.0 {
        0.65 * median + 0.35 * employers
    } else {
        market.unwrap_or(0.0)
    };
    let mid =
        (v["salary_from"].as_f64().unwrap_or(0.0) + v["salary_to"].as_f64().unwrap_or(0.0)) / 2.0;
    let status = if benchmark == 0.0 {
        "insufficient"
    } else if mid > benchmark * 1.1 {
        "above"
    } else if mid >= benchmark * 0.9 {
        "market"
    } else {
        "raise"
    };
    let label = match status {
        "above" => "Зарплата выше рынка",
        "market" => "Зарплата в рынке",
        "raise" => "Рекомендуем повысить",
        _ => "Недостаточно данных",
    };
    let distribution = if enough {
        (0..5).map(|i|{let lo=percentile(&salary,i as f64/5.0);let hi=percentile(&salary,(i+1)as f64/5.0);json!({"from":lo.round(),"to":hi.round(),"count":salary.iter().filter(|&&s|s>=lo&&(s<hi||(i==4&&s<=hi))).count()})}).collect::<Vec<_>>()
    } else {
        vec![]
    };
    let skills=required.iter().map(|skill|json!({"skill":skill,"count":relevant.iter().filter(|r|r.3.iter().any(|s|s.to_lowercase()==*skill)).count()})).collect::<Vec<_>>();
    Ok(Json(
        json!({"vacancy_id":id,"relevant_candidates":relevant.len(),"verified_candidates":relevant.iter().filter(|r|r.4).count(),"salary_label":label,"salary_status":status,"market_salary":benchmark.round(),"recommended_salary":if status=="raise"{Some((benchmark/1000.0).ceil()*1000.0)}else{None},"candidate_salary":{"sample":salary.len(),"median":if enough{Some(median.round())}else{None},"p25":if enough{Some(percentile(&salary,0.25).round())}else{None},"p75":if enough{Some(percentile(&salary,0.75).round())}else{None}},"salary_distribution":distribution,"skill_coverage":skills,"weights":{"candidate_expectations":0.65,"vacancy_offers":0.35},"small_sample":!enough}),
    ))
}
pub async fn task_recipients(
    State(s): State<AppState>,
    a: Actor,
    Path(id): Path<String>,
) -> Result<Json<Value>> {
    owned(&s, &a, &id).await?;
    let items:Vec<Value>=sqlx::query_scalar("SELECT jsonb_build_object('candidate_id',c.id,'label',c.display_name) FROM candidates c WHERE c.consent_processing AND NOT c.employment_blocked AND (EXISTS(SELECT 1 FROM applications ap WHERE ap.candidate_id=c.id AND ap.vacancy_id=$1 AND ap.status IN('sent','viewed','interview')) OR EXISTS(SELECT 1 FROM invitations i WHERE i.candidate_id=c.id AND i.vacancy_id=$1 AND i.company_id=$2 AND i.status='accepted')) ORDER BY c.id LIMIT 50").bind(id).bind(a.subject_id).fetch_all(&s.db).await?;
    Ok(Json(json!({"items":items})))
}
#[derive(Deserialize)]
pub struct Generate {
    pub vacancy_id: String,
    pub instruction: Option<String>,
}
fn public_contract(v: &Value) -> Value {
    json!({"title":v["title"],"prompt":v["prompt"],"starter_code":v["starter_code"],"public_tests":v["public_tests"],"validation":v["validation"]})
}
pub async fn generate_task(
    State(s): State<AppState>,
    a: Actor,
    Json(p): Json<Generate>,
) -> Result<Json<Value>> {
    let v = owned(&s, &a, &p.vacancy_id).await?;
    if p.instruction.as_ref().is_some_and(|x| x.len() > 1500) {
        return Err(AppError::bad("Уточнение слишком длинное"));
    }
    let result=ai(&s,json!({"operation":"task","vacancy":{"title":v["title"],"description":v["description"],"specialization":v["specialization"],"grade":v["grade"],"skills":v["skills"]},"instruction":p.instruction})).await?;
    let id = new_id("D");
    sqlx::query("INSERT INTO task_drafts(id,company_id,vacancy_id,contract) VALUES($1,$2,$3,$4)")
        .bind(&id)
        .bind(&a.subject_id)
        .bind(&p.vacancy_id)
        .bind(&result)
        .execute(&s.db)
        .await?;
    Ok(Json(json!({"draft_id":id,"task":public_contract(&result)})))
}
#[derive(Deserialize)]
pub struct Dispatch {
    pub draft_id: String,
    pub candidate_ids: Vec<String>,
}
pub async fn dispatch_task(
    State(s): State<AppState>,
    a: Actor,
    Json(p): Json<Dispatch>,
) -> Result<Json<Value>> {
    a.verified_employer(&s).await?;
    let row:Option<(String,Value)>=sqlx::query_as("SELECT vacancy_id,contract FROM task_drafts WHERE id=$1 AND company_id=$2 AND created_at>now()-interval '1 day'").bind(p.draft_id).bind(&a.subject_id).fetch_optional(&s.db).await?;
    let (vacancy, contract) = row.ok_or_else(AppError::missing)?;
    let ids: std::collections::HashSet<_> = p.candidate_ids.iter().collect();
    if ids.is_empty() || ids.len() != p.candidate_ids.len() || ids.len() > 50 {
        return Err(AppError::bad(
            "Выберите от 1 до 50 разных заинтересованных кандидатов",
        ));
    }
    let mut tx = s.db.begin().await?;
    sqlx::query("SELECT id FROM companies WHERE id=$1 FOR UPDATE")
        .bind(&a.subject_id)
        .fetch_one(&mut *tx)
        .await?;
    let mut sent = Vec::new();
    for candidate in p.candidate_ids {
        let interested:bool=sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM candidates c WHERE c.id=$1 AND c.consent_processing AND NOT c.employment_blocked AND (EXISTS(SELECT 1 FROM applications ap WHERE ap.candidate_id=c.id AND ap.vacancy_id=$2 AND ap.status IN('sent','viewed','interview')) OR EXISTS(SELECT 1 FROM invitations i WHERE i.candidate_id=c.id AND i.vacancy_id=$2 AND i.company_id=$3 AND i.status='accepted')))").bind(&candidate).bind(&vacancy).bind(&a.subject_id).fetch_one(&mut *tx).await?;
        if !interested {
            return Err(AppError::forbidden());
        }
        let recent:bool=sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM micro_tasks WHERE company_id=$1 AND candidate_id=$2 AND created_at>now()-interval '7 days')").bind(&a.subject_id).bind(&candidate).fetch_one(&mut *tx).await?;
        if recent {
            return Err(AppError::conflict(
                "Для одного из кандидатов уже есть задание от компании за последние 7 дней",
            ));
        }
        let id = new_id("T");
        sqlx::query("INSERT INTO micro_tasks(id,company_id,candidate_id,vacancy_id,title,prompt,contract) VALUES($1,$2,$3,$4,$5,$6,$7)").bind(&id).bind(&a.subject_id).bind(&candidate).bind(&vacancy).bind(contract["title"].as_str().unwrap_or("Практическое задание")).bind(contract["prompt"].as_str().unwrap_or("")).bind(&contract).execute(&mut *tx).await?;
        notice(
            &mut tx,
            &candidate,
            "task.offered",
            "Новое тестовое задание",
            &id,
            Some(&vacancy),
        )
        .await?;
        sent.push(id);
    }
    tx.commit().await?;
    Ok(Json(json!({"sent":sent.len(),"task_ids":sent})))
}
pub async fn task_list(State(s): State<AppState>, a: Actor) -> Result<Json<Value>> {
    let items:Vec<Value>=sqlx::query_scalar("SELECT (to_jsonb(t)-'contract')||jsonb_build_object('contract',CASE WHEN t.contract IS NULL THEN NULL ELSE jsonb_build_object('title',t.contract->'title','prompt',t.contract->'prompt','starter_code',t.contract->'starter_code','public_tests',t.contract->'public_tests') END,'vacancy_title',v.title,'company_name',co.name,'candidate_name',c.display_name,'participant',CASE WHEN $2='candidate' THEN co.name ELSE c.display_name END) FROM micro_tasks t JOIN candidates c ON c.id=t.candidate_id JOIN companies co ON co.id=t.company_id LEFT JOIN vacancies v ON v.id=t.vacancy_id WHERE CASE WHEN $2='candidate' THEN t.candidate_id=$1 ELSE t.company_id=$1 END ORDER BY t.created_at DESC LIMIT 100").bind(a.subject_id).bind(a.role).fetch_all(&s.db).await?;
    Ok(Json(json!({"items":items})))
}
#[derive(Deserialize)]
pub struct Decision {
    pub status: String,
}
pub async fn task_decide(
    State(s): State<AppState>,
    a: Actor,
    Path(id): Path<String>,
    Json(p): Json<Decision>,
) -> Result<Json<Value>> {
    a.require("candidate")?;
    if !["accepted", "declined"].contains(&p.status.as_str()) {
        return Err(AppError::bad("Выберите принять или отказаться"));
    }
    let mut tx = s.db.begin().await?;
    let row:Option<(String,Option<String>)>=sqlx::query_as("UPDATE micro_tasks SET status=$3,accepted_at=CASE WHEN $3='accepted' THEN now() ELSE NULL END WHERE id=$1 AND candidate_id=$2 AND status='pending' RETURNING company_id,vacancy_id").bind(&id).bind(&a.subject_id).bind(&p.status).fetch_optional(&mut *tx).await?;
    let (company, vacancy) = row.ok_or_else(|| AppError::conflict("На задание уже дан ответ"))?;
    notice(
        &mut tx,
        &company,
        "task.decision",
        if p.status == "accepted" {
            "Кандидат принял тестовое задание"
        } else {
            "Кандидат отказался от тестового задания"
        },
        &id,
        vacancy.as_deref(),
    )
    .await?;
    tx.commit().await?;
    Ok(Json(json!({"status":p.status})))
}
#[derive(Deserialize)]
pub struct Code {
    pub code: String,
}
async fn task_contract(s: &AppState, a: &Actor, id: &str) -> Result<Value> {
    a.require("candidate")?;
    sqlx::query_scalar("SELECT contract FROM micro_tasks WHERE id=$1 AND candidate_id=$2 AND status='accepted' AND contract IS NOT NULL").bind(id).bind(&a.subject_id).fetch_optional(&s.db).await?.ok_or_else(AppError::missing)
}
pub async fn task_run(
    State(s): State<AppState>,
    a: Actor,
    Path(id): Path<String>,
    Json(p): Json<Code>,
) -> Result<Json<Value>> {
    let contract = task_contract(&s, &a, &id).await?;
    if p.code.is_empty() || p.code.len() > 20000 {
        return Err(AppError::bad("Код: от 1 до 20 000 символов"));
    }
    Ok(Json(
        ai(
            &s,
            json!({"operation":"run","code":p.code,"contract":contract}),
        )
        .await?,
    ))
}
pub async fn task_submit(
    State(s): State<AppState>,
    a: Actor,
    Path(id): Path<String>,
    Json(p): Json<Code>,
) -> Result<Json<Value>> {
    let contract = task_contract(&s, &a, &id).await?;
    if p.code.is_empty() || p.code.len() > 20000 {
        return Err(AppError::bad("Код: от 1 до 20 000 символов"));
    }
    let claimed=sqlx::query("UPDATE micro_tasks SET status='reviewing',submitted_at=now() WHERE id=$1 AND candidate_id=$2 AND status='accepted'").bind(&id).bind(&a.subject_id).execute(&s.db).await?;
    if claimed.rows_affected() != 1 {
        return Err(AppError::conflict("Задание уже отправлено на проверку"));
    }
    let mut result = match ai(
        &s,
        json!({"operation":"submit","code":p.code,"contract":contract}),
    )
    .await
    {
        Ok(v) => v,
        Err(e) => {
            sqlx::query(
                "UPDATE micro_tasks SET status='accepted' WHERE id=$1 AND status='reviewing'",
            )
            .bind(&id)
            .execute(&s.db)
            .await?;
            return Err(e);
        }
    };
    if let Ok(indicator) =
        crate::professional::register_code_proof(&s, &a.id, &id, &p.code, "python").await
    {
        result["integrity"] = indicator;
    }
    let mut tx = s.db.begin().await?;
    let row:(String,Option<String>)=sqlx::query_as("UPDATE micro_tasks SET status='reviewed',response=$2,score=$3,feedback=$4,review=$5,reviewed_at=now() WHERE id=$1 AND status='reviewing' RETURNING company_id,vacancy_id").bind(&id).bind(redact(&p.code)).bind(result["score"].as_i64().unwrap_or(0)as i32).bind(result["review"]["feedback"].as_str().unwrap_or("")).bind(&result).fetch_one(&mut *tx).await?;
    notice(
        &mut tx,
        &row.0,
        "task.reviewed",
        &format!(
            "Готово тестовое кандидата {} по вакансии {}",
            a.subject_id,
            row.1.as_deref().unwrap_or("—")
        ),
        &id,
        row.1.as_deref(),
    )
    .await?;
    sqlx::query("INSERT INTO audit_events(actor_id,action,entity_id,details) VALUES($1,'task.auto_reviewed',$2,$3)").bind(&a.id).bind(&id).bind(json!({"passed":result["passed"],"total":result["total"],"score":result["score"]})).execute(&mut *tx).await?;
    tx.commit().await?;
    Ok(Json(result))
}
