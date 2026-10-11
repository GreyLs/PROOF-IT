//! Optional Talantix connector.
//!
//! The connector intentionally owns no candidate data at rest: the delivery queue
//! contains only local identifiers.  Contact data is read at dispatch time after a
//! candidate has explicitly allowed the hand-off, and provider credentials are
//! AES-256-GCM envelopes bound to the employer id and token purpose.
use crate::{
    AppState,
    auth::{Actor, new_id},
    error::{AppError, Result},
};
use aes_gcm::{
    Aes256Gcm, KeyInit, Nonce,
    aead::{Aead, Payload},
};
use axum::{
    Json,
    extract::{Path, State},
    http::StatusCode,
};
use chrono::{DateTime, Duration, Utc};
use rand::RngCore;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use sqlx::FromRow;
use std::time::Duration as StdDuration;

const PROVIDER: &str = "talantix";
const API_DEFAULT: &str = "https://api.talantix.ru";
const ACCESS_REFRESH_MARGIN: i64 = 60;

#[derive(Deserialize)]
pub struct ConnectInput {
    pub access_token: String,
    pub refresh_token: Option<String>,
    pub expires_in: Option<i64>,
    pub refresh_token_expires_in: Option<i64>,
}

#[derive(Deserialize)]
pub struct SourceInput {
    pub source_id: i64,
}

#[derive(Deserialize)]
pub struct VacancyMappingInput {
    pub external_vacancy_id: i64,
}

#[derive(FromRow)]
struct ConnectionSecrets {
    encrypted_access_token: Vec<u8>,
    encrypted_refresh_token: Option<Vec<u8>>,
    access_expires_at: DateTime<Utc>,
    refresh_expires_at: Option<DateTime<Utc>>,
}

#[derive(Deserialize)]
struct RefreshResponse {
    access_token: String,
    refresh_token: String,
    expires_in: i64,
    refresh_token_expires_in: i64,
}

#[derive(Serialize)]
struct GraphqlRequest<'a> {
    query: &'a str,
}

fn upstream(message: &str) -> AppError {
    AppError(StatusCode::BAD_GATEWAY, message.into())
}

fn reauthorize() -> AppError {
    AppError::conflict("Срок доступа Talantix истёк. Подключите интеграцию заново.")
}

fn decode_hex_key(encoded: &str, name: &str) -> anyhow::Result<[u8; 32]> {
    anyhow::ensure!(
        encoded.len() == 64 && encoded.is_ascii(),
        "{name} must be 64 hexadecimal characters"
    );
    let mut key = [0u8; 32];
    for (index, part) in key.iter_mut().enumerate() {
        *part = u8::from_str_radix(&encoded[index * 2..index * 2 + 2], 16)?;
    }
    Ok(key)
}

fn encryption_key() -> anyhow::Result<[u8; 32]> {
    // Development may reuse the local mail key so an unused connector does not
    // complicate the stand; production requires its own key in `validate_config`.
    let (encoded, name) = match crate::config::secret("INTEGRATION_ENCRYPTION_KEY") {
        Ok(value) => (value, "INTEGRATION_ENCRYPTION_KEY"),
        Err(_) => match crate::config::secret("MAIL_ENCRYPTION_KEY") {
            Ok(value) => (value, "MAIL_ENCRYPTION_KEY"),
            Err(_) if std::env::var("FSP_ENV").as_deref() != Ok("production") => {
                (development_key()?, "development integration key")
            }
            Err(error) => return Err(error),
        },
    };
    let master = decode_hex_key(&encoded, name)?;
    let mut hasher = Sha256::new();
    hasher.update(master);
    hasher.update(b"fsp-trajectory/talantix-connector/v1");
    Ok(hasher.finalize().into())
}

