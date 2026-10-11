use crate::{
    AppState,
    auth::{Actor, new_id},
    error::{AppError, Result},
};
use axum::{
    Json,
    extract::{Multipart, Path, Query, State},
    http::{StatusCode, header},
    response::{IntoResponse, Response},
};
use serde::Deserialize;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};

#[derive(Deserialize)]
pub struct UploadQuery {
    pub kind: String,
}
async fn admit(
    tx: &mut sqlx::Transaction<'_, sqlx::Postgres>,
    user: &str,
    incoming: i64,
    new_file: bool,
) -> Result<()> {
    // All upload/export/retry admissions share one short lock across API replicas.
    sqlx::query("SELECT pg_advisory_xact_lock(7410706)")
        .execute(&mut **tx)
        .await?;
    let (queued, count, used): (i64, i64, i64) = sqlx::query_as("SELECT count(*) FILTER(WHERE status IN ('queued','processing')),count(*),coalesce(sum(bytes+result_bytes),0)::bigint FROM documents WHERE user_id=$1").bind(user).fetch_one(&mut **tx).await?;
    if queued >= 5 || new_file && count >= 100 || used + incoming > 500 * 1024 * 1024 {
        return Err(AppError(StatusCode::TOO_MANY_REQUESTS, "Лимит документов: 5 в обработке, 100 сохранённых или 500 МБ. Удалите ненужные файлы или дождитесь обработки.".into()));
    }
    let (global_queue, global_count, global_bytes): (i64, i64, i64) = sqlx::query_as("SELECT count(*) FILTER(WHERE status IN ('queued','processing')),count(*),coalesce(sum(bytes+result_bytes),0)::bigint FROM documents").fetch_one(&mut **tx).await?;
    if global_queue >= 200
        || new_file && global_count >= 2000
        || global_bytes + incoming > 2 * 1024 * 1024 * 1024
    {
        return Err(AppError(
            StatusCode::SERVICE_UNAVAILABLE,
            "Хранилище или очередь заполнены. Повторите позже.".into(),
        ));
    }
    Ok(())
}
pub async fn upload(
    State(s): State<AppState>,
    actor: Actor,
    Query(q): Query<UploadQuery>,
    mut multipart: Multipart,
) -> Result<Json<Value>> {
    if !["resume", "vacancy", "employment"].contains(&q.kind.as_str())
        || actor.role == "candidate" && !["resume", "employment"].contains(&q.kind.as_str())
        || actor.role != "candidate" && q.kind == "employment"
    {
        return Err(AppError::bad("Недопустимый тип документа для вашей роли"));
    }
    if q.kind == "employment" {
        let consent: bool =
            sqlx::query_scalar("SELECT consent_processing FROM candidates WHERE id=$1")
                .bind(&actor.subject_id)
                .fetch_one(&s.db)
                .await?;
        if !consent {
            return Err(AppError::bad(
                "Для сверки выписки нужно согласие на обработку данных",
            ));
        }
    }
    crate::security::throttle(&s, &format!("documents:{}", actor.id), 30).await?;
    let _slot = s
        .security
        .uploads
        .clone()
        .try_acquire_owned()
        .map_err(|_| {
            AppError(
                StatusCode::TOO_MANY_REQUESTS,
                "Слишком много одновременных загрузок".into(),
            )
        })?;
    let Some(field) = multipart
        .next_field()
        .await
        .map_err(|_| AppError::bad("Не удалось прочитать загрузку"))?
    else {
        return Err(AppError::bad("Выберите документ"));
    };
    let filename = field
        .file_name()
        .unwrap_or("document.pdf")
        .chars()
        .filter(|c| !c.is_control())
        .take(250)
        .collect::<String>();
    let bytes = field
        .bytes()
        .await
        .map_err(|_| AppError::bad("Файл превышает 20 МБ или повреждён"))?;
    if bytes.is_empty() {
        return Err(AppError::bad("Пустой файл"));
    }
    let extension = if bytes.starts_with(b"%PDF-") {
        "pdf"
    } else if bytes.starts_with(b"\x89PNG\r\n\x1a\n") {
        "png"
    } else if bytes.starts_with(&[0xff, 0xd8, 0xff]) {
        "jpg"
    } else {
        return Err(AppError::bad(
            "Поддерживаются PDF, PNG и JPEG. Формат определяется по содержимому.",
        ));
    };
    let hash = format!("{:x}", Sha256::digest(&bytes));
    let mut tx = s.db.begin().await?;
    admit(&mut tx, &actor.id, bytes.len() as i64, true).await?;
    if q.kind == "resume" {
        actor.require("candidate")?;
        // Locking the candidate serializes two uploads from separate browser tabs.
        sqlx::query("SELECT id FROM candidates WHERE id=$1 FOR UPDATE")
            .bind(&actor.subject_id)
            .execute(&mut *tx)
            .await?;
        let count: i64 = sqlx::query_scalar(
            "SELECT count(*) FROM resume_profiles WHERE candidate_id=$1 AND status<>'archived'",
        )
        .bind(&actor.subject_id)
        .fetch_one(&mut *tx)
        .await?;
        if count >= 3 {
            return Err(AppError::conflict(
                "Одновременно можно подготовить до трёх резюме на разные позиции",
            ));
        }
    }
    let existing:Option<Value>=sqlx::query_scalar("SELECT to_jsonb(d)-'storage_key'-'worker_id' FROM documents d WHERE user_id=$1 AND sha256=$2 AND kind=$3").bind(&actor.id).bind(&hash).bind(&q.kind).fetch_optional(&mut *tx).await?;
    if let Some(doc) = existing {
        if q.kind == "employment" {
            activate_employment(&mut tx, &actor, doc["id"].as_str().unwrap()).await?;
            tx.commit().await?;
        }
        return Ok(Json(json!({"document":doc,"duplicate":true})));
    }
    let id = new_id("D");
    let key = format!("{id}.{extension}");
    let path = s.storage.join(&key);
    tokio::fs::write(&path, &bytes).await?;
    let record=sqlx::query_scalar::<_,Value>("INSERT INTO documents(id,user_id,kind,filename,sha256,storage_key,bytes) VALUES($1,$2,$3,$4,$5,$6,$7) RETURNING to_jsonb(documents)-'storage_key'-'worker_id'")
        .bind(&id).bind(&actor.id).bind(&q.kind).bind(filename).bind(hash).bind(key).bind(bytes.len() as i64).fetch_one(&mut *tx).await;
    let doc = match record {
        Ok(doc) => doc,
        Err(e) => {
            let _ = tokio::fs::remove_file(path).await;
            return Err(e.into());
        }
    };
    if q.kind == "employment" {
        activate_employment(&mut tx, &actor, &id).await?;
    }
    if q.kind == "resume" {
        let source: Value = sqlx::query_scalar("SELECT to_jsonb(c) FROM candidates c WHERE id=$1")
            .bind(&actor.subject_id)
            .fetch_one(&mut *tx)
            .await?;
        let resume_id = new_id("R");
        let title = source["specialization"]
            .as_str()
            .filter(|x| !x.is_empty())
            .unwrap_or("ИТ-специалист");
        // A candidate who has explicitly enabled discovery and given both
        // consents expects a newly uploaded target resume to take part in it.
        // Until extraction completes it remains unavailable; the worker turns
        // this intent into `published` only after it has produced the profile.
        let visibility = if source["visibility"] == "employer_searchable"
            && source["consent_processing"] == true
            && source["consent_publication"] == true
        {
            "employer_searchable"
        } else {
            "private"
        };
        sqlx::query("INSERT INTO resume_profiles(id,candidate_id,document_id,target_position,specialization,declared_grade,experience_years,skills,about,expected_salary,work_format,visibility,status) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,'extracting')")
            .bind(&resume_id).bind(&actor.subject_id).bind(&id).bind(title).bind(source["specialization"].as_str().unwrap_or("")).bind(source["declared_grade"].as_str().unwrap_or("junior")).bind(source["experience_years"].as_f64().unwrap_or(0.)).bind(source["skills"].as_array().map(|v|v.iter().filter_map(Value::as_str).collect::<Vec<_>>()).unwrap_or_default()).bind(source["about"].as_str().unwrap_or("")).bind(source["expected_salary"].as_i64().unwrap_or(0) as i32).bind(source["work_format"].as_str().unwrap_or("удалённо")).bind(visibility).execute(&mut *tx).await?;
        sqlx::query("INSERT INTO qualification_tests(id,resume_id,status,generation_status,seed) VALUES($1,$2,'waiting_resume','waiting',md5(random()::text||clock_timestamp()::text))").bind(new_id("Q")).bind(&resume_id).execute(&mut *tx).await?;
    }
    tx.commit().await?;
    Ok(Json(json!({"document":doc,"duplicate":false})))
}
async fn activate_employment(
    tx: &mut sqlx::Transaction<'_, sqlx::Postgres>,
    actor: &Actor,
    id: &str,
) -> Result<()> {
    sqlx::query("UPDATE candidates SET employment_document_id=$2,employment_check=jsonb_build_object('status','queued','document_id',$2::text,'message','Сверяем выписку с резюме. Предыдущее ограничение, если оно было, действует до завершения сверки.') WHERE id=$1 AND consent_processing").bind(&actor.subject_id).bind(id).execute(&mut **tx).await?;
    sqlx::query("UPDATE documents SET status='queued',attempts=0,next_attempt_at=now(),progress=0,error=NULL WHERE id=$1 AND status<>'processing'").bind(id).execute(&mut **tx).await?;
    Ok(())
}
pub async fn list(State(s): State<AppState>, actor: Actor) -> Result<Json<Value>> {
    let items:Vec<Value>=sqlx::query_scalar("SELECT to_jsonb(d)-'storage_key'-'worker_id' FROM documents d WHERE user_id=$1 ORDER BY created_at DESC LIMIT 100").bind(actor.id).fetch_all(&s.db).await?;
    Ok(Json(json!({"items":items})))
}
pub async fn get(
    State(s): State<AppState>,
    actor: Actor,
    Path(id): Path<String>,
) -> Result<Json<Value>> {
    let item: Value = sqlx::query_scalar(
        "SELECT to_jsonb(d)-'storage_key'-'worker_id' FROM documents d WHERE id=$1 AND user_id=$2",
    )
    .bind(id)
    .bind(actor.id)
    .fetch_optional(&s.db)
    .await?
    .ok_or_else(AppError::missing)?;
    Ok(Json(json!({"document":item})))
}
pub async fn retry(
    State(s): State<AppState>,
    actor: Actor,
    Path(id): Path<String>,
) -> Result<Json<Value>> {
    crate::security::throttle(&s, &format!("documents:{}", actor.id), 30).await?;
    let mut tx = s.db.begin().await?;
    admit(&mut tx, &actor.id, 0, false).await?;
    let item:Value=sqlx::query_scalar("UPDATE documents SET status='queued',error=NULL,attempts=0,next_attempt_at=now(),progress=0,updated_at=now() WHERE id=$1 AND user_id=$2 AND status='failed' RETURNING to_jsonb(documents)-'storage_key'-'worker_id'").bind(id).bind(actor.id).fetch_optional(&mut *tx).await?.ok_or_else(AppError::missing)?;
    tx.commit().await?;
    Ok(Json(json!({"document":item})))
}
pub async fn original(
    State(s): State<AppState>,
    actor: Actor,
    Path(id): Path<String>,
) -> Result<Response> {
    let row: Option<(String, String, Option<Value>)> =
        sqlx::query_as("SELECT storage_key,kind,result FROM documents WHERE id=$1 AND user_id=$2")
            .bind(&id)
            .bind(actor.id)
            .fetch_optional(&s.db)
            .await?;
    let (key, kind, result) = row.ok_or_else(AppError::missing)?;
    let key = if kind == "profile_export" {
        result
            .and_then(|v| v["output_key"].as_str().map(str::to_owned))
            .ok_or_else(|| AppError::conflict("PDF ещё создаётся"))?
    } else {
        key
    };
    if key.contains('/') || key.contains('\\') || key.contains("..") {
        return Err(AppError::bad("Недопустимый путь"));
    }
    let content = tokio::fs::File::open(s.storage.join(&key)).await?;
    let stream = axum::body::Body::from_stream(tokio_util::io::ReaderStream::with_capacity(
        content,
        64 * 1024,
    ));
    let mime = if key.ends_with(".pdf") {
        "application/pdf"
    } else if key.ends_with(".png") {
        "image/png"
    } else {
        "image/jpeg"
    };
    Ok((
        [
            (header::CONTENT_TYPE, mime),
            (header::CONTENT_DISPOSITION, "attachment"),
            (header::CACHE_CONTROL, "private, no-store"),
        ],
        stream,
    )
        .into_response())
}
pub async fn export_profile(State(s): State<AppState>, actor: Actor) -> Result<Json<Value>> {
    actor.require("candidate")?;
    crate::security::throttle(&s, &format!("documents:{}", actor.id), 30).await?;
    let profile: Value = sqlx::query_scalar(
        "SELECT to_jsonb(c) FROM candidates c WHERE id=$1 AND consent_processing",
    )
    .bind(actor.subject_id)
    .fetch_optional(&s.db)
    .await?
    .ok_or_else(|| AppError::bad("Нет согласия на обработку профиля"))?;
    let raw = serde_json::to_vec(&profile).unwrap();
    let hash = format!("{:x}", Sha256::digest(&raw));
    let id = new_id("D");
    let key = format!("{id}.json");
    let mut tx = s.db.begin().await?;
    admit(&mut tx, &actor.id, raw.len() as i64, true).await?;
    tokio::fs::write(s.storage.join(&key), &raw).await?;
    let doc:Value=sqlx::query_scalar("INSERT INTO documents(id,user_id,kind,filename,sha256,storage_key,bytes) VALUES($1,$2,'profile_export','Профиль ФСП.pdf',$3,$4,$5) ON CONFLICT(user_id,sha256,kind) DO UPDATE SET updated_at=now() RETURNING to_jsonb(documents)-'storage_key'-'worker_id'")
        .bind(&id).bind(actor.id).bind(hash).bind(&key).bind(raw.len() as i64).fetch_one(&mut *tx).await?;
    if doc["id"].as_str() != Some(&id) {
        let _ = tokio::fs::remove_file(s.storage.join(key)).await;
    }
    tx.commit().await?;
    Ok(Json(json!({"document":doc})))
}

