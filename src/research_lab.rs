//! Evidence-bound public contributions and observed two-sided market decisions.
use crate::{AppState,auth::{Actor,new_id,hash_token},error::{AppError,Result},intelligence::compute};
use axum::{Json,Router,extract::{State,Path,Query},routing::{get,post}};
use serde::Deserialize;
use serde_json::{Value,json};
const PAIRED_OBSERVATIONS:&str="WITH x AS(SELECT d.*,candidate_accepts IS NOT NULL AND employer_accepts IS NOT NULL done FROM intelligence.bilateral_decisions d JOIN candidates c ON c.id=d.candidate_id JOIN vacancies v ON v.id=d.vacancy_id JOIN companies co ON co.id=v.company_id WHERE vacancy_id=$1 AND stage=$2 AND(v.synthetic OR co.synthetic OR NOT c.synthetic)) SELECT jsonb_build_object('candidate',jsonb_build_object('accepted',count(*) FILTER(WHERE done AND candidate_accepts),'declined',count(*) FILTER(WHERE done AND NOT candidate_accepts),'censored',count(*) FILTER(WHERE NOT done)),'employer',jsonb_build_object('accepted',count(*) FILTER(WHERE done AND employer_accepts),'declined',count(*) FILTER(WHERE done AND NOT employer_accepts),'censored',count(*) FILTER(WHERE NOT done)),'joint',jsonb_build_object('accepted',count(*) FILTER(WHERE done AND candidate_accepts AND employer_accepts),'declined',count(*) FILTER(WHERE done AND NOT(candidate_accepts AND employer_accepts)),'censored',count(*) FILTER(WHERE NOT done))) FROM x";

pub fn routes()->Router<AppState>{Router::new()
 .route("/workspace",get(workspace))
 .route("/github/profile",post(profile))
 .route("/github/repository",post(repository))
 .route("/github/challenge",post(challenge))
 .route("/github/verify",post(verify))
 .route("/github/pr",post(import_pr))
 .route("/github/pr/{id}/answers",axum::routing::put(answers))
 .route("/github/pr/{id}/review",post(review))
 .route("/matrix/{specialization}",get(matrix))
 .route("/bilateral/{id}",get(bilateral))
 .route("/bilateral/{id}/decision",post(decision))
 .route("/bilateral/{id}/participants",get(participants))
 .route("/bilateral/{id}/freeze",post(freeze_prediction))
 .route("/validation/forecast",get(forecast_validation))
 .route("/validation/export",get(forecast_export))
 .route("/forms/report/{specialization}",get(form_report))
 .route("/reliability/{id}",get(reliability))
 .route("/market/{id}",get(market))
 .route("/forms/{resume}",post(form_assignment))}

pub async fn export_owned(s:&AppState,owner:&str)->Result<Value>{
 let account:Option<Value>=sqlx::query_scalar("SELECT to_jsonb(g) FROM intelligence.github_accounts g WHERE user_id=$1").bind(owner).fetch_optional(&s.db).await?;
 let defenses:Vec<Value>=sqlx::query_scalar("SELECT to_jsonb(g) FROM intelligence.github_defenses g WHERE user_id=$1 ORDER BY created_at").bind(owner).fetch_all(&s.db).await?;
 let forms:Vec<Value>=sqlx::query_scalar("SELECT to_jsonb(f) FROM intelligence.form_assignments f WHERE user_id=$1 ORDER BY created_at").bind(owner).fetch_all(&s.db).await?;
 let intentions:Vec<Value>=sqlx::query_scalar("SELECT to_jsonb(d) FROM intelligence.bilateral_decisions d JOIN users u ON (u.role='candidate' AND u.subject_id=d.candidate_id) OR (u.role='employer' AND EXISTS(SELECT 1 FROM vacancies v WHERE v.id=d.vacancy_id AND v.company_id=u.subject_id)) WHERE u.id=$1").bind(owner).fetch_all(&s.db).await?;
 let predictions:Vec<Value>=sqlx::query_scalar("SELECT to_jsonb(p)||jsonb_build_object('first_paired_outcome',to_jsonb(o)) FROM intelligence.prospective_predictions p JOIN users u ON u.id=$1 LEFT JOIN intelligence.prospective_outcomes o ON o.prediction_id=p.id WHERE p.owner_id=u.id OR (u.role='candidate' AND p.candidate_id=u.subject_id) ORDER BY p.created_at").bind(owner).fetch_all(&s.db).await?;
 Ok(json!({"github_account":account,"contribution_defenses":defenses,"parallel_forms":forms,"bilateral_intentions":intentions,"prospective_predictions":predictions}))
}