fn development_key() -> anyhow::Result<String> {
    use std::io::Write;
    let path = std::path::Path::new("runtime/integration-encryption.key");
    if let Ok(value) = std::fs::read_to_string(path) {
        return Ok(value.trim().to_owned());
    }
    std::fs::create_dir_all("runtime")?;
    let mut bytes = [0u8; 32];
    rand::rngs::OsRng.fill_bytes(&mut bytes);
    let generated = bytes.iter().map(|v| format!("{v:02x}")).collect::<String>();
    match std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)
    {
        Ok(mut file) => {
            file.write_all(generated.as_bytes())?;
            file.sync_all()?;
            Ok(generated)
        }
        Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
            Ok(std::fs::read_to_string(path)?.trim().to_owned())
        }
        Err(error) => Err(error.into()),
    }
}

fn cipher() -> anyhow::Result<Aes256Gcm> {
    let key = encryption_key()?;
    Aes256Gcm::new_from_slice(&key).map_err(|_| anyhow::anyhow!("Invalid integration key"))
}

pub fn validate_config(production: bool) -> anyhow::Result<()> {
    if production {
        let encoded = crate::config::secret("INTEGRATION_ENCRYPTION_KEY")?;
        let _ = decode_hex_key(&encoded, "INTEGRATION_ENCRYPTION_KEY")?;
    } else {
        let _ = encryption_key()?;
    }
    Ok(())
}

fn aad(company_id: &str, purpose: &str) -> Vec<u8> {
    format!("{PROVIDER}\0{company_id}\0{purpose}").into_bytes()
}

fn encrypt(company_id: &str, purpose: &str, plain: &str) -> anyhow::Result<Vec<u8>> {
    let mut nonce = [0u8; 12];
    rand::rngs::OsRng.fill_bytes(&mut nonce);
    let encrypted = cipher()?
        .encrypt(
            Nonce::from_slice(&nonce),
            Payload {
                msg: plain.as_bytes(),
                aad: &aad(company_id, purpose),
            },
        )
        .map_err(|_| anyhow::anyhow!("Integration encryption failed"))?;
    Ok([nonce.to_vec(), encrypted].concat())
}

fn decrypt(company_id: &str, purpose: &str, data: &[u8]) -> anyhow::Result<String> {
    anyhow::ensure!(data.len() > 28, "Invalid integration envelope");
    let plain = cipher()?
        .decrypt(
            Nonce::from_slice(&data[..12]),
            Payload {
                msg: &data[12..],
                aad: &aad(company_id, purpose),
            },
        )
        .map_err(|_| anyhow::anyhow!("Integration authentication failed"))?;
    Ok(String::from_utf8(plain)?)
}

fn api_base(s: &AppState) -> Result<reqwest::Url> {
    let configured = std::env::var("TALANTIX_API_BASE").unwrap_or_else(|_| API_DEFAULT.into());
    let url = reqwest::Url::parse(configured.trim())
        .map_err(|_| AppError::bad("Некорректный адрес Talantix"))?;
    let production_ok = url.scheme() == "https"
        && url.host_str() == Some("api.talantix.ru")
        && url.port().is_none()
        && url.path() == "/"
        && url.query().is_none()
        && url.fragment().is_none();
    let local_mock = !s.security.production
        && matches!(url.host_str(), Some("127.0.0.1" | "localhost"))
        && matches!(url.scheme(), "http" | "https")
        && url.username().is_empty()
        && url.password().is_none()
        && url.query().is_none()
        && url.fragment().is_none();
    if !(production_ok || local_mock) {
        return Err(AppError::bad(
            "Адрес Talantix не разрешён политикой безопасности",
        ));
    }
    Ok(url)
}

fn client() -> Result<reqwest::Client> {
    reqwest::Client::builder()
        .connect_timeout(StdDuration::from_secs(5))
        .timeout(StdDuration::from_secs(15))
        .redirect(reqwest::redirect::Policy::none())
        .user_agent("FSP-Trajectory/0.1 Talantix connector")
        .build()
        .map_err(|_| upstream("Не удалось подготовить соединение с Talantix"))
}

