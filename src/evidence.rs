//! Ownership-enforced decision tools. All features derive from persisted evidence.
use crate::{
    AppState,
    auth::{Actor, hash_token, new_id},
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

pub async fn weekly_dispatch(s: AppState) {
    loop {
        if let Err(e) = weekly_one(&s).await {
            tracing::warn!(status=%e.0,"weekly campaign unavailable");
        }
        tokio::time::sleep(std::time::Duration::from_secs(30)).await;
    }
}
async fn weekly_one(s: &AppState) -> Result<()> {
    let mut tx = s.db.begin().await?;
    let campaign:Option<(String,String,String)>=sqlx::query_as("SELECT wc.id,wc.company_id,wc.vacancy_id FROM intelligence.weekly_campaigns wc JOIN vacancies v ON v.id=wc.vacancy_id WHERE wc.enabled AND wc.next_run_at<=now() AND v.status='published' ORDER BY wc.next_run_at FOR UPDATE OF wc SKIP LOCKED LIMIT 1").fetch_optional(&mut *tx).await?;
    let Some((id, company, vacancy)) = campaign else {
        return Ok(());
    };
    sqlx::query("SELECT id FROM companies WHERE id=$1 FOR UPDATE")
        .bind(&company)
        .execute(&mut *tx)
        .await?;
    let rows:Vec<(String,Vec<String>)>=sqlx::query_as("SELECT c.id,ARRAY(SELECT lower(req.skill) FROM unnest(v.skills) AS req(skill) WHERE NOT EXISTS(SELECT 1 FROM intelligence.skill_support ss WHERE ss.candidate_id=c.id AND ss.skill=lower(req.skill) AND ss.strength>=0.5)) FROM candidates c JOIN vacancies v ON v.id=$1 WHERE c.consent_processing AND NOT c.employment_blocked AND (EXISTS(SELECT 1 FROM applications ap WHERE ap.candidate_id=c.id AND ap.vacancy_id=v.id AND ap.status IN('sent','viewed','interview')) OR EXISTS(SELECT 1 FROM invitations i WHERE i.candidate_id=c.id AND i.company_id=$2 AND i.vacancy_id=v.id AND i.status='accepted')) AND NOT EXISTS(SELECT 1 FROM micro_tasks t WHERE t.company_id=$2 AND t.candidate_id=c.id AND t.created_at>now()-interval '7 days') ORDER BY c.id LIMIT 20").bind(&vacancy).bind(&company).fetch_all(&mut *tx).await?;
    for (candidate, gaps) in rows {
        let kind = if gaps.contains(&"python".to_owned()) {
            "python"
        } else if gaps.contains(&"sql".to_owned()) {
            "sql"
        } else if gaps.contains(&"typescript".to_owned()) {
            "typescript"
        } else {
            continue;
        };
        let seed = u32::from_le_bytes(uuid::Uuid::new_v4().as_bytes()[..4].try_into().unwrap());
        let contract =
            compute(&json!({"operation":"arena_create","kind":kind,"seed":seed})).await?;
        let task = new_id("T");
        sqlx::query("INSERT INTO micro_tasks(id,company_id,candidate_id,vacancy_id,title,prompt,contract) VALUES($1,$2,$3,$4,$5,$6,$7)").bind(&task).bind(&company).bind(&candidate).bind(&vacancy).bind(contract["title"].as_str()).bind(contract["prompt"].as_str()).bind(&contract).execute(&mut *tx).await?;
        sqlx::query("INSERT INTO notifications(id,user_id,kind,title,entity_id,vacancy_id) SELECT $1,u.id,'task.offered','Адресная проверка навыка',$3,$4 FROM users u WHERE u.subject_id=$2 AND u.role='candidate'").bind(new_id("N")).bind(candidate).bind(task).bind(&vacancy).execute(&mut *tx).await?;
    }
    sqlx::query("UPDATE intelligence.weekly_campaigns SET last_run_at=now(),next_run_at=now()+interval '7 days' WHERE id=$1").bind(id).execute(&mut *tx).await?;
    tx.commit().await?;
    Ok(())
}

pub fn routes() -> Router<AppState> {
    Router::new()
        .route("/workspace", get(workspace))
        .route("/company-twin", get(company_twin).put(save_twin))
        .route("/allocation", post(allocation))
        .route("/diagnosis/{id}", post(diagnosis))
        .route("/compatibility/{resume}/{vacancy}", get(compatibility))
        .route("/passport", post(issue_passport).get(passports))
        .route("/passport/public-key", get(public_key))
        .route("/passport/verify", post(verify_passport))
        .route("/passport/{id}/revoke", post(revoke_passport))
        .route("/authorship/{id}", post(defense))
        .route("/reviews", get(reviews))
        .route("/reviews/{id}/challenge", post(challenge))
        .route("/reviews/{id}/resolve", post(resolve))
        .route("/followups", get(followups).post(schedule_followups))
        .route("/followups/{id}", axum::routing::put(update_followup))
        .route("/weekly-campaigns", get(campaigns).post(save_campaign))
}

const CANDIDATE_SQL: &str = r#"SELECT jsonb_build_object(
 'id',r.id,'candidate_id',c.id,'specialization',r.specialization,'salary',r.expected_salary,
 'grade',coalesce(q.grade,r.declared_grade),'grade_verified',q.id IS NOT NULL,
 'category_grade',rg.confirmed_grade,'category_scope',rg.category_scope,
 'category_proof_id',rg.category_proof_id,
 'support',coalesce((SELECT jsonb_object_agg(ss.skill,ss.strength) FROM intelligence.skill_support ss WHERE ss.candidate_id=c.id),'{}'),
 'preferences',CASE WHEN $1::text IS NOT NULL THEN coalesce(p.value,'{}') ELSE '{}'::jsonb END)
 FROM resume_profiles r JOIN candidates c ON c.id=r.candidate_id
 JOIN intelligence.resume_category_evidence rg ON rg.id=r.id
 LEFT JOIN LATERAL(SELECT qc.id,qc.grade FROM qualification_certificates qc
   WHERE qc.resume_id=r.id AND qc.candidate_id=c.id AND qc.specialization=r.specialization
     AND qc.scope='role-reviewed' AND qc.issued_at<=now() AND qc.valid_until>now() AND qc.revoked_at IS NULL
     AND NOT EXISTS(SELECT 1 FROM intelligence.evidence_controls ec JOIN users eu ON eu.id=ec.user_id
       WHERE eu.subject_id=c.id AND ec.evidence_id='cert:'||qc.id AND (ec.hidden OR ec.disputed))
     AND NOT EXISTS(SELECT 1 FROM intelligence.review_cases rc JOIN users eu ON eu.id=rc.user_id
       WHERE eu.subject_id=c.id AND rc.artifact_id IN(qc.id,r.id) AND rc.established_violation)
   ORDER BY qc.issued_at DESC,qc.id DESC LIMIT 1) q ON true
 LEFT JOIN users u ON u.subject_id=c.id AND u.role='candidate'
 LEFT JOIN intelligence.preferences p ON p.user_id=u.id
 WHERE NOT c.employment_blocked AND c.consent_processing AND r.status<>'archived'
   AND (($1::text IS NOT NULL AND c.id=$1) OR ($1 IS NULL AND rg.employer_eligible))
 ORDER BY r.updated_at DESC,r.id LIMIT 100"#;