async fn expert(s:&AppState,a:&Actor)->Result<()>{
 let yes:bool=sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM intelligence.assessment_experts WHERE user_id=$1 AND approved)").bind(&a.id).fetch_one(&s.db).await?;
 if yes{Ok(())}else{Err(AppError::forbidden())}
}
async fn workspace(State(s):State<AppState>,a:Actor)->Result<Json<Value>>{
 let can_review=expert(&s,&a).await.is_ok();
 let account:Option<Value>=sqlx::query_scalar("SELECT to_jsonb(g) FROM intelligence.github_accounts g WHERE user_id=$1").bind(&a.id).fetch_optional(&s.db).await?;
 let items:Vec<Value>=sqlx::query_scalar("SELECT to_jsonb(g)-'snapshot'||jsonb_build_object('source_url',snapshot->>'url','coverage',snapshot->'coverage','attributed_author',snapshot->'author_login') FROM intelligence.github_defenses g WHERE user_id=$1 OR $2 ORDER BY created_at DESC LIMIT 100").bind(&a.id).bind(can_review).fetch_all(&s.db).await?;
 let resumes:Vec<Value>=sqlx::query_scalar("SELECT jsonb_build_object('id',id,'title',target_position,'specialization',specialization,'grade',declared_grade) FROM resume_profiles WHERE candidate_id=$1 AND status<>'archived'").bind(&a.subject_id).fetch_all(&s.db).await?;
 Ok(Json(json!({"account":account,"items":items,"resumes":resumes,"can_review":can_review,"public_only":true,"automatic_grade_promotion":false})))
}
#[derive(Deserialize)]struct Profile{login:String}
#[derive(Deserialize)]struct Repository{repository:String}
async fn repository(State(s):State<AppState>,a:Actor,Json(p):Json<Repository>)->Result<Json<Value>>{
 a.require("candidate")?;crate::security::throttle(&s,&format!("github:{}",a.id),10).await?;
 Ok(Json(compute(&json!({"operation":"github_repository","repository":p.repository})).await?))
}
async fn profile(State(s):State<AppState>,a:Actor,Json(p):Json<Profile>)->Result<Json<Value>>{
 a.require("candidate")?;crate::security::throttle(&s,&format!("github:{}",a.id),10).await?;
 Ok(Json(compute(&json!({"operation":"github_profile","login":p.login})).await?))
}
async fn challenge(State(s):State<AppState>,a:Actor,Json(p):Json<Profile>)->Result<Json<Value>>{
 a.require("candidate")?;crate::security::throttle(&s,&format!("github:{}",a.id),10).await?;
 let account=compute(&json!({"operation":"github_profile","login":p.login})).await?;
 let nonce=format!("{}{}",uuid::Uuid::new_v4().simple(),uuid::Uuid::new_v4().simple());
 sqlx::query("INSERT INTO intelligence.github_challenges(user_id,github_id,login,nonce_hash,expires_at) VALUES($1,$2,$3,$4,now()+interval '10 minutes') ON CONFLICT(user_id) DO UPDATE SET github_id=EXCLUDED.github_id,login=EXCLUDED.login,nonce_hash=EXCLUDED.nonce_hash,expires_at=EXCLUDED.expires_at,consumed_at=NULL").bind(&a.id).bind(account["github_id"].as_i64()).bind(account["login"].as_str()).bind(hash_token(&nonce)).execute(&s.db).await?;
 Ok(Json(json!({"nonce":nonce,"filename":"proofit-claim.txt","expires_in_seconds":600,"instruction":"Создайте публичный gist от своего аккаунта GitHub с файлом proofit-claim.txt и только этим одноразовым кодом. Не добавляйте секреты или персональные данные."})))
}
#[derive(Deserialize)]struct Gist{gist_id:String}
async fn verify(State(s):State<AppState>,a:Actor,Json(p):Json<Gist>)->Result<Json<Value>>{
 a.require("candidate")?;crate::security::throttle(&s,&format!("github:{}",a.id),10).await?;
 let proof=compute(&json!({"operation":"github_verify_gist","gist_id":p.gist_id})).await?;
 let mut tx=s.db.begin().await?;
 let github_id:Option<i64>=sqlx::query_scalar("UPDATE intelligence.github_challenges SET consumed_at=now() WHERE user_id=$1 AND nonce_hash=$2 AND github_id=$3 AND consumed_at IS NULL AND expires_at>now() RETURNING github_id").bind(&a.id).bind(proof["nonce_hash"].as_str()).bind(proof["github_id"].as_i64()).fetch_optional(&mut *tx).await?;
 let github_id=github_id.ok_or_else(||AppError::conflict("Код истёк, уже использован или gist принадлежит другому аккаунту"))?;
 let taken:bool=sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM intelligence.github_accounts WHERE github_id=$1 AND user_id<>$2)").bind(github_id).bind(&a.id).fetch_one(&mut *tx).await?;
 if taken{return Err(AppError::conflict("GitHub уже привязан к другой учётной записи"));}
 sqlx::query("INSERT INTO intelligence.github_accounts(user_id,github_id,login,proof_url) VALUES($1,$2,$3,$4) ON CONFLICT(user_id) DO UPDATE SET github_id=EXCLUDED.github_id,login=EXCLUDED.login,proof_url=EXCLUDED.proof_url,verified_at=now()").bind(&a.id).bind(github_id).bind(proof["login"].as_str()).bind(proof["proof_url"].as_str()).execute(&mut *tx).await?;
 tx.commit().await?;Ok(Json(json!({"verified":true,"login":proof["login"],"authorship_verified":false})))
}
#[derive(Deserialize)]struct PrInput{url:String,resume_id:String,consent_public_evidence:bool}
async fn import_pr(State(s):State<AppState>,a:Actor,Json(p):Json<PrInput>)->Result<Json<Value>>{
 a.require("candidate")?;
 if !p.consent_public_evidence{return Err(AppError::bad("Подтвердите использование выбранного публичного артефакта для оценки"));}
 crate::security::throttle(&s,&format!("github-pr:{}",a.id),5).await?;
 let target:Option<(String,String)>=sqlx::query_as("SELECT specialization,declared_grade FROM resume_profiles WHERE id=$1 AND candidate_id=$2 AND status<>'archived'").bind(&p.resume_id).bind(&a.subject_id).fetch_optional(&s.db).await?;
 let (spec,grade)=target.ok_or_else(AppError::missing)?;
 let snapshot=compute(&json!({"operation":"github_pr","url":p.url,"specialization":spec})).await?;
 let id:String=sqlx::query_scalar("INSERT INTO intelligence.github_defenses(id,user_id,resume_id,specialization,target_grade,repository,pr_number,head_sha,artifact_digest,snapshot,questions) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) ON CONFLICT(user_id,resume_id,repository,pr_number,head_sha) DO UPDATE SET id=intelligence.github_defenses.id RETURNING id").bind(new_id("GHD")).bind(&a.id).bind(&p.resume_id).bind(&spec).bind(&grade).bind(snapshot["repository"].as_str()).bind(snapshot["number"].as_i64().unwrap_or(0) as i32).bind(snapshot["head_sha"].as_str()).bind(snapshot["digest"].as_str()).bind(&snapshot).bind(&snapshot["questions"]).fetch_one(&s.db).await?;
 Ok(Json(json!({"id":id,"questions":snapshot["questions"],"coverage":snapshot["coverage"],"source_url":snapshot["url"],"artifact_digest":snapshot["digest"],"identity_required_for_confirmation":true})))
}
#[derive(Deserialize)]struct Answers{revision:i32,answers:Value}
async fn answers(State(s):State<AppState>,a:Actor,Path(id):Path<String>,Json(p):Json<Answers>)->Result<Json<Value>>{
 a.require("candidate")?;let mut tx=s.db.begin().await?;
 let questions:Option<Value>=sqlx::query_scalar("SELECT questions FROM intelligence.github_defenses WHERE id=$1 AND user_id=$2 AND status='draft' AND revision=$3 FOR UPDATE").bind(&id).bind(&a.id).bind(p.revision).fetch_optional(&mut *tx).await?;
 let questions=questions.ok_or_else(||AppError::conflict("Защита уже отправлена или версия изменилась"))?;
 let values=p.answers.as_object().ok_or_else(||AppError::bad("Ответы должны быть связаны с вопросами"))?;
 let list=questions.as_array().unwrap();
 if values.len()!=list.len() || list.iter().any(|q|values.get(q["id"].as_str().unwrap_or("")).and_then(Value::as_str).is_none_or(|v|!(40..=8000).contains(&v.len()))){return Err(AppError::bad("Дайте содержательный ответ на каждый вопрос по изменённым строкам"));}
 sqlx::query("UPDATE intelligence.github_defenses SET answers=$2,status='submitted',revision=revision+1,submitted_at=now() WHERE id=$1").bind(&id).bind(&p.answers).execute(&mut *tx).await?;
 tx.commit().await?;Ok(Json(json!({"status":"submitted","automatic_verdict":false})))
}
#[derive(Deserialize)]struct Review{revision:i32,scores:Value,skills:Vec<String>,reason:String}
async fn review(State(s):State<AppState>,a:Actor,Path(id):Path<String>,Json(p):Json<Review>)->Result<Json<Value>>{
 expert(&s,&a).await?;
 if !(40..=4000).contains(&p.reason.len())||p.skills.is_empty()||p.skills.len()>12{return Err(AppError::bad("Укажите проверяемое основание и явно оценённые навыки"));}
 let preview:Option<Value>=sqlx::query_scalar("SELECT to_jsonb(d) FROM intelligence.github_defenses d WHERE id=$1 AND user_id<>$2 AND status='submitted' AND revision=$3").bind(&id).bind(&a.id).bind(p.revision).fetch_optional(&s.db).await?;
 let preview=preview.ok_or_else(||AppError::conflict("Версия защиты изменилась"))?;
 let fresh=compute(&json!({"operation":"github_head","url":preview["snapshot"]["url"]})).await?;
 if fresh["head_sha"]!=preview["head_sha"]{return Err(AppError::conflict("PR изменился: подготовьте защиту текущего head SHA"));}
 let mut tx=s.db.begin().await?;
 let row:Option<Value>=sqlx::query_scalar("SELECT to_jsonb(d)||jsonb_build_object('candidate_id',r.candidate_id,'resume_skills',r.skills,'github_id',g.github_id) FROM intelligence.github_defenses d JOIN resume_profiles r ON r.id=d.resume_id LEFT JOIN intelligence.github_accounts g ON g.user_id=d.user_id WHERE d.id=$1 AND d.user_id<>$2 AND d.status='submitted' AND d.revision=$3 AND d.specialization=r.specialization AND d.target_grade=r.declared_grade FOR UPDATE OF d,r").bind(&id).bind(&a.id).bind(p.revision).fetch_optional(&mut *tx).await?;
 let row=row.ok_or_else(||AppError::conflict("Нельзя оценивать собственную защиту, изменённую цель или закрытую версию"))?;
 let bound=!row["github_id"].is_null()&&(row["github_id"]==row["snapshot"]["author_github_id"] || row["snapshot"]["commits"].as_array().is_some_and(|cs|cs.iter().any(|c|c["author_github_id"]==row["github_id"])));
 if !bound{return Err(AppError::conflict("Подтвердите аккаунт автора PR или коммитов выбранного PR"));}
 if row["artifact_digest"]!=preview["artifact_digest"] || row["head_sha"]!=fresh["head_sha"]{return Err(AppError::conflict("Артефакт изменился"));}
 sqlx::query("SELECT id FROM candidates WHERE id=$1 FOR UPDATE").bind(row["candidate_id"].as_str()).execute(&mut *tx).await?;
 let declared:Vec<String>=serde_json::from_value(row["resume_skills"].clone()).unwrap_or_default();
 if p.skills.iter().any(|skill|!declared.iter().any(|s|s.eq_ignore_ascii_case(skill))){return Err(AppError::bad("Оценённый навык должен присутствовать в целевом резюме"));}
 let knowledge:bool=sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM qualification_certificates WHERE candidate_id=$1 AND specialization=$2 AND grade=$3 AND revoked_at IS NULL AND valid_until>now() AND NOT EXISTS(SELECT 1 FROM intelligence.evidence_controls ec JOIN users eu ON eu.id=ec.user_id WHERE eu.subject_id=$1 AND ec.evidence_id='cert:'||qualification_certificates.id AND (ec.hidden OR ec.disputed)))").bind(row["candidate_id"].as_str()).bind(row["specialization"].as_str()).bind(row["target_grade"].as_str()).fetch_one(&mut *tx).await?;
 let mut result=compute(&json!({"operation":"role_attestation","specialization":row["specialization"],"grade":row["target_grade"],"scores":p.scores,"identity_bound":true,"artifact_intact":true,"independent_review":true,"knowledge_scope_verified":knowledge,"leadership_verified":false})).await?;
 let blocked:bool=sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM qualification_certificates WHERE candidate_id=$1 AND grade<>$2 AND issued_at>now()-interval '90 days') OR EXISTS(SELECT 1 FROM intelligence.review_cases WHERE user_id=$3 AND artifact_id=$4 AND (established_violation OR status IN('pending','challenged')))").bind(row["candidate_id"].as_str()).bind(row["target_grade"].as_str()).bind(row["user_id"].as_str()).bind(row["resume_id"].as_str()).fetch_one(&mut *tx).await?;
 result["conditions"]["cooldown_and_review_clear"]=json!(!blocked);
 if blocked{result["role_confirmation_eligible"]=json!(false);result["missing_conditions"].as_array_mut().unwrap().push(json!("cooldown_and_review_clear"));}
 result["reason"]=json!(p.reason);result["assessed_skills"]=json!(p.skills);result["artifact_digest"]=row["artifact_digest"].clone();result["reviewer_id"]=json!(a.id);
 let certificate=if result["role_confirmation_eligible"]==true{
  let cert=new_id("CERT");sqlx::query("INSERT INTO qualification_certificates(id,candidate_id,resume_id,specialization,grade,skills,assessment_version,attempt,scope) VALUES($1,$2,$3,$4,$5,$6,'role-matrix-1.0.0',$7,'role-reviewed')").bind(&cert).bind(row["candidate_id"].as_str()).bind(row["resume_id"].as_str()).bind(row["specialization"].as_str()).bind(row["target_grade"].as_str()).bind(&result["assessed_skills"]).bind(&result).execute(&mut *tx).await?;Some(cert)
 }else{None};
 sqlx::query("UPDATE intelligence.github_defenses SET status='reviewed',review=$2,reviewer_id=$3,reviewed_at=now(),revision=revision+1 WHERE id=$1").bind(&id).bind(&result).bind(&a.id).execute(&mut *tx).await?;
 sqlx::query("INSERT INTO intelligence.role_attestations(id,user_id,defense_id,certificate_id,result) VALUES($1,$2,$3,$4,$5)").bind(new_id("RA")).bind(row["user_id"].as_str()).bind(&id).bind(&certificate).bind(&result).execute(&mut *tx).await?;
 sqlx::query("INSERT INTO audit_events(actor_id,action,entity_id,details) VALUES($1,'role.contribution_reviewed',$2,$3)").bind(&a.id).bind(&id).bind(json!({"artifact_digest":row["artifact_digest"],"certificate_id":certificate})).execute(&mut *tx).await?;
 tx.commit().await?;Ok(Json(result))
}
async fn matrix(_a:Actor,Path(spec):Path<String>)->Result<Json<Value>>{Ok(Json(compute(&json!({"operation":"role_matrix","specialization":spec})).await?))}
async fn form_assignment(State(s):State<AppState>,a:Actor,Path(id):Path<String>)->Result<Json<Value>>{
 a.require("candidate")?;let target:Option<(String,String)>=sqlx::query_as("SELECT specialization,declared_grade FROM resume_profiles WHERE id=$1 AND candidate_id=$2 AND status<>'archived'").bind(&id).bind(&a.subject_id).fetch_optional(&s.db).await?;
 let (spec,grade)=target.ok_or_else(AppError::missing)?;
 let assigned=compute(&json!({"operation":"form_assign","identity":a.id,"scope":format!("{spec}:{grade}"),"version":"forms-v1"})).await?;
 sqlx::query("INSERT INTO intelligence.form_assignments(user_id,specialization,target_grade,version,variant,assignment_hash) VALUES($1,$2,$3,'forms-v1',$4,$5) ON CONFLICT DO NOTHING").bind(&a.id).bind(spec).bind(grade).bind(assigned["variant"].as_str()).bind(assigned["assignment_hash"].as_str()).execute(&s.db).await?;Ok(Json(assigned))
}