async fn auth_check(s: &AppState, token: &str) -> Result<()> {
    let base = api_base(s)?;
    let url = base
        .join("auth_check")
        .map_err(|_| upstream("Talantix недоступен"))?;
    let response = client()?
        .get(url)
        .bearer_auth(token)
        .send()
        .await
        .map_err(|error| {
            tracing::warn!(
                timeout = error.is_timeout(),
                "talantix_auth_check_transport_error"
            );
            upstream("Talantix не ответил на проверку подключения")
        })?;
    if response.status() == StatusCode::NO_CONTENT {
        return Ok(());
    }
    if response.status().is_client_error() {
        return Err(AppError::bad("Talantix не принял токен доступа"));
    }
    tracing::warn!(status=%response.status(), "talantix_auth_check_failed");
    Err(upstream("Talantix временно не подтвердил подключение"))
}

async fn graphql(s: &AppState, token: &str, query: &str) -> Result<Value> {
    let base = api_base(s)?;
    let url = base
        .join("graphql")
        .map_err(|_| upstream("Talantix недоступен"))?;
    let response = client()?
        .post(url)
        .bearer_auth(token)
        .json(&GraphqlRequest { query })
        .send()
        .await
        .map_err(|error| {
            tracing::warn!(
                timeout = error.is_timeout(),
                "talantix_graphql_transport_error"
            );
            upstream("Talantix не ответил")
        })?;
    let status = response.status();
    if !status.is_success() {
        if status == StatusCode::UNAUTHORIZED {
            return Err(reauthorize());
        }
        tracing::warn!(%status, "talantix_graphql_http_error");
        return Err(upstream("Talantix временно недоступен"));
    }
    let body: Value = response
        .json()
        .await
        .map_err(|_| upstream("Talantix вернул некорректный ответ"))?;
    if body.get("errors").is_some() {
        tracing::warn!("talantix_graphql_application_error");
        return Err(upstream(
            "Talantix отклонил запрос. Проверьте права токена и данные.",
        ));
    }
    body.get("data")
        .cloned()
        .ok_or_else(|| upstream("Talantix не вернул данные"))
}

async fn refresh(s: &AppState, refresh_token: &str) -> Result<RefreshResponse> {
    let base = api_base(s)?;
    let url = base
        .join("oauth/token")
        .map_err(|_| upstream("Talantix недоступен"))?;
    let response = client()?
        .post(url)
        .form(&[
            ("grant_type", "refresh_token"),
            ("refresh_token", refresh_token),
        ])
        .send()
        .await
        .map_err(|error| {
            tracing::warn!(
                timeout = error.is_timeout(),
                "talantix_refresh_transport_error"
            );
            upstream("Talantix не ответил при обновлении доступа")
        })?;
    if !response.status().is_success() {
        tracing::warn!(status=%response.status(), "talantix_refresh_failed");
        return Err(reauthorize());
    }
    let value: RefreshResponse = response.json().await.map_err(|_| reauthorize())?;
    if value.access_token.len() < 20
        || value.refresh_token.len() < 20
        || !(60..=172_800).contains(&value.expires_in)
        || !(60..=31_536_000).contains(&value.refresh_token_expires_in)
    {
        return Err(reauthorize());
    }
    Ok(value)
}

