use crate::{
    AppState,
    error::{AppError, Result},
};
use argon2::{
    Argon2, PasswordHash, PasswordHasher, PasswordVerifier,
    password_hash::{SaltString, rand_core::OsRng},
};
use axum::{
    Json,
    extract::{FromRequestParts, State},
    http::{HeaderMap, HeaderValue, StatusCode, header, request::Parts},
    response::{IntoResponse, Response},
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use sqlx::FromRow;

#[derive(Clone, Debug, Serialize, FromRow)]
pub struct Actor {
    pub id: String,
    pub email: String,
    pub role: String,
    pub subject_id: String,
    pub synthetic: bool,
    #[serde(skip)]
    pub auth_epoch: i64,
}
impl Actor {
    pub async fn verified_employer(&self, s: &AppState) -> Result<()> {
        self.require("employer")?;
        if s.security.production {
            let verified: bool = sqlx::query_scalar("SELECT verification_status='verified' AND NOT synthetic FROM companies WHERE id=$1").bind(&self.subject_id).fetch_one(&s.db).await?;
            if !verified {
                return Err(AppError(
                    StatusCode::FORBIDDEN,
                    "Подбор и предложения доступны после проверки компании оператором".into(),
                ));
            }
        }
        Ok(())
    }
    pub fn require(&self, role: &str) -> Result<()> {
        if self.role == role {
            Ok(())
        } else {
            Err(AppError::forbidden())
        }
    }
}
pub fn hash_token(s: &str) -> String {
    format!("{:x}", Sha256::digest(s.as_bytes()))
}
pub fn new_id(prefix: &str) -> String {
    format!("{prefix}{}", uuid::Uuid::new_v4().simple())
}
fn read_token(headers: &HeaderMap, secure: bool) -> Option<String> {
    let prefix = if secure {
        "__Host-fsp_session="
    } else {
        "fsp_session="
    };
    headers
        .get(header::COOKIE)
        .and_then(|h| h.to_str().ok())
        .and_then(|s| {
            s.split(';')
                .find_map(|p| p.trim().strip_prefix(prefix).map(str::to_owned))
        })
        .or_else(|| {
            headers
                .get(header::AUTHORIZATION)
                .and_then(|h| h.to_str().ok())
                .and_then(|s| s.strip_prefix("Bearer ").map(str::to_owned))
        })
}
impl FromRequestParts<AppState> for Actor {
    type Rejection = AppError;
    async fn from_request_parts(parts: &mut Parts, state: &AppState) -> Result<Self> {
        let token = read_token(&parts.headers, state.base_url.starts_with("https://"))
            .ok_or_else(|| AppError(StatusCode::UNAUTHORIZED, "Войдите в личный кабинет".into()))?;
        sqlx::query_as::<_,Actor>("SELECT u.id,u.email,u.role,u.subject_id,u.synthetic,u.auth_epoch FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=$1 AND s.expires_at>now() AND u.email_verified AND s.auth_epoch=u.auth_epoch")
            .bind(hash_token(&token)).fetch_optional(&state.db).await?.ok_or_else(||AppError(StatusCode::UNAUTHORIZED,"Сессия истекла. Войдите снова.".into()))
    }
}
pub fn password_hash(password: &str) -> anyhow::Result<String> {
    Ok(Argon2::default()
        .hash_password(password.as_bytes(), &SaltString::generate(&mut OsRng))
        .map_err(|e| anyhow::anyhow!(e.to_string()))?
        .to_string())
}
pub(crate) async fn create_session(s: &AppState, actor: Actor) -> Result<Response> {
    let token = format!(
        "{}{}",
        uuid::Uuid::new_v4().simple(),
        uuid::Uuid::new_v4().simple()
    );
    let mut tx = s.db.begin().await?;
    let current_epoch: i64 =
        sqlx::query_scalar("SELECT auth_epoch FROM users WHERE id=$1 FOR UPDATE")
            .bind(&actor.id)
            .fetch_one(&mut *tx)
            .await?;
    if current_epoch != actor.auth_epoch {
        return Err(AppError(
            StatusCode::UNAUTHORIZED,
            "Учётные данные изменились. Войдите снова.".into(),
        ));
    }
    sqlx::query("DELETE FROM sessions WHERE user_id=$1 AND (expires_at<now() OR token_hash IN (SELECT token_hash FROM sessions WHERE user_id=$1 ORDER BY created_at DESC OFFSET 9))").bind(&actor.id).execute(&mut *tx).await?;
    sqlx::query("INSERT INTO sessions(token_hash,user_id,expires_at,auth_epoch) VALUES($1,$2,now()+interval '12 hours',$3)").bind(hash_token(&token)).bind(&actor.id).bind(actor.auth_epoch).execute(&mut *tx).await?;
    sqlx::query(
        "INSERT INTO audit_events(actor_id,action,entity_id) VALUES($1,'auth.session_created',$1)",
    )
    .bind(&actor.id)
    .execute(&mut *tx)
    .await?;
    tx.commit().await?;
    let secure = if s.base_url.starts_with("https://") {
        "; Secure"
    } else {
        ""
    };
    let mut response = Json(json!({"user":actor})).into_response();
    let cookie_name = if secure.is_empty() {
        "fsp_session"
    } else {
        "__Host-fsp_session"
    };
    response.headers_mut().insert(
        header::SET_COOKIE,
        HeaderValue::from_str(&format!(
            "{cookie_name}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=43200{secure}"
        ))
        .unwrap(),
    );
    Ok(response)
}

#[derive(Deserialize)]
pub struct Register {
    email: String,
    password: String,
    role: String,
    name: String,
    consent_processing: bool,
}
pub async fn register(
    State(s): State<AppState>,
    Json(input): Json<Register>,
) -> Result<Json<Value>> {
    let email = input.email.trim().to_lowercase();
    if email.len() > 254
        || email.parse::<lettre::Address>().is_err()
        || email.chars().any(char::is_whitespace)
        || !email.contains('@')
        || !email.rsplit('@').next().unwrap_or("").contains('.')
    {
        return Err(AppError::bad("Укажите корректный email"));
    }
    if !(10..=256).contains(&input.password.chars().count()) {
        return Err(AppError::bad(
            "Пароль должен содержать от 10 до 256 символов",
        ));
    }
    if !["candidate", "employer"].contains(&input.role.as_str())
        || input.name.trim().len() < 2
        || input.name.len() > 200
    {
        return Err(AppError::bad("Проверьте роль и имя"));
    }
    if !input.consent_processing {
        return Err(AppError::bad(
            "Для регистрации требуется согласие на обработку данных",
        ));
    }
    let _permit = s.auth_slots.clone().try_acquire_owned().map_err(|_| {
        AppError(
            StatusCode::TOO_MANY_REQUESTS,
            "Слишком много запросов входа. Повторите позже.".into(),
        )
    })?;
    let hash = tokio::task::spawn_blocking(move || {
        let _permit = _permit;
        password_hash(&input.password)
    })
    .await
    .map_err(|_| AppError::bad("Не удалось создать пароль"))?
    .map_err(|_| AppError::bad("Не удалось создать пароль"))?;
    let id = new_id("U");
    let subject = new_id(if input.role == "candidate" { "C" } else { "E" });
    let token = new_id("verify_");
    let mut tx = s.db.begin().await?;
    sqlx::query("SELECT pg_advisory_xact_lock(hashtextextended($1,0))")
        .bind(&email)
        .execute(&mut *tx)
        .await?;
    let exists: bool = sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM users WHERE email=$1)")
        .bind(&email)
        .fetch_one(&mut *tx)
        .await?;
    if exists {
        return Ok(Json(
            json!({"message":"Если адрес доступен для регистрации, письмо с подтверждением будет отправлено","email":email}),
        ));
    }
    if input.role == "candidate" {
        sqlx::query("INSERT INTO candidates(id,display_name,full_name,email,consent_processing) VALUES($1,$2,$3,$4,true)").bind(&subject).bind(format!("Кандидат {}",&subject[1..9])).bind(input.name.trim()).bind(&email).execute(&mut *tx).await?;
    } else {
        sqlx::query("INSERT INTO companies(id,name,contact) VALUES($1,$2,$3)")
            .bind(&subject)
            .bind(input.name.trim())
            .bind(&email)
            .execute(&mut *tx)
            .await?;
    }
    sqlx::query("INSERT INTO users(id,email,password_hash,role,subject_id) VALUES($1,$2,$3,$4,$5)")
        .bind(&id)
        .bind(&email)
        .bind(hash)
        .bind(&input.role)
        .bind(&subject)
        .execute(&mut *tx)
        .await?;
    sqlx::query("INSERT INTO email_tokens(token_hash,user_id,expires_at) VALUES($1,$2,now()+interval '30 minutes')").bind(hash_token(&token)).bind(&id).execute(&mut *tx).await?;
    let link = format!("{}/?verify={token}", s.base_url);
    if !s.demo {
        crate::mail::enqueue(&mut tx, &email, "verify", &link).await?;
    }
    tx.commit().await?;
    let mut result = json!({"message":"Если адрес доступен для регистрации, письмо с подтверждением будет отправлено","email":email});
    if s.demo {
        result["development_mail"] = json!({"subject":"Подтвердите email · ФСП Траектория","link":link,"token":token,"notice":"Локальная почтовая песочница. Внешнее письмо не отправлялось."});
    }
    Ok(Json(result))
}
#[derive(Deserialize)]
pub struct Verify {
    token: String,
}
pub async fn verify(State(s): State<AppState>, Json(input): Json<Verify>) -> Result<Response> {
    let mut tx = s.db.begin().await?;
    let uid: Option<String> = sqlx::query_scalar(
        "DELETE FROM email_tokens WHERE token_hash=$1 AND expires_at>now() RETURNING user_id",
    )
    .bind(hash_token(&input.token))
    .fetch_optional(&mut *tx)
    .await?;
    let uid = uid.ok_or_else(|| AppError::bad("Ссылка недействительна или истекла"))?;
    let actor=sqlx::query_as::<_,Actor>("UPDATE users SET email_verified=true WHERE id=$1 RETURNING id,email,role,subject_id,synthetic,auth_epoch").bind(uid).fetch_one(&mut *tx).await?;
    tx.commit().await?;
    create_session(&s, actor).await
}
#[derive(Deserialize)]
pub struct Login {
    #[serde(alias = "email")]
    identifier: String,
    password: String,
}
pub async fn login(State(s): State<AppState>, Json(input): Json<Login>) -> Result<Response> {
    let identifier = input.identifier.trim();
    if identifier.is_empty() || input.password.chars().count() > 256 || identifier.len() > 254 {
        return Err(AppError::bad("Некорректные данные"));
    }
    let key = hash_token(&format!("login:{}", identifier.to_lowercase()));
    let hits:i32=sqlx::query_scalar("INSERT INTO auth_throttle(key_hash) VALUES($1) ON CONFLICT(key_hash) DO UPDATE SET hits=CASE WHEN auth_throttle.window_start<now()-interval '15 minutes' THEN 1 ELSE auth_throttle.hits+1 END,window_start=CASE WHEN auth_throttle.window_start<now()-interval '15 minutes' THEN now() ELSE auth_throttle.window_start END RETURNING hits").bind(&key).fetch_one(&s.db).await?;
    if hits > 20 {
        return Err(AppError(
            StatusCode::TOO_MANY_REQUESTS,
            "Слишком много попыток для этого логина. Повторите через 15 минут.".into(),
        ));
    }
    let _permit = s
        .auth_slots
        .clone()
        .try_acquire_owned()
        .map_err(|_| AppError(StatusCode::TOO_MANY_REQUESTS, "Повторите вход позже".into()))?;
    // An email is canonical and therefore takes precedence over a human-readable name.
    // Names can be shared, so an ambiguous name must never select an arbitrary account.
    let email_row: Option<(String, String, bool, i64)> = sqlx::query_as(
        "SELECT id,password_hash,email_verified,auth_epoch FROM users WHERE email=$1",
    )
    .bind(identifier.to_lowercase())
    .fetch_optional(&s.db)
    .await?;
    let rows: Vec<(String, String, bool, i64)> = if let Some(row) = email_row {
        vec![row]
    } else {
        sqlx::query_as(
            "SELECT u.id,u.password_hash,u.email_verified,u.auth_epoch FROM users u \
             JOIN candidates c ON c.id=u.subject_id \
             WHERE u.role='candidate' AND (c.full_name=$1 OR c.display_name=$1) \
             UNION \
             SELECT u.id,u.password_hash,u.email_verified,u.auth_epoch FROM users u \
             JOIN companies c ON c.id=u.subject_id \
             WHERE u.role='employer' AND c.name=$1 \
             LIMIT 2",
        )
        .bind(identifier)
        .fetch_all(&s.db)
        .await?
    };
    let known = rows.len() == 1;
    let (id, hash, verified, epoch) = if known {
        rows.into_iter()
            .next()
            .expect("one resolved login identity")
    } else {
        (
            String::new(),
            s.dummy_password_hash.as_ref().clone(),
            false,
            0,
        )
    };
    let valid = tokio::task::spawn_blocking(move || {
        let _permit = _permit;
        PasswordHash::new(&hash)
            .map(|h| {
                Argon2::default()
                    .verify_password(input.password.as_bytes(), &h)
                    .is_ok()
            })
            .unwrap_or(false)
    })
    .await
    .unwrap_or(false);
    if !valid || !known {
        return Err(AppError(
            StatusCode::UNAUTHORIZED,
            "Неверный логин или пароль".into(),
        ));
    }
    if !verified {
        return Err(AppError(
            StatusCode::FORBIDDEN,
            "Сначала подтвердите email".into(),
        ));
    }
    sqlx::query("DELETE FROM auth_throttle WHERE key_hash=$1")
        .bind(key)
        .execute(&s.db)
        .await?;
    let actor = sqlx::query_as::<_, Actor>(
        "SELECT id,email,role,subject_id,synthetic,auth_epoch FROM users WHERE id=$1 AND auth_epoch=$2",
    )
    .bind(id)
    .bind(epoch)
    .fetch_optional(&s.db)
    .await?.ok_or_else(||AppError(StatusCode::UNAUTHORIZED,"Учётные данные изменились. Войдите снова.".into()))?;
    create_session(&s, actor).await
}
pub async fn me(actor: Actor) -> Json<Value> {
    Json(json!({"user":actor}))
}
pub async fn logout(State(s): State<AppState>, headers: HeaderMap) -> Result<Response> {
    if let Some(token) = read_token(&headers, s.base_url.starts_with("https://")) {
        sqlx::query("DELETE FROM sessions WHERE token_hash=$1")
            .bind(hash_token(&token))
            .execute(&s.db)
            .await?;
    }
    let mut response = Json(json!({"ok":true})).into_response();
    response.headers_mut().insert(
        header::SET_COOKIE,
        HeaderValue::from_static(if s.base_url.starts_with("https://") {
            "__Host-fsp_session=; Path=/; HttpOnly; SameSite=Strict; Secure; Max-Age=0"
        } else {
            "fsp_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"
        }),
    );
    Ok(response)
}

