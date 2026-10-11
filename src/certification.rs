//! Adaptive qualification with server time, revision fencing and immutable role certificates.
use crate::{
    AppState,
    auth::{Actor, new_id},
    error::{AppError, Result},
    intelligence::compute,
};
use axum::{
    Json,
    extract::{Path, State},
};
use serde::Deserialize;
use serde_json::{Value, json};

async fn owned(s: &AppState, a: &Actor, id: &str) -> Result<Value> {
    a.require("candidate")?;
    sqlx::query("UPDATE qualification_tests q SET status='ready',updated_at=now() FROM resume_profiles r WHERE q.resume_id=r.id AND r.id=$1 AND r.candidate_id=$2 AND q.status='cooldown' AND q.available_at<=now()").bind(id).bind(&a.subject_id).execute(&s.db).await?;
    sqlx::query_scalar("SELECT to_jsonb(q)||jsonb_build_object('resume_id',r.id,'specialization',r.specialization,'declared_grade',r.declared_grade,'target_position',r.target_position) FROM resume_profiles r JOIN qualification_tests q ON q.resume_id=r.id WHERE r.id=$1 AND r.candidate_id=$2 AND r.status<>'archived'").bind(id).bind(&a.subject_id).fetch_optional(&s.db).await?.ok_or_else(AppError::missing)
}
async fn public(row: Value) -> Result<Value> {
    let p = if row["status"] == "in_progress" {
        compute(&json!({"operation":"professional_public","contract":row["contract"]})).await?
    } else {
        json!({})
    };
    let questions = if p["question"].is_object() {
        vec![
            json!({"number":p["answered"].as_i64().unwrap_or(0)+1,"prompt":p["question"]["prompt"],"options":p["question"]["options"]}),
        ]
    } else {
        vec![]
    };
    Ok(
        json!({"status":if ["queued","processing","failed"].contains(&row["status"].as_str().unwrap_or("")){"ready"}else{row["status"].as_str().unwrap_or("ready")},"generation_status":"ready","questions":questions,"question_id":p["question"]["id"],"time_limit_seconds":p["question"]["time_limit_seconds"],"answered":p["answered"],"max_questions":p["max_questions"],"revision":row["revision"],"score":row["score"],"passed":row["passed"],"available_at":row["available_at"],"certified_grade":row["certified_grade"],"review":row["last_attempt"],"attempts":row["attempts"],"adaptive":true,"certification_scope":"role-knowledge","professional_role_certified":false}),
    )
}
pub async fn get(
    State(s): State<AppState>,
    a: Actor,
    Path(id): Path<String>,
) -> Result<Json<Value>> {
    Ok(Json(public(owned(&s, &a, &id).await?).await?))
}
pub async fn start(
    State(s): State<AppState>,
    a: Actor,
    Path(id): Path<String>,
) -> Result<Json<Value>> {
    a.require("candidate")?;
    crate::security::throttle(&s, &format!("cert-start:{}", a.id), 20).await?;
    let mut tx = s.db.begin().await?;
    let r:Option<Value>=sqlx::query_scalar("SELECT to_jsonb(r)||jsonb_build_object('test_status',q.status) FROM resume_profiles r JOIN qualification_tests q ON q.resume_id=r.id WHERE r.id=$1 AND r.candidate_id=$2 AND r.status<>'archived' FOR UPDATE OF r,q").bind(&id).bind(&a.subject_id).fetch_optional(&mut *tx).await?;
    let r = r.ok_or_else(AppError::missing)?;
    if r["test_status"] == "in_progress" {
        tx.commit().await?;
        return get(State(s), a, Path(id)).await;
    }
    let waiting:bool=sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM qualification_attempt_history WHERE candidate_id=$1 AND specialization=$2 AND grade=$3 AND available_at>now())").bind(&a.subject_id).bind(r["specialization"].as_str()).bind(r["declared_grade"].as_str()).fetch_one(&mut *tx).await?;
    if waiting {
        return Err(AppError::conflict(
            "Пересдача этого направления и грейда доступна после окончания срока ожидания",
        ));
    }
    let changing:bool=sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM qualification_certificates WHERE candidate_id=$1 AND specialization=$2 AND grade<>$3 AND revoked_at IS NULL AND issued_at>now()-interval '90 days')").bind(&a.subject_id).bind(r["specialization"].as_str()).bind(r["declared_grade"].as_str()).fetch_one(&mut *tx).await?;
    if changing {
        return Err(AppError::conflict(
            "Изменение подтверждённого грейда доступно через 90 дней после подтверждения",
        ));
    }
    let exposure_rows:Vec<(String,i64)>=sqlx::query_as("SELECT item_id,count(*) FROM (SELECT item_id FROM intelligence.professional_responses UNION ALL SELECT item_id FROM intelligence.qualification_responses) x GROUP BY item_id").fetch_all(&mut *tx).await?;
    let exposure: serde_json::Map<String, Value> = exposure_rows
        .into_iter()
        .map(|(id, count)| (id, json!(count)))
        .collect();
    let quarantined:Vec<String>=sqlx::query_scalar("SELECT family FROM (SELECT family,correct,expected_correct,created_at,pilot FROM intelligence.professional_responses UNION ALL SELECT family,correct,expected_correct,created_at,pilot FROM intelligence.qualification_responses) x WHERE created_at>now()-interval '7 days' AND NOT pilot GROUP BY family HAVING count(*)>=50 AND (sum(correct::int)-sum(expected_correct))/sqrt(greatest(1,sum(expected_correct*(1-expected_correct))))>4").fetch_all(&mut *tx).await?;
    let pilots:Vec<Value>=sqlx::query_scalar("SELECT content||jsonb_build_object('id',id,'status',status,'calibration',calibration) FROM intelligence.item_drafts WHERE specialization=$1 AND status IN ('pilot','active') ORDER BY updated_at DESC LIMIT 12").bind(r["specialization"].as_str()).fetch_all(&mut *tx).await?;
    let prepared=compute(&json!({"operation":"certification_prepare","resume":r,"seed":new_id("seed"),"exposure":exposure,"quarantined":quarantined,"pilots":pilots})).await?;
    sqlx::query("UPDATE qualification_tests SET contract=$2,target_specialization=$3,target_grade=$4,status='in_progress',generation_status='ready',revision=0,item_started_at=now(),started_at=now(),questions='[]',updated_at=now() WHERE resume_id=$1").bind(&id).bind(&prepared["contract"]).bind(prepared["target_specialization"].as_str()).bind(prepared["target_grade"].as_str()).execute(&mut *tx).await?;
    tx.commit().await?;
    get(State(s), a, Path(id)).await
}
#[derive(Deserialize)]
pub struct Submit {
    pub question_id: String,
    pub revision: i32,
    pub answers: Vec<Vec<i32>>,
}
pub async fn submit(
    State(s): State<AppState>,
    a: Actor,
    Path(id): Path<String>,
    Json(p): Json<Submit>,
) -> Result<Json<Value>> {
    a.require("candidate")?;
    crate::security::throttle(&s, &format!("cert-answer:{}", a.id), 100).await?;
    if p.answers.len() != 1 || p.answers[0].len() != 1 {
        return Err(AppError::bad("Выберите один вариант текущего задания"));
    }
    let mut tx = s.db.begin().await?;
    let row:Option<Value>=sqlx::query_scalar("SELECT to_jsonb(q)||jsonb_build_object('elapsed_ms',greatest(0,extract(epoch FROM(now()-q.item_started_at))*1000)::bigint) FROM qualification_tests q JOIN resume_profiles r ON r.id=q.resume_id WHERE r.id=$1 AND r.candidate_id=$2 AND q.status='in_progress' AND q.revision=$3 AND r.specialization=q.target_specialization AND r.declared_grade=q.target_grade FOR UPDATE OF q,r").bind(&id).bind(&a.subject_id).bind(p.revision).fetch_optional(&mut *tx).await?;
    let row =
        row.ok_or_else(|| AppError::conflict("Задание уже обработано или цель резюме изменилась"))?;
    let out=compute(&json!({"operation":"certification_step","contract":row["contract"],"question_id":p.question_id,"answer":p.answers[0][0],"elapsed_ms":row["elapsed_ms"]})).await?;
    let obs = &out["observation"];
    sqlx::query("INSERT INTO intelligence.qualification_responses(user_id,resume_id,item_id,family,topic,pilot,correct,theta_before,expected_correct,elapsed_ms) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)").bind(&a.id).bind(&id).bind(obs["question_id"].as_str()).bind(obs["family"].as_str()).bind(obs["topic"].as_str()).bind(obs["pilot"].as_bool().unwrap_or(false)).bind(obs["correct"].as_bool().unwrap_or(false)).bind(obs["theta_before"].as_f64().unwrap_or(0.)).bind(obs["expected_correct"].as_f64().unwrap_or(0.)).bind(obs["elapsed_ms"].as_i64().unwrap_or(0)).execute(&mut *tx).await?;
    if out["completed"] == true {
        let passed = out["result"]["passed"] == true;
        let mut review = out["result"].clone();
        let contract = &out["contract"];
        let mut questions = vec![];
        for (i, answer) in contract["answers"].as_array().unwrap().iter().enumerate() {
            if let Some(q) = contract["bank"]
                .as_array()
                .unwrap()
                .iter()
                .find(|q| q["id"] == answer["question_id"])
            {
                questions.push(json!({"number":i+1,"prompt":q["prompt"],"options":q["options"],"answer":[answer["answer"]],"correct":[q["correct"]],"is_correct":answer["correct"]}));
            }
        }
        review["questions"] = json!(questions);
        review["submitted_at"] = json!(chrono::Utc::now());
        if out["result"]["review_required"]==true {
            sqlx::query("INSERT INTO intelligence.review_cases(id,user_id,artifact_id,task_key,evidence) VALUES($1,$2,$3,$4,$5) ON CONFLICT(user_id,artifact_id) DO NOTHING").bind(new_id("RC")).bind(&a.id).bind(&id).bind("role-knowledge-response-pattern").bind(&out["result"]).execute(&mut *tx).await?;
        }
        if passed {
            sqlx::query("INSERT INTO qualification_certificates(id,candidate_id,resume_id,specialization,grade,skills,assessment_version,attempt) VALUES($1,$2,$3,$4,$5,$6,$7,$8)").bind(new_id("CERT")).bind(&a.subject_id).bind(&id).bind(row["target_specialization"].as_str()).bind(row["target_grade"].as_str()).bind(&out["result"]["certified_skills"]).bind("certification-3.0.0").bind(&review).execute(&mut *tx).await?;
        }
        sqlx::query("INSERT INTO qualification_attempt_history(id,candidate_id,resume_id,specialization,grade,result,available_at) VALUES($1,$2,$3,$4,$5,$6,now()+interval '30 days')").bind(new_id("QH")).bind(&a.subject_id).bind(&id).bind(row["target_specialization"].as_str()).bind(row["target_grade"].as_str()).bind(&review).execute(&mut *tx).await?;
        sqlx::query("UPDATE qualification_tests SET contract=$2,status=$3,score=$4,passed=$5,last_attempt=$6,attempts=attempts+1,revision=revision+1,finished_at=now(),available_at=now()+interval '30 days',certified_grade=CASE WHEN $5 THEN target_grade ELSE certified_grade END,certified_specialization=CASE WHEN $5 THEN target_specialization ELSE certified_specialization END,certified_score=CASE WHEN $5 THEN $4 ELSE certified_score END,certified_skills=CASE WHEN $5 THEN $7 ELSE certified_skills END,grade_changed_at=CASE WHEN $5 AND certified_grade IS DISTINCT FROM target_grade THEN now() ELSE grade_changed_at END,certified_at=CASE WHEN $5 THEN now() ELSE certified_at END,updated_at=now() WHERE resume_id=$1").bind(&id).bind(&out["contract"]).bind(if passed{"passed"}else{"cooldown"}).bind(out["result"]["score"].as_f64().unwrap_or(0.).round() as i32).bind(passed).bind(review).bind(&out["result"]["certified_skills"]).execute(&mut *tx).await?;
    } else {
        sqlx::query("UPDATE qualification_tests SET contract=$2,revision=revision+1,item_started_at=now(),updated_at=now() WHERE resume_id=$1").bind(&id).bind(&out["contract"]).execute(&mut *tx).await?;
    }
    tx.commit().await?;
    get(State(s), a, Path(id)).await
}
