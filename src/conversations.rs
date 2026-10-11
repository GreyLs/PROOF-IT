//! Private candidate--employer conversations.
//!
//! A thread cannot be composed by an arbitrary account: it is materialised by
//! the invitation/application transaction and every read or write joins back to
//! its candidate/company binding.
use crate::{
    AppState,
    auth::{Actor, new_id},
    error::{AppError, Result},
};
use axum::{
    Json,
    extract::{Path, Query, State},
};
use serde::Deserialize;
use serde_json::{Value, json};

fn scope_key(vacancy_id: Option<&str>, resume_id: Option<&str>) -> String {
    format!(
        "vacancy:{}|resume:{}",
        vacancy_id.unwrap_or(""),
        resume_id.unwrap_or("")
    )
}

/// Creates or finds the only thread for the exact candidate/company/vacancy/
/// resume context. Called from the transaction that creates the triggering
/// invitation or application.
pub async fn ensure_thread(
    tx: &mut sqlx::Transaction<'_, sqlx::Postgres>,
    candidate_id: &str,
    company_id: &str,
    vacancy_id: Option<&str>,
    resume_id: Option<&str>,
    origin: &str,
) -> Result<String> {
    let vacancy_title: String = if let Some(id) = vacancy_id {
        sqlx::query_scalar("SELECT title FROM vacancies WHERE id=$1")
            .bind(id)
            .fetch_optional(&mut **tx)
            .await?
            .unwrap_or_default()
    } else {
        String::new()
    };
    let resume_title: String = if let Some(id) = resume_id {
        sqlx::query_scalar("SELECT target_position FROM resume_profiles WHERE id=$1")
            .bind(id)
            .fetch_optional(&mut **tx)
            .await?
            .unwrap_or_default()
    } else {
        String::new()
    };
    let scope = scope_key(vacancy_id, resume_id);
    let id = new_id("PC");
    let thread: String = sqlx::query_scalar(
        "INSERT INTO private_conversations(id,candidate_id,company_id,vacancy_id,resume_id,scope_key,origin,vacancy_title,resume_title) \
         VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9) \
         ON CONFLICT(candidate_id,company_id,scope_key) DO UPDATE \
         SET vacancy_title=CASE WHEN private_conversations.vacancy_title='' THEN EXCLUDED.vacancy_title ELSE private_conversations.vacancy_title END, \
             resume_title=CASE WHEN private_conversations.resume_title='' THEN EXCLUDED.resume_title ELSE private_conversations.resume_title END \
         RETURNING id",
    )
    .bind(id)
    .bind(candidate_id)
    .bind(company_id)
    .bind(vacancy_id)
    .bind(resume_id)
    .bind(scope)
    .bind(origin)
    .bind(vacancy_title)
    .bind(resume_title)
    .fetch_one(&mut **tx)
    .await?;
    Ok(thread)
}

fn member_filter(actor: &Actor) -> (&str, &str) {
    if actor.role == "candidate" {
        ("candidate_id", &actor.subject_id)
    } else {
        ("company_id", &actor.subject_id)
    }
}

async fn thread_for_actor(s: &AppState, actor: &Actor, id: &str) -> Result<Value> {
    let (field, subject) = member_filter(actor);
    let query = format!(
        "SELECT to_jsonb(pc)||jsonb_build_object( \
           'other_name',CASE WHEN $2='candidate' THEN co.name ELSE ca.display_name END, \
           'other_kind',CASE WHEN $2='candidate' THEN 'company' ELSE 'candidate' END, \
           'contact_revoked',EXISTS(SELECT 1 FROM contact_revocations cr WHERE cr.candidate_id=pc.candidate_id AND cr.company_id=pc.company_id), \
           'unread_count',(SELECT count(*) FROM private_conversation_messages m WHERE m.conversation_id=pc.id AND m.sender_user_id<>$3 AND m.read_at IS NULL) \
         ) FROM private_conversations pc JOIN candidates ca ON ca.id=pc.candidate_id JOIN companies co ON co.id=pc.company_id \
         WHERE pc.id=$1 AND pc.{field}=$4"
    );
    sqlx::query_scalar(&query)
        .bind(id)
        .bind(&actor.role)
        .bind(&actor.id)
        .bind(subject)
        .fetch_optional(&s.db)
        .await?
        .ok_or_else(AppError::missing)
}