async fn current_access_token(s: &AppState, company_id: &str) -> Result<String> {
    let mut tx = s.db.begin().await?;
    let connection: Option<ConnectionSecrets> = sqlx::query_as(
        "SELECT encrypted_access_token,encrypted_refresh_token,access_expires_at,refresh_expires_at FROM ats_connections WHERE company_id=$1 AND provider='talantix' AND status='connected' FOR UPDATE",
    )
    .bind(company_id)
    .fetch_optional(&mut *tx)
    .await?;
    let Some(connection) = connection else {
        return Err(AppError::conflict("Сначала подключите Talantix."));
    };
    if connection.access_expires_at > Utc::now() + Duration::seconds(ACCESS_REFRESH_MARGIN) {
        let token = decrypt(company_id, "access", &connection.encrypted_access_token)
            .map_err(|_| reauthorize())?;
        tx.commit().await?;
        return Ok(token);
    }
    let Some(encrypted_refresh) = connection.encrypted_refresh_token else {
        sqlx::query("UPDATE ats_connections SET status='reauthorize',last_error_code='access_expired',updated_at=now() WHERE company_id=$1")
            .bind(company_id).execute(&mut *tx).await?;
        tx.commit().await?;
        return Err(reauthorize());
    };
    if connection
        .refresh_expires_at
        .is_some_and(|expires| expires <= Utc::now())
    {
        sqlx::query("UPDATE ats_connections SET status='reauthorize',last_error_code='refresh_expired',updated_at=now() WHERE company_id=$1")
            .bind(company_id).execute(&mut *tx).await?;
        tx.commit().await?;
        return Err(reauthorize());
    }
    let old_refresh =
        decrypt(company_id, "refresh", &encrypted_refresh).map_err(|_| reauthorize())?;
    let refreshed = match refresh(s, &old_refresh).await {
        Ok(value) => value,
        Err(error) => {
            sqlx::query("UPDATE ats_connections SET status='reauthorize',last_error_code='refresh_failed',updated_at=now() WHERE company_id=$1")
                .bind(company_id).execute(&mut *tx).await?;
            tx.commit().await?;
            return Err(error);
        }
    };
    let access = encrypt(company_id, "access", &refreshed.access_token)
        .map_err(|_| upstream("Защищённое хранилище интеграции недоступно"))?;
    let refresh_value = encrypt(company_id, "refresh", &refreshed.refresh_token)
        .map_err(|_| upstream("Защищённое хранилище интеграции недоступно"))?;
    sqlx::query("UPDATE ats_connections SET encrypted_access_token=$2,encrypted_refresh_token=$3,access_expires_at=now()+($4::text||' seconds')::interval,refresh_expires_at=now()+($5::text||' seconds')::interval,last_error_code=NULL,updated_at=now() WHERE company_id=$1")
        .bind(company_id).bind(access).bind(refresh_value).bind(refreshed.expires_in).bind(refreshed.refresh_token_expires_in).execute(&mut *tx).await?;
    tx.commit().await?;
    Ok(refreshed.access_token)
}

async fn connection_json(s: &AppState, company_id: &str) -> Result<Value> {
    let connection: Option<Value> = sqlx::query_scalar(
        "SELECT jsonb_build_object('provider','talantix','connected',status='connected','ready',status='connected' AND source_id IS NOT NULL,'status',status,'source_id',source_id,'access_expires_at',access_expires_at,'last_checked_at',last_checked_at,'last_error_code',last_error_code,'mapped_vacancies',(SELECT count(*) FROM ats_vacancy_mappings m WHERE m.company_id=c.company_id),'outbox',(SELECT coalesce(jsonb_object_agg(status,count),'{}'::jsonb) FROM (SELECT status,count(*) FROM ats_outbox o WHERE o.company_id=c.company_id GROUP BY status) q)) FROM ats_connections c WHERE company_id=$1",
    )
    .bind(company_id)
    .fetch_optional(&s.db)
    .await?;
    Ok(connection.unwrap_or_else(|| json!({"provider":"talantix","connected":false,"ready":false,"status":"not_connected","mapped_vacancies":0,"outbox":{}})))
}

pub async fn status(State(s): State<AppState>, actor: Actor) -> Result<Json<Value>> {
    actor.verified_employer(&s).await?;
    Ok(Json(
        json!({"connection":connection_json(&s,&actor.subject_id).await?}),
    ))
}