async fn own_vacancy(s:&AppState,a:&Actor,id:&str)->Result<Value>{
 a.verified_employer(s).await?;
 sqlx::query_scalar("SELECT to_jsonb(v)||jsonb_build_object('industry',c.industry) FROM vacancies v JOIN companies c ON c.id=v.company_id WHERE v.id=$1 AND v.company_id=$2").bind(id).bind(&a.subject_id).fetch_optional(&s.db).await?.ok_or_else(AppError::missing)
}
async fn observations(s:&AppState,id:&str)->Result<Value>{
 sqlx::query_scalar("SELECT jsonb_build_object('candidate',jsonb_build_object('accepted',(SELECT count(*) FROM invitations WHERE vacancy_id=$1 AND status='accepted'),'declined',(SELECT count(*) FROM invitations WHERE vacancy_id=$1 AND status='declined'),'censored',(SELECT count(*) FROM invitations WHERE vacancy_id=$1 AND status IN('sent','viewed'))),'employer',jsonb_build_object('accepted',(SELECT count(*) FROM applications WHERE vacancy_id=$1 AND status='interview'),'declined',(SELECT count(*) FROM applications WHERE vacancy_id=$1 AND status='rejected'),'censored',(SELECT count(*) FROM applications WHERE vacancy_id=$1 AND status IN('sent','viewed'))))").bind(id).fetch_one(&s.db).await.map_err(Into::into)
}
async fn bilateral(State(s):State<AppState>,a:Actor,Path(id):Path<String>)->Result<Json<Value>>{
 let v=own_vacancy(&s,&a,&id).await?;
 let vacancy=paired_prediction(&s,&id,"vacancy").await?;let offer=paired_prediction(&s,&id,"offer").await?;
 let baseline=compute(&json!({"operation":"robust_twin","stage":"offer","candidate":offer["candidate_acceptance"],"employer":offer["employer_acceptance"]})).await?;
 Ok(Json(json!({"vacancy_id":id,"synthetic_context":v["synthetic"],"vacancy":vacancy,"offer":offer,"baseline":baseline["baseline"],"observed_workflow_counts":observations(&s,&id).await?,"denominator_note":"Общий знаменатель — пары с двумя явно выраженными намерениями для одной стадии; неполные пары цензурированы. Намерение не является исходом найма.","snapshot_at":chrono::Utc::now()})))
}
async fn paired_prediction(s:&AppState,id:&str,stage:&str)->Result<Value>{
 let p:Value=sqlx::query_scalar(PAIRED_OBSERVATIONS).bind(id).bind(stage).fetch_one(&s.db).await?;
 compute_paired(p,stage).await
}
async fn compute_paired(mut p:Value,stage:&str)->Result<Value>{
 p["operation"]=json!("bilateral");p["stage"]=json!(stage);let mut out=compute(&p).await?;out["observation_kind"]=json!("explicit paired intentions; not realized employment outcomes");Ok(out)
}
#[derive(Deserialize)]struct Decision{stage:String,accepts:bool,candidate_id:Option<String>}
async fn decision(State(s):State<AppState>,a:Actor,Path(id):Path<String>,Json(p):Json<Decision>)->Result<Json<Value>>{
 if !["vacancy","offer"].contains(&p.stage.as_str()){return Err(AppError::bad("Выберите стадию"));}
 crate::security::throttle(&s,&format!("bilateral:{}",a.id),30).await?;
 let candidate=if a.role=="candidate"{a.subject_id.clone()}else{own_vacancy(&s,&a,&id).await?;p.candidate_id.ok_or_else(||AppError::bad("Выберите существующего участника"))?};
 let allowed:bool=sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM vacancies v WHERE v.id=$1 AND (v.status='published' OR EXISTS(SELECT 1 FROM invitations i WHERE i.vacancy_id=v.id AND i.candidate_id=$2)) AND (EXISTS(SELECT 1 FROM applications ap WHERE ap.vacancy_id=v.id AND ap.candidate_id=$2 AND ap.status<>'withdrawn') OR EXISTS(SELECT 1 FROM invitations i WHERE i.vacancy_id=v.id AND i.candidate_id=$2)) AND ($3='vacancy' OR EXISTS(SELECT 1 FROM invitations i WHERE i.vacancy_id=v.id AND i.candidate_id=$2)))").bind(&id).bind(&candidate).bind(&p.stage).fetch_one(&s.db).await?;
 if !allowed{return Err(AppError::missing());}
 let mut tx=s.db.begin().await?;
 let candidate_actor=a.role=="candidate";
 sqlx::query("SELECT pg_advisory_xact_lock(hashtextextended($1,0))").bind(format!("prediction:{id}:{candidate}:{}",p.stage)).execute(&mut *tx).await?;
 sqlx::query("INSERT INTO intelligence.bilateral_decisions(vacancy_id,candidate_id,stage,candidate_accepts,employer_accepts,candidate_decided_at,employer_decided_at) VALUES($1,$2,$3,CASE WHEN $4 THEN $5 END,CASE WHEN NOT $4 THEN $5 END,CASE WHEN $4 THEN clock_timestamp() END,CASE WHEN NOT $4 THEN clock_timestamp() END) ON CONFLICT(vacancy_id,candidate_id,stage) DO UPDATE SET candidate_accepts=CASE WHEN $4 THEN $5 ELSE bilateral_decisions.candidate_accepts END,employer_accepts=CASE WHEN NOT $4 THEN $5 ELSE bilateral_decisions.employer_accepts END,candidate_decided_at=CASE WHEN $4 THEN clock_timestamp() ELSE bilateral_decisions.candidate_decided_at END,employer_decided_at=CASE WHEN NOT $4 THEN clock_timestamp() ELSE bilateral_decisions.employer_decided_at END,revision=bilateral_decisions.revision+1").bind(&id).bind(&candidate).bind(&p.stage).bind(candidate_actor).bind(p.accepts).execute(&mut *tx).await?;
 sqlx::query("INSERT INTO intelligence.prospective_outcomes(prediction_id,candidate_accepts,employer_accepts,candidate_decided_at,employer_decided_at) SELECT p.id,d.candidate_accepts,d.employer_accepts,d.candidate_decided_at,d.employer_decided_at FROM intelligence.prospective_predictions p JOIN intelligence.bilateral_decisions d ON (d.vacancy_id,d.candidate_id,d.stage)=(p.vacancy_id,p.candidate_id,p.stage) WHERE p.vacancy_id=$1 AND p.candidate_id=$2 AND p.stage=$3 AND d.candidate_accepts IS NOT NULL AND d.employer_accepts IS NOT NULL AND least(d.candidate_decided_at,d.employer_decided_at)>p.created_at ON CONFLICT DO NOTHING").bind(&id).bind(&candidate).bind(&p.stage).execute(&mut *tx).await?;
 sqlx::query("INSERT INTO audit_events(actor_id,action,entity_id,details) VALUES($1,'bilateral.intention',$2,$3)").bind(&a.id).bind(&id).bind(json!({"stage":p.stage,"accepts":p.accepts,"role":a.role})).execute(&mut *tx).await?;
 tx.commit().await?;Ok(Json(json!({"recorded":true,"is_application_or_offer_acceptance":false})))
}
async fn participants(State(s):State<AppState>,a:Actor,Path(id):Path<String>)->Result<Json<Value>>{
 own_vacancy(&s,&a,&id).await?;
 let items:Vec<Value>=sqlx::query_scalar("SELECT jsonb_build_object('candidate_id',c.id,'display_name',c.display_name,'has_offer',EXISTS(SELECT 1 FROM invitations i WHERE i.vacancy_id=$1 AND i.candidate_id=c.id)) FROM candidates c WHERE EXISTS(SELECT 1 FROM applications ap WHERE ap.vacancy_id=$1 AND ap.candidate_id=c.id AND ap.status<>'withdrawn') OR EXISTS(SELECT 1 FROM invitations i WHERE i.vacancy_id=$1 AND i.candidate_id=c.id) ORDER BY c.id LIMIT 100").bind(&id).fetch_all(&s.db).await?;
 Ok(Json(json!({"items":items})))
}
async fn form_report(State(s):State<AppState>,a:Actor,Path(spec):Path<String>)->Result<Json<Value>>{
 expert(&s,&a).await?;
 let groups:Vec<(String,Value)>=sqlx::query_as("SELECT coalesce(contract->'parallel_form'->>'variant','A'),jsonb_agg((result->>'theta')::float8) FROM intelligence.professional_attempts WHERE specialization=$1 AND status='completed' AND NOT coalesce((result->>'review_required')::boolean,false) GROUP BY 1").bind(&spec).fetch_all(&s.db).await?;
 let av=groups.iter().find(|x|x.0=="A").map(|x|x.1.clone()).unwrap_or(json!([]));let bv=groups.iter().find(|x|x.0=="B").map(|x|x.1.clone()).unwrap_or(json!([]));
 if av.as_array().unwrap().len()<2||bv.as_array().unwrap().len()<2{return Ok(Json(json!({"status":"insufficient_observations","sample_a":av.as_array().unwrap().len(),"sample_b":bv.as_array().unwrap().len(),"production_activation_allowed":false})));}
 let mut r=compute(&json!({"operation":"form_equivalence","a":av,"b":bv,"margin":0.2,"planned_looks":10})).await?;r["production_activation_allowed"]=json!(false);r["activation_note"]=json!("Результаты тренировки не являются контрольной выборкой; нужны независимые якоря и проверка по ролям до применения в аттестации");Ok(Json(r))
}
async fn reliability(State(s):State<AppState>,a:Actor,Path(id):Path<String>)->Result<Json<Value>>{
 let company:Option<Value>=sqlx::query_scalar("SELECT jsonb_build_object('verification_status',verification_status,'synthetic',synthetic) FROM companies WHERE id=$1").bind(&id).fetch_optional(&s.db).await?;let company=company.ok_or_else(AppError::missing)?;
 // Aggregates only; never expose candidate identities or contacts.
 let mut p:Value=sqlx::query_scalar("SELECT jsonb_build_object('response',jsonb_build_object('accepted',count(*) FILTER(WHERE ap.status<>'withdrawn' AND ap.first_employer_response_at<=ap.created_at+interval '7 days'),'declined',count(*) FILTER(WHERE ap.status<>'withdrawn' AND(ap.first_employer_response_at>ap.created_at+interval '7 days' OR(ap.status='sent' AND ap.first_employer_response_at IS NULL AND ap.created_at<now()-interval '7 days'))),'censored',count(*) FILTER(WHERE ap.status='withdrawn' OR(ap.first_employer_response_at IS NULL AND(ap.status<>'sent' OR ap.created_at>=now()-interval '7 days'))))) FROM applications ap JOIN vacancies v ON v.id=ap.vacancy_id WHERE v.company_id=$1").bind(&id).fetch_one(&s.db).await?;
 p["operation"]=json!("employer_reliability");p["verified_identity"]=json!(company["verification_status"]=="verified");p["synthetic"]=company["synthetic"].clone();
 let snapshot:Option<Value>=sqlx::query_scalar("SELECT value FROM intelligence.provider_snapshots WHERE provider='dreamjob' AND subject_id=$1 AND status='verified'").bind(&id).fetch_optional(&s.db).await?;p["employee_reviews"]=json!(snapshot);
 p["offer_followthrough"]=sqlx::query_scalar::<_,Value>("SELECT jsonb_build_object('accepted',count(*) FILTER(WHERE f.confirmed_by_employer),'declined',count(*) FILTER(WHERE NOT f.confirmed_by_employer AND f.due_at<now()),'censored',count(*) FILTER(WHERE NOT f.confirmed_by_employer AND f.due_at>=now())) FROM intelligence.followups f JOIN invitations i ON i.id=f.invitation_id WHERE i.company_id=$1 AND f.day=30").bind(&id).fetch_one(&s.db).await?;
 p["bilateral_followup"]=sqlx::query_scalar::<_,Value>("SELECT jsonb_build_object('accepted',count(*) FILTER(WHERE f.confirmed_by_candidate AND f.confirmed_by_employer),'declined',count(*) FILTER(WHERE NOT(f.confirmed_by_candidate AND f.confirmed_by_employer) AND f.due_at<now()),'censored',count(*) FILTER(WHERE NOT(f.confirmed_by_candidate AND f.confirmed_by_employer) AND f.due_at>=now())) FROM intelligence.followups f JOIN invitations i ON i.id=f.invitation_id WHERE i.company_id=$1 AND f.day=90").bind(&id).fetch_one(&s.db).await?;
 let mut out=compute(&p).await?;out["viewer_role"]=json!(a.role);out["observation_windows"]=json!({"response":"ответ / просмотр за 7 дней","offer_followthrough":"ответ работодателя на контрольную точку 30 дней","bilateral_followup":"ответ обеих сторон на контрольную точку 90 дней","followup_measures":"участие в контроле, не качество трудоустройства"});Ok(Json(out))
}
async fn market(State(s):State<AppState>,a:Actor,Path(id):Path<String>)->Result<Json<Value>>{
 let v=own_vacancy(&s,&a,&id).await?;
 let mut data:Value=sqlx::query_scalar("SELECT jsonb_build_object('unique_vacancies',count(DISTINCT lower(title)||':'||company_id),'synthetic_vacancies',count(*) FILTER(WHERE vacancies.synthetic),'median_salary_from',percentile_cont(.5) WITHIN GROUP(ORDER BY salary_from),'median_salary_to',percentile_cont(.5) WITHIN GROUP(ORDER BY salary_to),'new_7d',count(*) FILTER(WHERE vacancies.created_at>now()-interval '7 days')) FROM vacancies JOIN companies market_company ON market_company.id=vacancies.company_id WHERE specialization=$1 AND grade=$2 AND status='published' AND market_company.industry=$3").bind(v["specialization"].as_str()).bind(v["grade"].as_str()).bind(v["industry"].as_str()).fetch_one(&s.db).await?;
 let pool:Value=sqlx::query_scalar("SELECT jsonb_build_object('available_pool',count(DISTINCT r.candidate_id),'median_expectation',CASE WHEN count(DISTINCT r.candidate_id)>=5 THEN percentile_cont(.5) WITHIN GROUP(ORDER BY r.expected_salary) ELSE NULL END) FROM intelligence.resume_category_evidence r WHERE r.employer_eligible AND r.specialization=$1 AND r.confirmed_grade=$2").bind(v["specialization"].as_str()).bind(v["grade"].as_str()).fetch_one(&s.db).await?;
 data["pool"]=pool;data["source"]=json!("platform-inventory; not representative national labor statistics");data["scope"]=json!({"specialization":v["specialization"],"grade":v["grade"],"industry":v["industry"]});data["as_of"]=json!(chrono::Utc::now());
 data["moex"]=compute(&json!({"operation":"economic_status"})).await?;
 let interval:Option<f64>=sqlx::query_scalar("SELECT percentile_cont(.5) WITHIN GROUP(ORDER BY extract(epoch FROM(responded_at-created_at))/86400.0) FROM invitations WHERE company_id=$1 AND responded_at IS NOT NULL").bind(&a.subject_id).fetch_one(&s.db).await?;data["median_observed_response_days"]=json!(interval);
 sqlx::query("INSERT INTO intelligence.market_snapshots(company_id,specialization,grade,industry,value) VALUES($1,$2,$3,$4,$5) ON CONFLICT(company_id,specialization,grade,industry,snapshot_date) DO UPDATE SET value=EXCLUDED.value").bind(&a.subject_id).bind(v["specialization"].as_str()).bind(v["grade"].as_str()).bind(v["industry"].as_str().unwrap_or("")).bind(&data).execute(&s.db).await?;
 let history:Vec<Value>=sqlx::query_scalar("SELECT jsonb_build_object('date',snapshot_date,'value',value) FROM intelligence.market_snapshots WHERE company_id=$1 AND specialization=$2 AND grade=$3 AND industry=$4 ORDER BY snapshot_date DESC LIMIT 30").bind(&a.subject_id).bind(v["specialization"].as_str()).bind(v["grade"].as_str()).bind(v["industry"].as_str().unwrap_or("")).fetch_all(&s.db).await?;data["history"]=json!(history);data["historical_trend_available"]=json!(data["history"].as_array().is_some_and(|x|x.len()>1));Ok(Json(data))
}

