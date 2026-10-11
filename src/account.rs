use crate::{
    AppState,
    auth::Actor,
    error::{AppError, Result},
};
use axum::{Json, extract::State, http::StatusCode};
use serde::Deserialize;
use serde_json::{Value, json};

pub async fn export(State(s): State<AppState>, actor: Actor) -> Result<Json<Value>> {
    let table = if actor.role == "candidate" {
        "candidates"
    } else {
        "companies"
    };
    let profile: Value =
        sqlx::query_scalar(&format!("SELECT to_jsonb(p) FROM {table} p WHERE id=$1"))
            .bind(&actor.subject_id)
            .fetch_one(&s.db)
            .await?;
    crate::security::throttle(&s, &format!("account-export:{}", actor.id), 5).await?;
    let documents: Vec<Value>=sqlx::query_scalar("SELECT to_jsonb(d)-'storage_key'-'worker_id'-'result' FROM documents d WHERE user_id=$1 ORDER BY created_at").bind(&actor.id).fetch_all(&s.db).await?;
    let events: Vec<Value>=sqlx::query_scalar("SELECT to_jsonb(a) FROM audit_events a WHERE actor_id=$1 ORDER BY created_at DESC LIMIT 1000").bind(&actor.id).fetch_all(&s.db).await?;
    let dialogues: Vec<Value> = sqlx::query_scalar(
        "SELECT to_jsonb(d) FROM expert_dialogues d WHERE candidate_id=$1 ORDER BY created_at",
    )
    .bind(&actor.subject_id)
    .fetch_all(&s.db)
    .await?;
    let conversations: Vec<Value> = sqlx::query_scalar(
        "SELECT jsonb_build_object('conversation',to_jsonb(pc),'messages',coalesce((SELECT jsonb_agg(to_jsonb(m) ORDER BY m.created_at,m.id) FROM private_conversation_messages m WHERE m.conversation_id=pc.id),'[]'::jsonb)) FROM private_conversations pc WHERE (pc.candidate_id=$1 AND $2='candidate') OR (pc.company_id=$1 AND $2='employer') ORDER BY pc.created_at",
    )
    .bind(&actor.subject_id)
    .bind(&actor.role)
    .fetch_all(&s.db)
    .await?;
    // Export is not a paginated inbox: include all owned new records, while
    // never exporting the server's hidden test/reference contract.
    let career_items: Vec<Value> = if actor.role == "candidate" {
        sqlx::query_scalar(
            "SELECT to_jsonb(m) FROM career_messages m WHERE candidate_id=$1 ORDER BY id",
        )
        .bind(&actor.subject_id)
        .fetch_all(&s.db)
        .await?
    } else {
        Vec::new()
    };
    let task_items: Vec<Value> = sqlx::query_scalar("SELECT to_jsonb(t)-'contract' FROM micro_tasks t WHERE (candidate_id=$1 AND $2='candidate') OR (company_id=$1 AND $2='employer') ORDER BY created_at,id")
        .bind(&actor.subject_id).bind(&actor.role).fetch_all(&s.db).await?;
    let notification_items: Vec<Value> = sqlx::query_scalar(
        "SELECT to_jsonb(n) FROM notifications n WHERE user_id=$1 ORDER BY created_at,id",
    )
    .bind(&actor.id)
    .fetch_all(&s.db)
    .await?;
    let career = json!({"items":career_items});
    let tasks = json!({"items":task_items});
    let notifications = json!({"items":notification_items});
    let intelligence = crate::intelligence::export_owned(&s, &actor.id).await?;
    let research_lab = crate::research_lab::export_owned(&s, &actor.id).await?;
    Ok(Json(
        json!({"account":actor,"profile":profile,"documents":documents,"dialogues":dialogues,"conversations":conversations,"career_consultant":career,"practical_tasks":tasks,"notifications":notifications,"intelligence":intelligence,"research_lab":research_lab,"security_events":events,"exported_at":chrono::Utc::now()}),
    ))
}
pub async fn grants(State(s): State<AppState>, actor: Actor) -> Result<Json<Value>> {
    actor.require("candidate")?;
    let items: Vec<Value>=sqlx::query_scalar("SELECT jsonb_build_object('company_id',c.id,'company_name',c.name,'revoked',EXISTS(SELECT 1 FROM contact_revocations r WHERE r.candidate_id=$1 AND r.company_id=c.id)) FROM companies c WHERE EXISTS(SELECT 1 FROM invitations i WHERE i.candidate_id=$1 AND i.company_id=c.id AND i.status='accepted') OR EXISTS(SELECT 1 FROM applications a JOIN vacancies v ON v.id=a.vacancy_id WHERE a.candidate_id=$1 AND v.company_id=c.id AND a.status<>'withdrawn') ORDER BY c.id LIMIT 300").bind(&actor.subject_id).fetch_all(&s.db).await?;
    Ok(Json(json!({"items":items})))
}
#[derive(Deserialize)]
pub struct Revoke {
    company_id: String,
    restore: Option<bool>,
}
pub async fn revoke(
    State(s): State<AppState>,
    actor: Actor,
    Json(input): Json<Revoke>,
) -> Result<Json<Value>> {
    actor.require("candidate")?;
    let mut tx = s.db.begin().await?;
    let exists: bool = sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM invitations WHERE company_id=$1 AND candidate_id=$2 AND status='accepted') OR EXISTS(SELECT 1 FROM applications a JOIN vacancies v ON v.id=a.vacancy_id WHERE v.company_id=$1 AND a.candidate_id=$2 AND a.status<>'withdrawn')")
        .bind(&input.company_id)
        .bind(&actor.subject_id)
        .fetch_one(&mut *tx)
        .await?;
    if !exists {
        return Err(AppError::missing());
    }
    let restore = input.restore.unwrap_or(false);
    let statement = if restore {
        "DELETE FROM contact_revocations WHERE candidate_id=$1 AND company_id=$2"
    } else {
        "INSERT INTO contact_revocations(candidate_id,company_id) VALUES($1,$2) ON CONFLICT DO NOTHING"
    };
    sqlx::query(statement)
        .bind(&actor.subject_id)
        .bind(&input.company_id)
        .execute(&mut *tx)
        .await?;
    sqlx::query("INSERT INTO audit_events(actor_id,action,entity_id,details) VALUES($1,$2,$3,$4)")
        .bind(&actor.id)
        .bind(if restore {
            "contacts.restored"
        } else {
            "contacts.revoked"
        })
        .bind(&actor.subject_id)
        .bind(json!({"company_id":input.company_id}))
        .execute(&mut *tx)
        .await?;
    tx.commit().await?;
    Ok(Json(json!({"revoked":!restore})))
}
#[derive(Deserialize)]
pub struct Password {
    password: String,
}
pub async fn delete(
    State(s): State<AppState>,
    actor: Actor,
    Json(input): Json<Password>,
) -> Result<Json<Value>> {
    let guest: bool = sqlx::query_scalar("SELECT is_guest FROM users WHERE id=$1")
        .bind(&actor.id)
        .fetch_one(&s.db)
        .await?;
    if actor.synthetic && !guest {
        return Err(AppError::forbidden());
    }
    if input.password.len() > 1024 {
        return Err(AppError::bad("Некорректный пароль"));
    }
    let hash: String = sqlx::query_scalar("SELECT password_hash FROM users WHERE id=$1")
        .bind(&actor.id)
        .fetch_one(&s.db)
        .await?;
    let checked_hash = hash.clone();
    let slot = s
        .auth_slots
        .clone()
        .try_acquire_owned()
        .map_err(|_| AppError(StatusCode::TOO_MANY_REQUESTS, "Повторите позже".into()))?;
    let valid = tokio::task::spawn_blocking(move || {
        use argon2::{Argon2, PasswordHash, PasswordVerifier};
        let _slot = slot;
        PasswordHash::new(&checked_hash).is_ok_and(|h| {
            Argon2::default()
                .verify_password(input.password.as_bytes(), &h)
                .is_ok()
        })
    })
    .await
    .unwrap_or(false);
    if !valid && !(guest && s.demo) {
        return Err(AppError(StatusCode::UNAUTHORIZED, "Неверный пароль".into()));
    }
    let mut tx = s.db.begin().await?;
    let current: String =
        sqlx::query_scalar("SELECT password_hash FROM users WHERE id=$1 FOR UPDATE")
            .bind(&actor.id)
            .fetch_one(&mut *tx)
            .await?;
    if current != hash {
        return Err(AppError::conflict("Учётные данные изменились"));
    }
    sqlx::query("SELECT id FROM documents WHERE user_id=$1 FOR UPDATE")
        .bind(&actor.id)
        .execute(&mut *tx)
        .await?;
    let active: bool = sqlx::query_scalar(
        "SELECT EXISTS(SELECT 1 FROM documents WHERE user_id=$1 AND status='processing')",
    )
    .bind(&actor.id)
    .fetch_one(&mut *tx)
    .await?;
    if active {
        return Err(AppError::conflict(
            "Дождитесь завершения обработки документов",
        ));
    }
    sqlx::query("INSERT INTO file_deletions(storage_key) SELECT storage_key FROM documents WHERE user_id=$1 UNION SELECT result->>'output_key' FROM documents WHERE user_id=$1 AND result->>'output_key' IS NOT NULL ON CONFLICT DO NOTHING").bind(&actor.id).execute(&mut *tx).await?;
    sqlx::query("DELETE FROM documents WHERE user_id=$1")
        .bind(&actor.id)
        .execute(&mut *tx)
        .await?;
    let queries: &[&str] = if actor.role == "candidate" {
        &[
            "DELETE FROM invitations WHERE candidate_id=$1",
            "DELETE FROM applications WHERE candidate_id=$1",
            "DELETE FROM micro_tasks WHERE candidate_id=$1",
            "DELETE FROM assessments WHERE candidate_id=$1",
            "DELETE FROM candidates WHERE id=$1",
        ]
    } else {
        &[
            "DELETE FROM invitations WHERE company_id=$1",
            "DELETE FROM micro_tasks WHERE company_id=$1",
            "DELETE FROM applications WHERE vacancy_id IN(SELECT id FROM vacancies WHERE company_id=$1)",
            "DELETE FROM saved_searches WHERE company_id=$1",
            "DELETE FROM vacancies WHERE company_id=$1",
            "DELETE FROM companies WHERE id=$1",
        ]
    };
    for query in queries {
        sqlx::query(query)
            .bind(&actor.subject_id)
            .execute(&mut *tx)
            .await?;
    }
    sqlx::query("DELETE FROM mail_outbox WHERE recipient=$1")
        .bind(&actor.email)
        .execute(&mut *tx)
        .await?;
    sqlx::query("DELETE FROM users WHERE id=$1")
        .bind(&actor.id)
        .execute(&mut *tx)
        .await?;
    sqlx::query(
        "INSERT INTO audit_events(actor_id,action,entity_id) VALUES($1,'account.deleted',$1)",
    )
    .bind(&actor.id)
    .execute(&mut *tx)
    .await?;
    tx.commit().await?;
    Ok(Json(
        json!({"deleted":true,"message":"Аккаунт удалён. Файлы поставлены в очередь физического удаления."}),
    ))
}