pub async fn connect(
    State(s): State<AppState>,
    actor: Actor,
    Json(input): Json<ConnectInput>,
) -> Result<Json<Value>> {
    actor.verified_employer(&s).await?;
    let access = input.access_token.trim();
    let refresh_token = input
        .refresh_token
        .as_deref()
        .map(str::trim)
        .filter(|v| !v.is_empty());
    let access_ttl = input.expires_in.unwrap_or(86_400);
    let refresh_ttl = input.refresh_token_expires_in.unwrap_or(10_368_000);
    if !(20..=4096).contains(&access.len())
        || refresh_token.is_some_and(|token| !(20..=4096).contains(&token.len()))
        || !(60..=172_800).contains(&access_ttl)
        || refresh_token.is_some() && !(60..=31_536_000).contains(&refresh_ttl)
    {
        return Err(AppError::bad(
            "Проверьте токены и срок их действия из файла Talantix.",
        ));
    }
    auth_check(&s, access).await?;
    let encrypted_access = encrypt(&actor.subject_id, "access", access)
        .map_err(|_| upstream("Защищённое хранилище интеграции недоступно"))?;
    let encrypted_refresh = refresh_token
        .map(|token| encrypt(&actor.subject_id, "refresh", token))
        .transpose()
        .map_err(|_| upstream("Защищённое хранилище интеграции недоступно"))?;
    sqlx::query("INSERT INTO ats_connections(company_id,encrypted_access_token,encrypted_refresh_token,access_expires_at,refresh_expires_at,last_checked_at,last_error_code) VALUES($1,$2,$3,now()+($4::text||' seconds')::interval,CASE WHEN $3 IS NULL THEN NULL ELSE now()+($5::text||' seconds')::interval END,now(),NULL) ON CONFLICT(company_id) DO UPDATE SET encrypted_access_token=EXCLUDED.encrypted_access_token,encrypted_refresh_token=EXCLUDED.encrypted_refresh_token,access_expires_at=EXCLUDED.access_expires_at,refresh_expires_at=EXCLUDED.refresh_expires_at,status='connected',last_checked_at=now(),last_error_code=NULL,updated_at=now()")
        .bind(&actor.subject_id).bind(encrypted_access).bind(encrypted_refresh).bind(access_ttl).bind(refresh_ttl).execute(&s.db).await?;
    crate::db::audit(
        &s,
        &actor.id,
        "ats.talantix.connected",
        &actor.subject_id,
        json!({"refresh_available":refresh_token.is_some()}),
    )
    .await?;
    Ok(Json(
        json!({"connection":connection_json(&s,&actor.subject_id).await?}),
    ))
}

pub async fn disconnect(State(s): State<AppState>, actor: Actor) -> Result<Json<Value>> {
    actor.verified_employer(&s).await?;
    let mut tx = s.db.begin().await?;
    sqlx::query("UPDATE ats_outbox SET status='cancelled',updated_at=now(),last_error_code='connection_removed' WHERE company_id=$1 AND status IN ('queued','processing')")
        .bind(&actor.subject_id).execute(&mut *tx).await?;
    sqlx::query("DELETE FROM ats_connections WHERE company_id=$1")
        .bind(&actor.subject_id)
        .execute(&mut *tx)
        .await?;
    sqlx::query("INSERT INTO audit_events(actor_id,action,entity_id,details) VALUES($1,'ats.talantix.disconnected',$2,'{}')")
        .bind(&actor.id).bind(&actor.subject_id).execute(&mut *tx).await?;
    tx.commit().await?;
    Ok(Json(
        json!({"connection":connection_json(&s,&actor.subject_id).await?}),
    ))
}