#[derive(Deserialize)]
pub struct ResetRequest {
    email: String,
}
pub async fn request_reset(
    State(s): State<AppState>,
    Json(input): Json<ResetRequest>,
) -> Result<Json<Value>> {
    let email = input.email.trim().to_lowercase();
    if email.len() > 254 {
        return Err(AppError::bad("Некорректный email"));
    }
    let mut output = json!({"message":"Если адрес зарегистрирован, мы отправим ссылку для восстановления пароля."});
    if crate::security::throttle(&s, &format!("reset-email:{email}"), 3)
        .await
        .is_err()
    {
        return Ok(Json(output));
    }
    let uid: Option<String> =
        sqlx::query_scalar("SELECT id FROM users WHERE email=$1 AND NOT synthetic")
            .bind(&email)
            .fetch_optional(&s.db)
            .await?;
    if let Some(uid) = uid {
        let token = new_id("reset_");
        let link = format!("{}/?reset={token}", s.base_url);
        let mut tx = s.db.begin().await?;
        sqlx::query("INSERT INTO password_reset_tokens(token_hash,user_id,expires_at) VALUES($1,$2,now()+interval '30 minutes')").bind(hash_token(&token)).bind(&uid).execute(&mut *tx).await?;
        if !s.demo {
            crate::mail::enqueue(&mut tx, &email, "reset", &link).await?;
        }
        tx.commit().await?;
        if s.demo {
            output["development_mail"] =
                json!({"token":token,"link":link,"notice":"Локальная почтовая песочница"});
        }
    }
    Ok(Json(output))
}
#[derive(Deserialize)]
pub struct ResetConfirm {
    token: String,
    password: String,
}
pub async fn confirm_reset(
    State(s): State<AppState>,
    Json(input): Json<ResetConfirm>,
) -> Result<Json<Value>> {
    if input.token.len() > 100 || !(10..=256).contains(&input.password.chars().count()) {
        return Err(AppError::bad(
            "Пароль должен содержать от 10 до 256 символов",
        ));
    }
    let permit = s
        .auth_slots
        .clone()
        .try_acquire_owned()
        .map_err(|_| AppError(StatusCode::TOO_MANY_REQUESTS, "Повторите позже".into()))?;
    let hash = tokio::task::spawn_blocking(move || {
        let _permit = permit;
        password_hash(&input.password)
    })
    .await
    .map_err(|_| AppError::bad("Ошибка смены пароля"))?
    .map_err(|_| AppError::bad("Ошибка смены пароля"))?;
    let mut tx = s.db.begin().await?;
    let uid: Option<String>=sqlx::query_scalar("DELETE FROM password_reset_tokens WHERE token_hash=$1 AND expires_at>now() RETURNING user_id").bind(hash_token(&input.token)).fetch_optional(&mut *tx).await?;
    let uid = uid.ok_or_else(|| AppError::bad("Ссылка недействительна или истекла"))?;
    sqlx::query(
        "UPDATE users SET password_hash=$2,email_verified=true,auth_epoch=auth_epoch+1 WHERE id=$1",
    )
    .bind(&uid)
    .bind(hash)
    .execute(&mut *tx)
    .await?;
    for query in [
        "DELETE FROM sessions WHERE user_id=$1",
        "DELETE FROM password_reset_tokens WHERE user_id=$1",
        "DELETE FROM email_tokens WHERE user_id=$1",
    ] {
        sqlx::query(query).bind(&uid).execute(&mut *tx).await?;
    }
    sqlx::query(
        "INSERT INTO audit_events(actor_id,action,entity_id) VALUES($1,'auth.password_reset',$1)",
    )
    .bind(&uid)
    .execute(&mut *tx)
    .await?;
    tx.commit().await?;
    Ok(Json(
        json!({"message":"Пароль изменён. Все прежние сессии завершены. Войдите с новым паролем."}),
    ))
}
pub async fn logout_all(
    State(s): State<AppState>,
    actor: Actor,
    headers: HeaderMap,
) -> Result<Response> {
    sqlx::query("UPDATE users SET auth_epoch=auth_epoch+1 WHERE id=$1")
        .bind(&actor.id)
        .execute(&s.db)
        .await?;
    sqlx::query("DELETE FROM sessions WHERE user_id=$1")
        .bind(&actor.id)
        .execute(&s.db)
        .await?;
    crate::db::audit(&s, &actor.id, "auth.sessions_revoked", &actor.id, json!({})).await?;
    logout(State(s), headers).await
}