pub async fn delete(
    State(s): State<AppState>,
    actor: Actor,
    Path(id): Path<String>,
) -> Result<Json<Value>> {
    let mut tx = s.db.begin().await?;
    let row: Option<(String, String, Option<Value>)> = sqlx::query_as(
        "SELECT storage_key,status,result FROM documents WHERE id=$1 AND user_id=$2 FOR UPDATE",
    )
    .bind(&id)
    .bind(&actor.id)
    .fetch_optional(&mut *tx)
    .await?;
    let (key, status, result) = row.ok_or_else(AppError::missing)?;
    if status == "processing" {
        return Err(AppError::conflict(
            "Дождитесь завершения обработки перед удалением",
        ));
    }
    let mut keys = vec![key];
    if let Some(output) = result.and_then(|v| {
        v.get("output_key")
            .and_then(Value::as_str)
            .map(str::to_owned)
    }) {
        keys.push(output);
    }
    for key in keys {
        sqlx::query("INSERT INTO file_deletions(storage_key) VALUES($1) ON CONFLICT DO NOTHING")
            .bind(key)
            .execute(&mut *tx)
            .await?;
    }
    sqlx::query("DELETE FROM documents WHERE id=$1")
        .bind(&id)
        .execute(&mut *tx)
        .await?;
    sqlx::query("UPDATE candidates SET employment_document_id=NULL,employment_check=jsonb_build_object('status',CASE WHEN employment_blocked THEN 'source_removed' ELSE 'not_provided' END,'message',CASE WHEN employment_blocked THEN 'Выписка удалена. Выявленное расхождение не снято: исправьте резюме и загрузите актуальную выписку для повторной сверки.' ELSE 'Выписка не предоставлена; это не снижает видимость.' END) WHERE employment_document_id=$1").bind(&id).execute(&mut *tx).await?;
    sqlx::query(
        "INSERT INTO audit_events(actor_id,action,entity_id) VALUES($1,'document.deleted',$2)",
    )
    .bind(&actor.id)
    .bind(&id)
    .execute(&mut *tx)
    .await?;
    tx.commit().await?;
    Ok(Json(json!({"deleted":true})))
}
#[derive(Deserialize)]
pub struct Review {
    pub fields: Value,
    pub profile_index: Option<usize>,
}
pub async fn review(
    State(s): State<AppState>,
    actor: Actor,
    Path(id): Path<String>,
    Json(p): Json<Review>,
) -> Result<Json<Value>> {
    if !p.fields.is_object() || p.fields.to_string().len() > 50000 {
        return Err(AppError::bad("Некорректный черновик"));
    }
    // Keep each resume's corrections separate; never merge identities in a PDF bundle.
    let mut tx = s.db.begin().await?;
    let mut result:Value=sqlx::query_scalar("SELECT result FROM documents WHERE id=$1 AND user_id=$2 AND status IN ('review','completed') AND kind IN ('resume','vacancy') FOR UPDATE")
        .bind(&id).bind(&actor.id).fetch_optional(&mut *tx).await?.ok_or_else(AppError::missing)?;
    let reviewed = p.fields.clone();
    let completed = if let Some(profiles) = result.get_mut("profiles").and_then(Value::as_array_mut)
    {
        let index = p
            .profile_index
            .ok_or_else(|| AppError::bad("Выберите резюме из файла"))?;
        let profile = profiles
            .get_mut(index)
            .ok_or_else(|| AppError::bad("Резюме не найдено в файле"))?;
        profile["reviewed_fields"] = reviewed.clone();
        let completed = profiles
            .iter()
            .all(|item| item.get("reviewed_fields").is_some());
        result["reviewed_profile_index"] = json!(index);
        completed
    } else {
        if p.profile_index.is_some() {
            return Err(AppError::bad("Документ содержит одно резюме"));
        }
        result["reviewed_fields"] = reviewed.clone();
        true
    };
    if actor.role == "candidate" {
        let target = reviewed["title"].as_str().unwrap_or("").trim();
        let specialization = reviewed["specialization"]
            .as_str()
            .filter(|x| crate::matching::valid_spec(x))
            .unwrap_or("");
        let declared = reviewed["grade"].as_str().unwrap_or("");
        let skills = reviewed["skills"]
            .as_array()
            .map(|a| a.iter().filter_map(Value::as_str).collect::<Vec<_>>())
            .unwrap_or_default();
        let changed:Option<String>=sqlx::query_scalar("UPDATE resume_profiles SET target_position=CASE WHEN length($2)>=3 THEN left($2,250) ELSE target_position END,specialization=CASE WHEN $3<>'' THEN $3 ELSE specialization END,declared_grade=CASE WHEN $4 IN ('junior','middle','senior') THEN $4 ELSE declared_grade END,skills=CASE WHEN cardinality($5::text[])>0 THEN $5 ELSE skills END,status=CASE WHEN visibility='employer_searchable' THEN 'published' ELSE 'draft' END,updated_at=now(),version=version+1 WHERE document_id=$1 AND candidate_id=$6 RETURNING id")
            .bind(&id).bind(target).bind(specialization).bind(declared).bind(skills).bind(&actor.subject_id).fetch_optional(&mut *tx).await?;
        if let Some(resume_id) = changed {
            sqlx::query("UPDATE qualification_tests SET status='queued',generation_status='queued',questions='[]',score=NULL,passed=NULL,attempts=0,available_at=now(),seed=md5(random()::text||clock_timestamp()::text),error=NULL,updated_at=now() WHERE resume_id=$1 AND status NOT IN ('in_progress','passed')").bind(resume_id).execute(&mut *tx).await?;
        }
    }
    let result_bytes = result.to_string().len() as i64;
    let doc:Value=sqlx::query_scalar("UPDATE documents SET result=$3,result_bytes=$4,status=$5,updated_at=now() WHERE id=$1 AND user_id=$2 RETURNING to_jsonb(documents)-'storage_key'-'worker_id'")
        .bind(&id).bind(&actor.id).bind(result).bind(result_bytes).bind(if completed{"completed"}else{"review"}).fetch_one(&mut *tx).await?;
    tx.commit().await?;
    crate::db::audit(&s, &actor.id, "document.reviewed", &id, json!({})).await?;
    Ok(Json(json!({"document":doc})))
}