pub async fn catalogue(State(s): State<AppState>, actor: Actor) -> Result<Json<Value>> {
    actor.verified_employer(&s).await?;
    let token = current_access_token(&s, &actor.subject_id).await?;
    let sources = graphql(&s, &token, "query PersonSources { personSources { items { id name } pageInfo { endCursor hasNextPage } } }").await?;
    let vacancies = graphql(&s, &token, "query VacancyList { vacancies(first: 100) { items { id title department createdAt status salary { currency from to } } pageInfo { endCursor hasNextPage } } }").await?;
    sqlx::query("UPDATE ats_connections SET last_checked_at=now(),last_error_code=NULL,updated_at=now() WHERE company_id=$1")
        .bind(&actor.subject_id).execute(&s.db).await?;
    let mappings: Vec<Value> = sqlx::query_scalar("SELECT jsonb_build_object('vacancy_id',vacancy_id,'external_vacancy_id',external_vacancy_id) FROM ats_vacancy_mappings WHERE company_id=$1")
        .bind(&actor.subject_id).fetch_all(&s.db).await?;
    Ok(Json(json!({
        "sources":sources.pointer("/personSources/items").cloned().unwrap_or_else(||json!([])),
        "vacancies":vacancies.pointer("/vacancies/items").cloned().unwrap_or_else(||json!([])),
        "mappings":mappings
    })))
}

pub async fn set_source(
    State(s): State<AppState>,
    actor: Actor,
    Json(input): Json<SourceInput>,
) -> Result<Json<Value>> {
    actor.verified_employer(&s).await?;
    if input.source_id <= 0 {
        return Err(AppError::bad(
            "Источник Talantix должен быть положительным числом.",
        ));
    }
    let updated = sqlx::query("UPDATE ats_connections SET source_id=$2,updated_at=now() WHERE company_id=$1 AND status='connected'")
        .bind(&actor.subject_id).bind(input.source_id).execute(&s.db).await?;
    if updated.rows_affected() != 1 {
        return Err(AppError::conflict("Сначала подключите Talantix."));
    }
    crate::db::audit(
        &s,
        &actor.id,
        "ats.talantix.source_selected",
        &actor.subject_id,
        json!({"source_id":input.source_id}),
    )
    .await?;
    Ok(Json(
        json!({"connection":connection_json(&s,&actor.subject_id).await?}),
    ))
}

pub async fn map_vacancy(
    State(s): State<AppState>,
    actor: Actor,
    Path(vacancy_id): Path<String>,
    Json(input): Json<VacancyMappingInput>,
) -> Result<Json<Value>> {
    actor.verified_employer(&s).await?;
    if input.external_vacancy_id <= 0 {
        return Err(AppError::bad(
            "Идентификатор вакансии Talantix должен быть положительным числом.",
        ));
    }
    let ready: bool = sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM ats_connections WHERE company_id=$1 AND status='connected' AND source_id IS NOT NULL)").bind(&actor.subject_id).fetch_one(&s.db).await?;
    if !ready {
        return Err(AppError::conflict(
            "Подключите Talantix и выберите источник кандидатов.",
        ));
    }
    let own: bool =
        sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM vacancies WHERE id=$1 AND company_id=$2)")
            .bind(&vacancy_id)
            .bind(&actor.subject_id)
            .fetch_one(&s.db)
            .await?;
    if !own {
        return Err(AppError::missing());
    }
    sqlx::query("INSERT INTO ats_vacancy_mappings(company_id,vacancy_id,external_vacancy_id) VALUES($1,$2,$3) ON CONFLICT(company_id,vacancy_id) DO UPDATE SET external_vacancy_id=EXCLUDED.external_vacancy_id,updated_at=now()")
        .bind(&actor.subject_id).bind(&vacancy_id).bind(input.external_vacancy_id).execute(&s.db).await?;
    crate::db::audit(
        &s,
        &actor.id,
        "ats.talantix.vacancy_mapped",
        &vacancy_id,
        json!({"external_vacancy_id":input.external_vacancy_id}),
    )
    .await?;
    Ok(Json(
        json!({"mapping":{"vacancy_id":vacancy_id,"external_vacancy_id":input.external_vacancy_id}}),
    ))
}