pub async fn list(State(s): State<AppState>, actor: Actor) -> Result<Json<Value>> {
    let (field, subject) = member_filter(&actor);
    let query = format!(
        "SELECT jsonb_build_object( \
           'id',pc.id,'candidate_id',pc.candidate_id,'company_id',pc.company_id,'vacancy_id',pc.vacancy_id,'resume_id',pc.resume_id, \
           'origin',pc.origin,'vacancy_title',pc.vacancy_title,'resume_title',pc.resume_title,'created_at',pc.created_at,'last_message_at',pc.last_message_at, \
           'other_name',CASE WHEN $1='candidate' THEN co.name ELSE ca.display_name END, \
           'other_kind',CASE WHEN $1='candidate' THEN 'company' ELSE 'candidate' END, \
           'contact_revoked',EXISTS(SELECT 1 FROM contact_revocations cr WHERE cr.candidate_id=pc.candidate_id AND cr.company_id=pc.company_id), \
           'unread_count',(SELECT count(*) FROM private_conversation_messages m WHERE m.conversation_id=pc.id AND m.sender_user_id<>$2 AND m.read_at IS NULL), \
           'last_message_preview',(SELECT left(m.body,140) FROM private_conversation_messages m WHERE m.conversation_id=pc.id ORDER BY m.created_at DESC,m.id DESC LIMIT 1), \
           'last_message_sender_id',(SELECT m.sender_user_id FROM private_conversation_messages m WHERE m.conversation_id=pc.id ORDER BY m.created_at DESC,m.id DESC LIMIT 1) \
         ) FROM private_conversations pc JOIN candidates ca ON ca.id=pc.candidate_id JOIN companies co ON co.id=pc.company_id \
         WHERE pc.{field}=$3 ORDER BY COALESCE(pc.last_message_at,pc.created_at) DESC,pc.id DESC LIMIT 300"
    );
    let items: Vec<Value> = sqlx::query_scalar(&query)
        .bind(&actor.role)
        .bind(&actor.id)
        .bind(subject)
        .fetch_all(&s.db)
        .await?;
    Ok(Json(json!({"items":items})))
}

#[derive(Deserialize)]
pub struct HistoryQuery {
    pub before: Option<String>,
}

pub async fn get(
    State(s): State<AppState>,
    actor: Actor,
    Path(id): Path<String>,
    Query(query): Query<HistoryQuery>,
) -> Result<Json<Value>> {
    let thread = thread_for_actor(&s, &actor, &id).await?;
    let before = query.before.unwrap_or_default();
    let messages: Vec<Value> = sqlx::query_scalar(
        "SELECT to_jsonb(m) FROM ( \
           SELECT id,conversation_id,sender_user_id,body,created_at,read_at \
           FROM private_conversation_messages \
           WHERE conversation_id=$1 AND ($2='' OR (created_at,id)<(SELECT created_at,id FROM private_conversation_messages WHERE id=$2 AND conversation_id=$1)) \
           ORDER BY created_at DESC,id DESC LIMIT 100 \
         ) m ORDER BY created_at,id",
    )
    .bind(&id)
    .bind(before)
    .fetch_all(&s.db)
    .await?;
    Ok(Json(json!({"conversation":thread,"messages":messages})))
}

#[derive(Deserialize)]
pub struct MessageInput {
    pub body: String,
}

pub async fn message(
    State(s): State<AppState>,
    actor: Actor,
    Path(id): Path<String>,
    Json(input): Json<MessageInput>,
) -> Result<Json<Value>> {
    let body = input.body.trim();
    if body.is_empty()
        || body.chars().count() > 4000
        || body
            .chars()
            .any(|c| c == '\0' || (c.is_control() && c != '\n' && c != '\r' && c != '\t'))
    {
        return Err(AppError::bad(
            "Сообщение должно содержать от 1 до 4 000 допустимых символов",
        ));
    }
    crate::security::throttle(
        &s,
        &format!("private-conversation-message:{}", actor.id),
        80,
    )
    .await?;
    let _thread = thread_for_actor(&s, &actor, &id).await?;
    let mut tx = s.db.begin().await?;
    let item: Value = sqlx::query_scalar(
        "INSERT INTO private_conversation_messages(id,conversation_id,sender_user_id,body) VALUES($1,$2,$3,$4) \
         RETURNING to_jsonb(private_conversation_messages)",
    )
    .bind(new_id("PCM"))
    .bind(&id)
    .bind(&actor.id)
    .bind(body)
    .fetch_one(&mut *tx)
    .await?;
    sqlx::query("UPDATE private_conversations SET last_message_at=now() WHERE id=$1")
        .bind(&id)
        .execute(&mut *tx)
        .await?;
    sqlx::query("INSERT INTO audit_events(actor_id,action,entity_id,details) VALUES($1,'private_conversation.message_sent',$2,$3)")
        .bind(&actor.id)
        .bind(&id)
        .bind(json!({"message_id":item["id"]}))
        .execute(&mut *tx)
        .await?;
    tx.commit().await?;
    Ok(Json(json!({"message":item})))
}

pub async fn mark_read(
    State(s): State<AppState>,
    actor: Actor,
    Path(id): Path<String>,
) -> Result<Json<Value>> {
    let _thread = thread_for_actor(&s, &actor, &id).await?;
    let changed = sqlx::query(
        "UPDATE private_conversation_messages SET read_at=now() \
         WHERE conversation_id=$1 AND sender_user_id<>$2 AND read_at IS NULL",
    )
    .bind(&id)
    .bind(&actor.id)
    .execute(&s.db)
    .await?
    .rows_affected();
    Ok(Json(json!({"marked":changed})))
}