async fn candidates(s: &AppState, owner: Option<&str>) -> Result<Vec<Value>> {
    Ok(sqlx::query_scalar(CANDIDATE_SQL)
        .bind(owner)
        .fetch_all(&s.db)
        .await?)
}
async fn vacancies(s: &AppState, owner: Option<&str>) -> Result<Vec<Value>> {
    Ok(sqlx::query_scalar("SELECT jsonb_build_object('id',v.id,'title',v.title,'specialization',v.specialization,'grade',CASE WHEN v.grade='' THEN 'junior' ELSE v.grade END,'skills',v.skills,'salary',v.salary_to,'team',coalesce(t.value,'{}')) FROM vacancies v LEFT JOIN intelligence.company_twins t ON t.company_id=v.company_id WHERE v.status='published' AND ($1::text IS NULL OR v.company_id=$1) ORDER BY v.updated_at DESC LIMIT 100").bind(owner).fetch_all(&s.db).await?)
}
async fn company_twin(State(s): State<AppState>, a: Actor) -> Result<Json<Value>> {
    a.verified_employer(&s).await?;
    let v: Option<Value> = sqlx::query_scalar(
        "SELECT to_jsonb(t) FROM intelligence.company_twins t WHERE company_id=$1",
    )
    .bind(a.subject_id)
    .fetch_optional(&s.db)
    .await?;
    Ok(Json(
        json!({"twin":v.unwrap_or(json!({"value":{},"version":0}))}),
    ))
}
async fn save_twin(
    State(s): State<AppState>,
    a: Actor,
    Json(p): Json<Value>,
) -> Result<Json<Value>> {
    a.verified_employer(&s).await?;
    let map = p
        .as_object()
        .ok_or_else(|| AppError::bad("Проверьте параметры команды"))?;
    if map.keys().any(|k| {
        ![
            "collaboration",
            "pace",
            "growth",
            "response_days",
            "interview_stages",
        ]
        .contains(&k.as_str())
    }) {
        return Err(AppError::bad(
            "Разрешены только параметры рабочего процесса",
        ));
    }
    for (k, values) in [
        ("collaboration", vec!["team", "independent", ""]),
        ("pace", vec!["stable", "dynamic", ""]),
        ("growth", vec!["expert", "leadership", "explore", ""]),
    ] {
        if p.get(k)
            .is_some_and(|v| !values.contains(&v.as_str().unwrap_or("invalid")))
        {
            return Err(AppError::bad("Проверьте рабочие предпочтения"));
        }
    }
    if p.get("response_days").is_some_and(|x| {
        !x.as_f64()
            .is_some_and(|v| v.is_finite() && (0.25..=14.).contains(&v))
    }) || p
        .get("interview_stages")
        .is_some_and(|x| !x.as_i64().is_some_and(|v| (1..=7).contains(&v)))
    {
        return Err(AppError::bad("Проверьте этапы и срок ответа"));
    }
    let v:Value=sqlx::query_scalar("INSERT INTO intelligence.company_twins(company_id,value) VALUES($1,$2) ON CONFLICT(company_id) DO UPDATE SET value=$2,version=company_twins.version+1,updated_at=now() RETURNING to_jsonb(company_twins)").bind(a.subject_id).bind(p).fetch_one(&s.db).await?;
    Ok(Json(json!({"twin":v})))
}
async fn workspace(State(s): State<AppState>, a: Actor) -> Result<Json<Value>> {
    if a.role == "candidate" {
        let cs = candidates(&s, Some(&a.subject_id)).await?;
        let vs = vacancies(&s, None).await?;
        let mut items = vec![];
        for c in cs {
            items.push(json!({"resume":c,"next_proof":compute(&json!({"operation":"twin_next_proof","candidate":c,"vacancies":vs})).await?,"transfer":compute(&json!({"operation":"twin_transfer","candidate":c,"roles":crate::matching::taxonomy()})).await?}));
        }
        Ok(Json(json!({"items":items})))
    } else {
        a.verified_employer(&s).await?;
        Ok(Json(
            json!({"vacancies":vacancies(&s,Some(&a.subject_id)).await?,"candidate_profiles":candidates(&s,None).await?.len()}),
        ))
    }
}
async fn allocation(State(s): State<AppState>, a: Actor) -> Result<Json<Value>> {
    a.verified_employer(&s).await?;
    crate::security::throttle(&s, &format!("allocate:{}", a.id), 20).await?;
    let cs = candidates(&s, None).await?;
    let vs = vacancies(&s, Some(&a.subject_id)).await?;
    if vs.len() > 30 {
        return Err(AppError::bad(
            "Выберите портфель до 30 опубликованных вакансий",
        ));
    }
    Ok(Json(
        compute(&json!({"operation":"twin_allocation","candidates":cs,"vacancies":vs})).await?,
    ))
}
async fn diagnosis(
    State(s): State<AppState>,
    a: Actor,
    Path(id): Path<String>,
) -> Result<Json<Value>> {
    a.verified_employer(&s).await?;
    let vs = vacancies(&s, Some(&a.subject_id)).await?;
    let v = vs
        .iter()
        .find(|v| v["id"] == id)
        .ok_or_else(AppError::missing)?;
    Ok(Json(compute(&json!({"operation":"twin_diagnosis","vacancy":v,"candidates":candidates(&s,None).await?})).await?))
}
async fn compatibility(
    State(s): State<AppState>,
    a: Actor,
    Path((rid, vid)): Path<(String, String)>,
) -> Result<Json<Value>> {
    if a.role == "employer" {
        a.verified_employer(&s).await?;
    }
    let cs = candidates(
        &s,
        if a.role == "candidate" {
            Some(&a.subject_id)
        } else {
            None
        },
    )
    .await?;
    let vs = vacancies(
        &s,
        if a.role == "employer" {
            Some(&a.subject_id)
        } else {
            None
        },
    )
    .await?;
    let c = cs
        .iter()
        .find(|x| x["id"] == rid)
        .ok_or_else(AppError::missing)?;
    let v = vs
        .iter()
        .find(|x| x["id"] == vid)
        .ok_or_else(AppError::missing)?;
    Ok(Json(
        compute(&json!({"operation":"twin_compatibility","candidate":c,"vacancy":v})).await?,
    ))
}