#[derive(Deserialize)]struct FreezeInput{candidate_id:String,stage:String}
async fn freeze_prediction(State(s):State<AppState>,a:Actor,Path(id):Path<String>,Json(p):Json<FreezeInput>)->Result<Json<Value>>{
 let v=own_vacancy(&s,&a,&id).await?;
 if !["vacancy","offer"].contains(&p.stage.as_str()){return Err(AppError::bad("Invalid stage"));}
 crate::security::throttle(&s,&format!("prediction:{}",a.id),30).await?;
 let mut tx=s.db.begin().await?;
 sqlx::query("SELECT pg_advisory_xact_lock(hashtextextended($1,0))").bind(format!("prediction:{id}:{}:{}",p.candidate_id,p.stage)).execute(&mut *tx).await?;
 let eligible:Option<bool>=sqlx::query_scalar("SELECT c.synthetic FROM candidates c WHERE c.id=$2 AND c.consent_processing AND (EXISTS(SELECT 1 FROM applications ap WHERE ap.vacancy_id=$1 AND ap.candidate_id=c.id AND ap.status<>'withdrawn') OR EXISTS(SELECT 1 FROM invitations i WHERE i.vacancy_id=$1 AND i.candidate_id=c.id)) AND ($3='vacancy' OR EXISTS(SELECT 1 FROM invitations i WHERE i.vacancy_id=$1 AND i.candidate_id=c.id))").bind(&id).bind(&p.candidate_id).bind(&p.stage).fetch_optional(&mut *tx).await?;
 let synthetic=eligible.ok_or_else(AppError::missing)? || a.synthetic || v["synthetic"]==true;
 let already_decided:bool=sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM intelligence.bilateral_decisions WHERE vacancy_id=$1 AND candidate_id=$2 AND stage=$3 AND (candidate_accepts IS NOT NULL OR employer_accepts IS NOT NULL))").bind(&id).bind(&p.candidate_id).bind(&p.stage).fetch_one(&mut *tx).await?;
 if already_decided{return Err(AppError::conflict("Prediction must precede both decisions"));}
 // Prediction is computed from prior completed pairs, never a caller-supplied score.
 // Reuse the transaction connection: concurrent snapshots cannot exhaust a
 // bounded pool by each holding one connection while requesting a second.
 let input:Value=sqlx::query_scalar(PAIRED_OBSERVATIONS).bind(&id).bind(&p.stage).fetch_one(&mut *tx).await?;
 let mut prediction=compute_paired(input,&p.stage).await?;
 prediction["context"]=json!({"role":v["specialization"],"grade":v["grade"]});
 let saved:Option<Value>=sqlx::query_scalar("INSERT INTO intelligence.prospective_predictions(id,owner_id,vacancy_id,candidate_id,stage,model_version,prediction,synthetic) VALUES($1,$2,$3,$4,$5,'bilateral-market-1.0.0',$6,$7) ON CONFLICT(vacancy_id,candidate_id,stage,model_version) DO NOTHING RETURNING to_jsonb(prospective_predictions)").bind(new_id("PV")).bind(&a.id).bind(&id).bind(&p.candidate_id).bind(&p.stage).bind(&prediction).bind(synthetic).fetch_optional(&mut *tx).await?;
 let saved=saved.ok_or_else(||AppError::conflict("Prediction already frozen"))?;
 sqlx::query("INSERT INTO audit_events(actor_id,action,entity_id,details) VALUES($1,'prediction.frozen',$2,$3)").bind(&a.id).bind(saved["id"].as_str()).bind(json!({"stage":p.stage,"model_version":"bilateral-market-1.0.0","synthetic":synthetic})).execute(&mut *tx).await?;
 tx.commit().await?;Ok(Json(saved))
}
#[derive(Deserialize,Default)]struct ValidationFilter{vacancy_id:Option<String>,stage:Option<String>}
async fn validation_records(s:&AppState,a:&Actor,filter:&ValidationFilter)->Result<Vec<Value>>{
 a.verified_employer(s).await?;
 if filter.stage.as_deref().is_some_and(|stage|!matches!(stage,"vacancy"|"offer")){return Err(AppError::bad("Invalid stage"));}
 let rows:Vec<Value>=sqlx::query_scalar("SELECT to_jsonb(p)||jsonb_build_object('candidate_accepts',d.candidate_accepts,'employer_accepts',d.employer_accepts,'candidate_decided_at',d.candidate_decided_at,'employer_decided_at',d.employer_decided_at) FROM intelligence.prospective_predictions p LEFT JOIN intelligence.prospective_outcomes d ON d.prediction_id=p.id WHERE p.owner_id=$1 AND ($2::text IS NULL OR p.vacancy_id=$2) AND ($3::text IS NULL OR p.stage=$3) ORDER BY p.created_at LIMIT 5001").bind(&a.id).bind(&filter.vacancy_id).bind(&filter.stage).fetch_all(&s.db).await?;
 if rows.len()>5000{return Err(AppError::conflict("Export cohort limit; define a narrower independent protocol"));}
 Ok(rows)
}
async fn forecast_validation(State(s):State<AppState>,a:Actor,Query(filter):Query<ValidationFilter>)->Result<Json<Value>>{
 let rows=validation_records(&s,&a,&filter).await?;
 if rows.len()>500{return Err(AppError::conflict("Online cohort limit: 500; filter vacancy/stage or use owned export for offline evaluation"));}
 // Compact feature projection respects the numerical service's 512 kB perimeter.
 let compact:Vec<Value>=rows.iter().map(|r|json!({"vacancy_id":r["vacancy_id"],"candidate_id":r["candidate_id"],"stage":r["stage"],"model_version":r["model_version"],"created_at":r["created_at"],"synthetic":r["synthetic"],"candidate_accepts":r["candidate_accepts"],"employer_accepts":r["employer_accepts"],"candidate_decided_at":r["candidate_decided_at"],"employer_decided_at":r["employer_decided_at"],"prediction":{"candidate_acceptance":{"mean":r["prediction"]["candidate_acceptance"]["mean"]},"employer_acceptance":{"mean":r["prediction"]["employer_acceptance"]["mean"]},"joint_point_estimate":r["prediction"]["joint_point_estimate"]}})).collect();
 let compact:Vec<Value>=compact.into_iter().zip(rows.iter()).map(|(mut item,row)|{item["prediction"]["context"]=row["prediction"]["context"].clone();item}).collect();
 Ok(Json(compute(&json!({"operation":"prospective_forecast","records":compact})).await?))
}
async fn forecast_export(State(s):State<AppState>,a:Actor,Query(filter):Query<ValidationFilter>)->Result<Json<Value>>{
 let rows=validation_records(&s,&a,&filter).await?;
 Ok(Json(json!({"version":"prospective-intentions-1.0.0","records":rows,"scope":"owned frozen predictions and subsequent explicit intentions; not employment outcomes"})))
}