pub async fn enqueue(
    tx: &mut sqlx::Transaction<'_, sqlx::Postgres>,
    company_id: &str,
    candidate_id: &str,
    vacancy_id: &str,
    event_type: &str,
    event_id: &str,
) -> Result<()> {
    let ready: bool = sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM ats_connections c JOIN ats_vacancy_mappings m ON m.company_id=c.company_id AND m.vacancy_id=$2 WHERE c.company_id=$1 AND c.status='connected' AND c.source_id IS NOT NULL)")
        .bind(company_id).bind(vacancy_id).fetch_one(&mut **tx).await?;
    if ready {
        sqlx::query("INSERT INTO ats_outbox(id,company_id,event_type,event_id,candidate_id,vacancy_id) VALUES($1,$2,$3,$4,$5,$6) ON CONFLICT(company_id,provider,event_type,event_id) DO NOTHING")
            .bind(new_id("O")).bind(company_id).bind(event_type).bind(event_id).bind(candidate_id).bind(vacancy_id).execute(&mut **tx).await?;
    }
    Ok(())
}

fn html_escape(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#39;")
}

fn graphql_string(value: &str) -> String {
    serde_json::to_string(value).unwrap_or_else(|_| "\"\"".into())
}

fn contact_fragment(kind: &str, value: &str) -> Option<String> {
    let value = value.trim();
    (!value.is_empty()).then(|| format!("{{type: {kind}, value: {}}}", graphql_string(value)))
}

async fn dispatch_one(s: &AppState) -> Result<bool> {
    let row: Option<(String, String, String, String, String, String, i32)> = sqlx::query_as(
        "WITH picked AS (SELECT id FROM ats_outbox WHERE status='queued' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1) UPDATE ats_outbox o SET status='processing',attempts=attempts+1,lease_until=now()+interval '90 seconds',updated_at=now() FROM picked WHERE o.id=picked.id RETURNING o.id,o.company_id,o.candidate_id,o.vacancy_id,o.event_type,o.event_id,o.attempts",
    ).fetch_optional(&s.db).await?;
    let Some((id, company_id, candidate_id, vacancy_id, _event_type, _event_id, _attempts)) = row
    else {
        return Ok(false);
    };
    let payload: Option<(String, String, String, String, String, String, i64, i64)> = sqlx::query_as(
        "SELECT c.full_name,c.email,c.phone,c.specialization,c.about,array_to_string(c.skills,', '),m.external_vacancy_id,ac.source_id FROM candidates c JOIN ats_vacancy_mappings m ON m.company_id=$2 AND m.vacancy_id=$3 JOIN ats_connections ac ON ac.company_id=$2 AND ac.status='connected' AND ac.source_id IS NOT NULL WHERE c.id=$1 AND c.consent_processing AND NOT c.employment_blocked AND NOT EXISTS(SELECT 1 FROM contact_revocations r WHERE r.candidate_id=c.id AND r.company_id=$2)",
    ).bind(&candidate_id).bind(&company_id).bind(&vacancy_id).fetch_optional(&s.db).await?;
    let Some((
        full_name,
        email,
        phone,
        specialization,
        about,
        skills,
        external_vacancy_id,
        source_id,
    )) = payload
    else {
        sqlx::query("UPDATE ats_outbox SET status='cancelled',last_error_code='consent_or_mapping_missing',lease_until=NULL,updated_at=now() WHERE id=$1").bind(&id).execute(&s.db).await?;
        return Ok(true);
    };
    let parts: Vec<&str> = full_name.split_whitespace().collect();
    let contacts: Vec<String> = [
        contact_fragment("email", &email),
        contact_fragment("cell", &phone),
    ]
    .into_iter()
    .flatten()
    .collect();
    if parts.len() < 2 || contacts.is_empty() {
        sqlx::query("UPDATE ats_outbox SET status='failed',last_error_code='candidate_profile_incomplete',lease_until=NULL,updated_at=now() WHERE id=$1").bind(&id).execute(&s.db).await?;
        return Ok(true);
    }
    let token = match current_access_token(s, &company_id).await {
        Ok(token) => token,
        Err(error) => {
            sqlx::query("UPDATE ats_outbox SET status='needs_review',last_error_code='authorization_or_transport',lease_until=NULL,updated_at=now() WHERE id=$1").bind(&id).execute(&s.db).await?;
            return Err(error);
        }
    };
    let resume = format!(
        "<p><strong>{}</strong></p><p>Специализация: {}</p><p>Навыки: {}</p><p>{}</p><p>Источник: ФСП · Траектория. Передача подтверждена кандидатом.</p>",
        html_escape(&full_name),
        html_escape(&specialization),
        html_escape(&skills),
        html_escape(&about)
    );
    let middle = if parts.len() > 2 {
        format!(
            "middleName: {},",
            graphql_string(&parts[1..parts.len() - 1].join(" "))
        )
    } else {
        String::new()
    };
    let query = format!(
        "mutation CreatePerson {{ createPerson(personCreate: {{ firstName: {}, {} lastName: {}, contacts: [{}], customResumes: [{{text: {}, type: TMS}}], sourceId: {}, vacancyIds: [{}] }}) {{ ... on PersonItem {{ id }} ... on PersonSaveError {{ errorType errors {{ field violatedConstraints }} }} }} }}",
        graphql_string(parts[0]),
        middle,
        graphql_string(parts.last().unwrap()),
        contacts.join(","),
        graphql_string(&resume),
        source_id,
        external_vacancy_id
    );
    let result = graphql(s, &token, &query).await;
    match result {
        Ok(data) => {
            let external_id = data.pointer("/createPerson/id").and_then(Value::as_i64);
            if let Some(person_id) = external_id {
                sqlx::query("UPDATE ats_outbox SET status='sent',external_person_id=$2,sent_at=now(),lease_until=NULL,last_error_code=NULL,updated_at=now() WHERE id=$1").bind(&id).bind(person_id).execute(&s.db).await?;
            } else {
                // Provider-side validation is final: automatic retries could create duplicates.
                sqlx::query("UPDATE ats_outbox SET status='failed',last_error_code='remote_validation',lease_until=NULL,updated_at=now() WHERE id=$1").bind(&id).execute(&s.db).await?;
            }
        }
        Err(_) => {
            // Once a request has been handed to the network its outcome can be ambiguous.
            sqlx::query("UPDATE ats_outbox SET status='needs_review',last_error_code='ambiguous_delivery',lease_until=NULL,updated_at=now() WHERE id=$1").bind(&id).execute(&s.db).await?;
        }
    }
    Ok(true)
}