async fn issue_passport(State(s): State<AppState>, a: Actor) -> Result<Json<Value>> {
    a.require("candidate")?;
    crate::security::throttle(&s, &format!("passport:{}", a.id), 10).await?;
    let certificates:Vec<Value>=sqlx::query_scalar("SELECT jsonb_build_object('id',q.id,'specialization',q.specialization,'grade',q.grade,'skills',q.skills,'issued_at',q.issued_at,'valid_until',q.valid_until,'method',q.assessment_version,'scope',q.scope) FROM qualification_certificates q WHERE candidate_id=$1 AND revoked_at IS NULL AND valid_until>now() AND NOT EXISTS(SELECT 1 FROM intelligence.evidence_controls ec WHERE ec.user_id=$2 AND ec.evidence_id='cert:'||q.id AND (ec.hidden OR ec.disputed)) ORDER BY issued_at DESC LIMIT 20").bind(&a.subject_id).bind(&a.id).fetch_all(&s.db).await?;
    if certificates.is_empty() {
        return Err(AppError::conflict(
            "Сначала подтвердите квалификацию; паспорт содержит только действующие доказательства",
        ));
    }
    let ids: Vec<Value> = certificates.iter().map(|c| c["id"].clone()).collect();
    let id = new_id("PP");
    let out=compute(&json!({"operation":"passport_issue","id":id,"claims":{"certificates":certificates,"schema":"proofit-proof-1","contains_contacts":false}})).await?;
    sqlx::query("INSERT INTO intelligence.passports(id,user_id,digest,certificate_ids,expires_at) VALUES($1,$2,$3,$4,to_timestamp($5))").bind(&id).bind(&a.id).bind(out["digest"].as_str()).bind(json!(ids)).bind(out["expires_at"].as_f64().unwrap_or(0.)).execute(&s.db).await?;
    Ok(Json(json!({"id":id,"credential":out})))
}
async fn passports(State(s): State<AppState>, a: Actor) -> Result<Json<Value>> {
    let items:Vec<Value>=sqlx::query_scalar("SELECT to_jsonb(p)-'digest' FROM intelligence.passports p WHERE user_id=$1 ORDER BY issued_at DESC LIMIT 30").bind(a.id).fetch_all(&s.db).await?;
    Ok(Json(json!({"items":items})))
}
async fn public_key() -> Result<Json<Value>> {
    Ok(Json(
        compute(&json!({"operation":"passport_public"})).await?,
    ))
}
#[derive(Deserialize)]
struct Credential {
    token: String,
}
async fn verify_passport(
    State(s): State<AppState>,
    Json(p): Json<Credential>,
) -> Result<Json<Value>> {
    let out = compute(&json!({"operation":"passport_verify","token":p.token})).await?;
    if out["signature_valid"] != true {
        return Ok(Json(json!({"valid":false,"reason":"signature_or_expiry"})));
    }
    let valid:bool=sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM intelligence.passports pp WHERE pp.id=$1 AND pp.digest=$2 AND pp.revoked_at IS NULL AND pp.expires_at>now() AND NOT EXISTS(SELECT 1 FROM jsonb_array_elements_text(pp.certificate_ids) cid(id) WHERE NOT EXISTS(SELECT 1 FROM qualification_certificates q WHERE q.id=cid.id AND q.revoked_at IS NULL AND q.valid_until>now()) OR EXISTS(SELECT 1 FROM intelligence.evidence_controls ec WHERE ec.user_id=pp.user_id AND ec.evidence_id='cert:'||cid.id AND (ec.hidden OR ec.disputed))))").bind(out["id"].as_str()).bind(hash_token(&p.token)).fetch_one(&s.db).await?;
    Ok(Json(
        json!({"valid":valid,"signature_valid":true,"proof":if valid{out["proof"].clone()}else{Value::Null},"reason":if valid{"active"}else{"revoked_expired_or_evidence_hidden"}}),
    ))
}
async fn revoke_passport(
    State(s): State<AppState>,
    a: Actor,
    Path(id): Path<String>,
) -> Result<Json<Value>> {
    let n=sqlx::query("UPDATE intelligence.passports SET revoked_at=coalesce(revoked_at,now()) WHERE id=$1 AND user_id=$2").bind(id).bind(a.id).execute(&s.db).await?;
    if n.rows_affected() != 1 {
        return Err(AppError::missing());
    }
    Ok(Json(json!({"revoked":true})))
}
#[derive(Deserialize)]
struct Assistance {
    #[serde(default)]
    ai_assisted: bool,
}
async fn defense(
    State(s): State<AppState>,
    a: Actor,
    Path(id): Path<String>,
    Json(p): Json<Assistance>,
) -> Result<Json<Value>> {
    a.require("candidate")?;
    let row:Option<(String,String)>=sqlx::query_as("SELECT submission,kind FROM intelligence.arena_attempts WHERE id=$1 AND user_id=$2 AND status='completed' AND kind IN ('python','sql','typescript')").bind(&id).bind(&a.id).fetch_optional(&s.db).await?;
    let (code, language) = row.ok_or_else(AppError::missing)?;
    let out=compute(&json!({"operation":"authorship_defense","code":code,"language":language,"ai_assisted":p.ai_assisted})).await?;
    sqlx::query("UPDATE intelligence.arena_attempts SET defense=$3,ai_assisted=$4 WHERE id=$1 AND user_id=$2").bind(id).bind(a.id).bind(&out).bind(p.ai_assisted).execute(&s.db).await?;
    Ok(Json(out))
}
async fn expert(s: &AppState, a: &Actor) -> Result<()> {
    let yes: bool = sqlx::query_scalar(
        "SELECT EXISTS(SELECT 1 FROM intelligence.assessment_experts WHERE user_id=$1 AND approved)",
    )
    .bind(&a.id)
    .fetch_one(&s.db)
    .await?;
    if yes {
        Ok(())
    } else {
        Err(AppError::forbidden())
    }
}
async fn reviews(State(s): State<AppState>, a: Actor) -> Result<Json<Value>> {
    let is_expert = expert(&s, &a).await.is_ok();
    let items:Vec<Value>=sqlx::query_scalar("SELECT to_jsonb(r) FROM intelligence.review_cases r WHERE user_id=$1 OR $2 ORDER BY created_at DESC LIMIT 100").bind(a.id).bind(is_expert).fetch_all(&s.db).await?;
    Ok(Json(json!({"items":items,"can_review":is_expert})))
}
#[derive(Deserialize)]
struct ReviewDecision {
    reason: String,
    status: Option<String>,
}
async fn challenge(
    State(s): State<AppState>,
    a: Actor,
    Path(id): Path<String>,
    Json(p): Json<ReviewDecision>,
) -> Result<Json<Value>> {
    if !(10..=2000).contains(&p.reason.len()) {
        return Err(AppError::bad("Объясните основание оспаривания"));
    }
    let n=sqlx::query("UPDATE intelligence.review_cases SET status='challenged',decision=$3,resolved_at=NULL WHERE id=$1 AND user_id=$2").bind(id).bind(a.id).bind(p.reason).execute(&s.db).await?;
    if n.rows_affected() != 1 {
        return Err(AppError::missing());
    }
    Ok(Json(json!({"status":"challenged"})))
}
async fn resolve(
    State(s): State<AppState>,
    a: Actor,
    Path(id): Path<String>,
    Json(p): Json<ReviewDecision>,
) -> Result<Json<Value>> {
    expert(&s, &a).await?;
    let status = p.status.unwrap_or_default();
    if !["confirmed", "dismissed"].contains(&status.as_str())
        || !(20..=2000).contains(&p.reason.len())
    {
        return Err(AppError::bad("Укажите решение и проверяемое основание"));
    }
    let n=sqlx::query("UPDATE intelligence.review_cases SET status=$3,reviewer_id=$2,decision=$4,resolved_at=now() WHERE id=$1 AND user_id<>$2 AND status IN ('pending','challenged')").bind(id).bind(a.id).bind(&status).bind(p.reason).execute(&s.db).await?;
    if n.rows_affected() != 1 {
        return Err(AppError::conflict(
            "Нельзя пересматривать собственное решение или закрытый случай",
        ));
    }
    Ok(Json(json!({"status":status})))
}

