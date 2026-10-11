use crate::{
    AppState,
    auth::new_id,
    error::{AppError, Result},
};
use aes_gcm::{
    Aes256Gcm, KeyInit, Nonce,
    aead::{Aead, Payload},
};
use rand::RngCore;

fn cipher() -> anyhow::Result<Aes256Gcm> {
    let encoded = crate::config::secret("MAIL_ENCRYPTION_KEY")?;
    anyhow::ensure!(
        encoded.len() == 64 && encoded.is_ascii(),
        "MAIL_ENCRYPTION_KEY must be 64 hexadecimal characters"
    );
    let bytes = (0..32)
        .map(|i| u8::from_str_radix(&encoded[i * 2..i * 2 + 2], 16))
        .collect::<std::result::Result<Vec<_>, _>>()?;
    Ok(Aes256Gcm::new_from_slice(&bytes).map_err(|_| anyhow::anyhow!("Invalid mail key"))?)
}
pub fn validate_config() -> anyhow::Result<()> {
    cipher().map(|_| ())
}
fn encrypt(text: &str, aad: &[u8]) -> anyhow::Result<Vec<u8>> {
    let mut nonce = [0u8; 12];
    rand::rngs::OsRng.fill_bytes(&mut nonce);
    let encrypted = cipher()?
        .encrypt(
            Nonce::from_slice(&nonce),
            Payload {
                msg: text.as_bytes(),
                aad,
            },
        )
        .map_err(|_| anyhow::anyhow!("Mail encryption failed"))?;
    Ok([nonce.to_vec(), encrypted].concat())
}
fn decrypt(data: &[u8], aad: &[u8]) -> anyhow::Result<String> {
    anyhow::ensure!(data.len() > 28, "Invalid mail envelope");
    let plain = cipher()?
        .decrypt(
            Nonce::from_slice(&data[..12]),
            Payload {
                msg: &data[12..],
                aad,
            },
        )
        .map_err(|_| anyhow::anyhow!("Mail authentication failed"))?;
    Ok(String::from_utf8(plain)?)
}
pub async fn enqueue(
    tx: &mut sqlx::Transaction<'_, sqlx::Postgres>,
    recipient: &str,
    purpose: &str,
    link: &str,
) -> Result<()> {
    let encrypted = encrypt(link, format!("{recipient}\0{purpose}").as_bytes()).map_err(|_| {
        AppError(
            axum::http::StatusCode::SERVICE_UNAVAILABLE,
            "Отправка писем не настроена".into(),
        )
    })?;
    sqlx::query("INSERT INTO mail_outbox(id,recipient,purpose,encrypted_body,expires_at) VALUES($1,$2,$3,$4,now()+interval '30 minutes')")
        .bind(new_id("M")).bind(recipient).bind(purpose).bind(encrypted).execute(&mut **tx).await?;
    Ok(())
}
async fn send(recipient: &str, purpose: &str, link: &str) -> anyhow::Result<()> {
    use lettre::{
        AsyncSmtpTransport, AsyncTransport, Message, Tokio1Executor,
        transport::smtp::authentication::Credentials,
    };
    let host = std::env::var("SMTP_HOST")?;
    let subject = if purpose == "reset" {
        "Восстановление пароля · ФСП Траектория"
    } else {
        "Подтвердите email · ФСП Траектория"
    };
    let message=Message::builder().from(std::env::var("SMTP_FROM")?.parse()?).to(recipient.parse()?).subject(subject)
        .body(format!("Откройте ссылку в течение 30 минут:\n{link}\n\nЕсли вы не запрашивали это действие, проигнорируйте письмо."))?;
    let mut transport = AsyncSmtpTransport::<Tokio1Executor>::relay(&host)?
        .timeout(Some(std::time::Duration::from_secs(15)));
    if let (Ok(user), Ok(password)) = (
        crate::config::secret("SMTP_USER"),
        crate::config::secret("SMTP_PASSWORD"),
    ) {
        transport = transport.credentials(Credentials::new(user, password));
    }
    transport.build().send(message).await?;
    Ok(())
}
pub async fn dispatch(s: AppState) {
    loop {
        let _ = sqlx::query("DELETE FROM mail_outbox WHERE expires_at<now()")
            .execute(&s.db)
            .await;
        let row=sqlx::query_as::<_,(String,String,String,Vec<u8>)>("WITH picked AS(SELECT id FROM mail_outbox WHERE attempts<5 AND next_attempt_at<=now() AND (lease_until IS NULL OR lease_until<now()) ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1) UPDATE mail_outbox m SET attempts=attempts+1,lease_until=now()+interval '60 seconds' FROM picked WHERE m.id=picked.id RETURNING m.id,m.recipient,m.purpose,m.encrypted_body").fetch_optional(&s.db).await;
        if let Ok(Some((id, recipient, purpose, payload))) = row {
            let success = match decrypt(&payload, format!("{recipient}\0{purpose}").as_bytes()) {
                Ok(link) => send(&recipient, &purpose, &link).await.is_ok(),
                Err(_) => false,
            };
            if success {
                let _ = sqlx::query("DELETE FROM mail_outbox WHERE id=$1")
                    .bind(&id)
                    .execute(&s.db)
                    .await;
            } else {
                let _=sqlx::query("UPDATE mail_outbox SET lease_until=NULL,next_attempt_at=now()+attempts*interval '60 seconds' WHERE id=$1").bind(&id).execute(&s.db).await;
                tracing::warn!(message_id = id, "mail_delivery_retry");
            }
        }
        tokio::time::sleep(std::time::Duration::from_secs(2)).await;
    }
}