pub async fn dispatch(s: AppState) {
    loop {
        // Never replay a request whose previous process might have delivered it.
        let _ = sqlx::query("UPDATE ats_outbox SET status='needs_review',last_error_code='lease_expired',lease_until=NULL,updated_at=now() WHERE status='processing' AND lease_until<now()")
            .execute(&s.db).await;
        match dispatch_one(&s).await {
            Ok(true) => {}
            Ok(false) => tokio::time::sleep(StdDuration::from_secs(2)).await,
            Err(_) => tokio::time::sleep(StdDuration::from_secs(2)).await,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn token_envelopes_are_bound_to_company_and_purpose() {
        // The integration key is isolated to this test process and not read by
        // the other unit tests. Rust 2024 marks process-environment mutation unsafe.
        unsafe {
            std::env::set_var("INTEGRATION_ENCRYPTION_KEY", "11".repeat(32));
        }
        let envelope = encrypt("company-a", "access", "sensitive-token").unwrap();
        assert_eq!(
            decrypt("company-a", "access", &envelope).unwrap(),
            "sensitive-token"
        );
        assert!(decrypt("company-b", "access", &envelope).is_err());
        assert!(decrypt("company-a", "refresh", &envelope).is_err());
    }
    #[test]
    fn free_form_resume_is_escaped_before_tms_submission() {
        assert_eq!(html_escape("<img src=x> &"), "&lt;img src=x&gt; &amp;");
    }
}