async fn followups(State(s): State<AppState>, a: Actor) -> Result<Json<Value>> {
    let items:Vec<Value>=sqlx::query_scalar("SELECT to_jsonb(f)||jsonb_build_object('offer_title',i.title) FROM intelligence.followups f JOIN invitations i ON i.id=f.invitation_id WHERE ($1='candidate' AND i.candidate_id=$2) OR ($1='employer' AND i.company_id=$2) ORDER BY f.due_at LIMIT 100").bind(a.role).bind(a.subject_id).fetch_all(&s.db).await?;
    Ok(Json(json!({"items":items})))
}
#[derive(Deserialize)]
struct FollowupStart {
    invitation_id: String,
    started_at: chrono::DateTime<chrono::Utc>,
}
async fn schedule_followups(
    State(s): State<AppState>,
    a: Actor,
    Json(p): Json<FollowupStart>,
) -> Result<Json<Value>> {
    if (p.started_at - chrono::Utc::now()).num_days().abs() > 365 {
        return Err(AppError::bad("Проверьте дату начала сотрудничества"));
    }
    let owner:bool=sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM invitations WHERE id=$1 AND status='accepted' AND (($2='candidate' AND candidate_id=$3) OR ($2='employer' AND company_id=$3)))").bind(&p.invitation_id).bind(&a.role).bind(&a.subject_id).fetch_one(&s.db).await?;
    if !owner {
        return Err(AppError::missing());
    }
    let mut tx = s.db.begin().await?;
    for day in [30, 60, 90] {
        sqlx::query("INSERT INTO intelligence.followups(id,user_id,invitation_id,day,due_at) VALUES($1,$2,$3,$4,$5) ON CONFLICT(invitation_id,day) DO NOTHING").bind(new_id("FU")).bind(&a.id).bind(&p.invitation_id).bind(day).bind(p.started_at+chrono::Duration::days(day as i64)).execute(&mut *tx).await?;
    }
    tx.commit().await?;
    Ok(Json(json!({"scheduled":[30,60,90]})))
}
#[derive(Deserialize)]
struct FollowupResult {
    result: Value,
}
async fn update_followup(
    State(s): State<AppState>,
    a: Actor,
    Path(id): Path<String>,
    Json(p): Json<FollowupResult>,
) -> Result<Json<Value>> {
    if !p.result.is_object() || p.result.to_string().len() > 3000 {
        return Err(AppError::bad("Проверьте результат"));
    }
    let key = if a.role == "candidate" {
        "candidate"
    } else {
        "employer"
    };
    let n=sqlx::query("UPDATE intelligence.followups f SET result=coalesce(f.result,'{}')||jsonb_build_object($4::text,$5::jsonb),confirmed_by_candidate=f.confirmed_by_candidate OR $2='candidate',confirmed_by_employer=f.confirmed_by_employer OR $2='employer',updated_at=now() FROM invitations i WHERE f.id=$1 AND i.id=f.invitation_id AND (($2='candidate' AND i.candidate_id=$3) OR ($2='employer' AND i.company_id=$3))").bind(id).bind(a.role).bind(a.subject_id).bind(key).bind(p.result).execute(&s.db).await?;
    if n.rows_affected() != 1 {
        return Err(AppError::missing());
    }
    Ok(Json(
        json!({"recorded":true,"ranking_automatically_changed":false}),
    ))
}
async fn campaigns(State(s): State<AppState>, a: Actor) -> Result<Json<Value>> {
    a.verified_employer(&s).await?;
    let items:Vec<Value>=sqlx::query_scalar("SELECT to_jsonb(c) FROM intelligence.weekly_campaigns c WHERE company_id=$1 ORDER BY created_at DESC").bind(a.subject_id).fetch_all(&s.db).await?;
    Ok(Json(json!({"items":items})))
}
#[derive(Deserialize)]
struct Campaign {
    vacancy_id: String,
    enabled: bool,
}
async fn save_campaign(
    State(s): State<AppState>,
    a: Actor,
    Json(p): Json<Campaign>,
) -> Result<Json<Value>> {
    a.verified_employer(&s).await?;
    let v:Option<Value>=sqlx::query_scalar("INSERT INTO intelligence.weekly_campaigns(id,company_id,vacancy_id,enabled) SELECT $1,$2,v.id,$4 FROM vacancies v WHERE v.id=$3 AND company_id=$2 AND status='published' ON CONFLICT(company_id,vacancy_id) DO UPDATE SET enabled=$4 RETURNING to_jsonb(weekly_campaigns)").bind(new_id("WC")).bind(a.subject_id).bind(p.vacancy_id).bind(p.enabled).fetch_optional(&s.db).await?;
    Ok(Json(v.ok_or_else(AppError::missing)?))
}
