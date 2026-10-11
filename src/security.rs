use crate::{AppState, auth::hash_token, error::AppError};
use axum::{
    body::Body,
    extract::{ConnectInfo, Request, State},
    http::{HeaderValue, Method, StatusCode, header},
    middleware::Next,
    response::{IntoResponse, Response},
};
use std::{
    collections::HashMap,
    net::{IpAddr, SocketAddr},
    sync::Mutex,
    time::{Duration, Instant},
};

pub struct Security {
    pub production: bool,
    pub origins: Vec<String>,
    pub hosts: Vec<String>,
    proxies: Vec<ProxyNetwork>,
    requests: Mutex<HashMap<IpAddr, (Instant, u32)>>,
    pub slots: std::sync::Arc<tokio::sync::Semaphore>,
    pub uploads: std::sync::Arc<tokio::sync::Semaphore>,
}

#[derive(Clone)]
struct ProxyNetwork {
    address: IpAddr,
    prefix: u32,
}
impl std::str::FromStr for ProxyNetwork {
    type Err = anyhow::Error;
    fn from_str(value: &str) -> anyhow::Result<Self> {
        let (address, prefix) = match value.split_once('/') {
            Some((address, prefix)) => (address.parse::<IpAddr>()?, Some(prefix.parse::<u32>()?)),
            None => (value.parse::<IpAddr>()?, None),
        };
        let width = if address.is_ipv4() { 32 } else { 128 };
        let prefix = prefix.unwrap_or(width);
        anyhow::ensure!(prefix <= width, "Invalid trusted proxy CIDR");
        Ok(Self { address, prefix })
    }
}
impl ProxyNetwork {
    fn contains(&self, ip: IpAddr) -> bool {
        match (self.address, ip) {
            (IpAddr::V4(a), IpAddr::V4(b)) => {
                self.prefix == 0
                    || (u32::from(a) >> (32 - self.prefix)) == (u32::from(b) >> (32 - self.prefix))
            }
            (IpAddr::V6(a), IpAddr::V6(b)) => {
                self.prefix == 0
                    || (u128::from(a) >> (128 - self.prefix))
                        == (u128::from(b) >> (128 - self.prefix))
            }
            _ => false,
        }
    }
}

impl Security {
    pub fn load(base: &str, demo: bool, preparing: bool) -> anyhow::Result<Self> {
        let environment = std::env::var("FSP_ENV").unwrap_or("development".into());
        anyhow::ensure!(
            matches!(environment.as_str(), "development" | "production"),
            "FSP_ENV must be development or production"
        );
        let production = environment == "production";
        let url = reqwest::Url::parse(base)?;
        anyhow::ensure!(
            matches!(url.scheme(), "http" | "https")
                && url.username().is_empty()
                && url.password().is_none()
                && url.query().is_none()
                && url.fragment().is_none()
                && url.path() == "/",
            "BASE_URL must be an HTTP(S) origin without credentials, path, query or fragment"
        );
        if production {
            if !preparing {
                crate::mail::validate_config()?;
                crate::talantix::validate_config(true)?;
            }
            anyhow::ensure!(!demo, "Production forbids FSP_DEMO_MODE");
            anyhow::ensure!(
                url.scheme() == "https"
                    && !matches!(url.host_str(), Some("localhost" | "127.0.0.1" | "::1")),
                "Production requires a public HTTPS BASE_URL"
            );
            for key in if preparing {
                &[][..]
            } else {
                &["SMTP_HOST", "SMTP_FROM"][..]
            } {
                anyhow::ensure!(
                    std::env::var(key).is_ok_and(|v| !v.trim().is_empty()),
                    "Production requires {key}"
                );
            }
        }
        let mut origins = vec![url.origin().ascii_serialization()];
        if !production {
            let port = url.port_or_known_default().unwrap_or(8080);
            origins.extend([
                format!("http://localhost:{port}"),
                format!("http://127.0.0.1:{port}"),
            ]);
        }
        let hosts = origins
            .iter()
            .map(|s| s.split_once("://").unwrap().1.to_owned())
            .collect();
        let proxies = std::env::var("TRUSTED_PROXY_IPS")
            .unwrap_or_default()
            .split(',')
            .filter(|s| !s.trim().is_empty())
            .map(|s| s.trim().parse())
            .collect::<Result<Vec<ProxyNetwork>, _>>()?;
        Ok(Self {
            production,
            origins,
            hosts,
            proxies,
            requests: Mutex::new(HashMap::new()),
            slots: std::sync::Arc::new(tokio::sync::Semaphore::new(128)),
            uploads: std::sync::Arc::new(tokio::sync::Semaphore::new(2)),
        })
    }

    fn allow_ip(&self, ip: IpAddr) -> bool {
        let mut map = self.requests.lock().unwrap_or_else(|e| e.into_inner());
        if !map.contains_key(&ip) && map.len() >= 10_000 {
            map.retain(|_, (start, _)| start.elapsed() < Duration::from_secs(60));
            if map.len() >= 10_000 {
                return false;
            }
        }
        let (start, count) = map.entry(ip).or_insert((Instant::now(), 0));
        if start.elapsed() >= Duration::from_secs(60) {
            *start = Instant::now();
            *count = 0;
        }
        *count = count.saturating_add(1);
        *count <= 3000
    }
}

pub async fn throttle(s: &AppState, key: &str, limit: i32) -> crate::error::Result<()> {
    let hits: i32 = sqlx::query_scalar("INSERT INTO auth_throttle(key_hash) VALUES($1) ON CONFLICT(key_hash) DO UPDATE SET hits=CASE WHEN auth_throttle.window_start<now()-interval '15 minutes' THEN 1 ELSE least(auth_throttle.hits+1,1000000) END,window_start=CASE WHEN auth_throttle.window_start<now()-interval '15 minutes' THEN now() ELSE auth_throttle.window_start END RETURNING hits")
        .bind(hash_token(key)).fetch_one(&s.db).await?;
    if hits > limit {
        return Err(AppError(
            StatusCode::TOO_MANY_REQUESTS,
            "Лимит запросов достигнут. Повторите позже.".into(),
        ));
    }
    Ok(())
}

fn reject(status: StatusCode, message: &str) -> Response {
    AppError(status, message.into()).into_response()
}

pub fn origin_allowed(
    allowed: &[String],
    origin: Option<&str>,
    fetch_site: Option<&str>,
    cookie: bool,
    unsafe_method: bool,
) -> bool {
    if matches!(fetch_site, Some("cross-site" | "same-site")) {
        return false;
    }
    if let Some(origin) = origin {
        return allowed.iter().any(|s| s == origin);
    }
    // Cookie mutations must prove origin even when Fetch Metadata is missing.
    !(cookie && unsafe_method)
}

pub async fn perimeter(State(s): State<AppState>, req: Request<Body>, next: Next) -> Response {
    let request_id = uuid::Uuid::new_v4().simple().to_string();
    let api = req.uri().path().starts_with("/api/");
    let health = matches!(req.uri().path(), "/api/health" | "/api/health/live")
        && req.method() == Method::GET;
    let start = Instant::now();
    let mut response = async {
        let _permit = match s.security.slots.clone().try_acquire_owned() {
            Ok(v) => v,
            Err(_) => {
                return reject(
                    StatusCode::SERVICE_UNAVAILABLE,
                    "Сервис занят. Повторите позже",
                );
            }
        };
        if req.uri().to_string().len() > 4096
            || req
                .headers()
                .iter()
                .map(|(k, v)| k.as_str().len() + v.len())
                .sum::<usize>()
                > 16_384
        {
            return reject(
                StatusCode::REQUEST_HEADER_FIELDS_TOO_LARGE,
                "Заголовки запроса слишком велики",
            );
        }
        if !health
            && !req
                .headers()
                .get(header::HOST)
                .and_then(|h| h.to_str().ok())
                .is_some_and(|host| {
                    s.security
                        .hosts
                        .iter()
                        .any(|h| h.eq_ignore_ascii_case(host))
                })
        {
            return reject(StatusCode::MISDIRECTED_REQUEST, "Неизвестный адрес сервиса");
        }
        if api && !health {
            let unsafe_method =
                !matches!(*req.method(), Method::GET | Method::HEAD | Method::OPTIONS);
            let origin = req
                .headers()
                .get(header::ORIGIN)
                .and_then(|h| h.to_str().ok());
            let fetch = req
                .headers()
                .get("sec-fetch-site")
                .and_then(|h| h.to_str().ok());
            // OIDC is an intentional top-level return from an external site.
            // The exact handler verifies a one-time browser-binding cookie,
            // state, PKCE, nonce and signed token; all other paths retain CSRF.
            let oidc_return = req.method() == Method::GET
                && req.uri().path() == "/api/intelligence/assessment/oidc/callback"
                && req
                    .headers()
                    .get("sec-fetch-mode")
                    .is_some_and(|v| v == "navigate")
                && req
                    .headers()
                    .get("sec-fetch-dest")
                    .is_some_and(|v| v == "document");
            if !oidc_return
                && !origin_allowed(
                    &s.security.origins,
                    origin,
                    fetch,
                    req.headers().contains_key(header::COOKIE),
                    unsafe_method,
                )
            {
                return reject(StatusCode::FORBIDDEN, "Запрос с другого сайта запрещён");
            }
            let peer = req
                .extensions()
                .get::<ConnectInfo<SocketAddr>>()
                .map(|x| x.0.ip())
                .unwrap_or(IpAddr::from([127, 0, 0, 1]));
            let ip = if s
                .security
                .proxies
                .iter()
                .any(|network| network.contains(peer))
            {
                req.headers()
                    .get("x-forwarded-for")
                    .and_then(|h| h.to_str().ok())
                    .and_then(|v| v.parse().ok())
                    .unwrap_or(peer)
            } else {
                peer
            };
            if !s.security.allow_ip(ip) {
                return reject(
                    StatusCode::TOO_MANY_REQUESTS,
                    "Слишком много запросов с этого адреса",
                );
            }
            if req.method() == Method::POST && req.uri().path().starts_with("/api/auth/") {
                if let Err(e) = throttle(&s, &format!("auth-ip:{ip}"), 120).await {
                    return e.into_response();
                }
            }
        }
        let path = req.uri().path();
        let long_ai = req.method() == Method::POST
            && (path == "/api/career-consultant"
                || path == "/api/vacancies/generate"
                || path == "/api/tasks/generate"
                || (path.starts_with("/api/tasks/") && path.ends_with("/submit")));
        let deadline = if path.starts_with("/api/dialogues") || long_ai {
            330
        } else {
            45
        };
        match tokio::time::timeout(Duration::from_secs(deadline), next.run(req)).await {
            Ok(response) => response,
            Err(_) => reject(
                StatusCode::REQUEST_TIMEOUT,
                "Время обработки запроса истекло",
            ),
        }
    }
    .await;
    let h = response.headers_mut();
    if api {
        h.insert(
            header::CACHE_CONTROL,
            HeaderValue::from_static("private, no-store"),
        );
    }
    h.insert("x-request-id", HeaderValue::from_str(&request_id).unwrap());
    h.insert(
        "cross-origin-resource-policy",
        HeaderValue::from_static("same-origin"),
    );
    h.insert(
        "cross-origin-opener-policy",
        HeaderValue::from_static("same-origin"),
    );
    h.insert(
        "permissions-policy",
        HeaderValue::from_static("camera=(), microphone=(), geolocation=(), payment=()"),
    );
    h.insert(
        header::REFERRER_POLICY,
        HeaderValue::from_static("no-referrer"),
    );
    h.insert(header::CONTENT_SECURITY_POLICY, HeaderValue::from_static("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; frame-src 'self' blob:; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"));
    if s.security.production {
        h.insert(
            header::STRICT_TRANSPORT_SECURITY,
            HeaderValue::from_static("max-age=31536000"),
        );
    }
    if response.status() == StatusCode::TOO_MANY_REQUESTS {
        response
            .headers_mut()
            .insert(header::RETRY_AFTER, HeaderValue::from_static("900"));
    }
    tracing::info!(
        request_id,
        status = response.status().as_u16(),
        elapsed_ms = start.elapsed().as_millis(),
        "http_request"
    );
    response
}

pub async fn maintenance(s: AppState) {
    loop {
        for query in [
            "DELETE FROM sessions WHERE expires_at<now()",
            "DELETE FROM email_tokens WHERE expires_at<now()",
            "DELETE FROM password_reset_tokens WHERE expires_at<now()",
            "DELETE FROM auth_throttle WHERE window_start<now()-interval '1 day'",
        ] {
            if let Err(e) = sqlx::query(query).execute(&s.db).await {
                tracing::warn!(error_type=?e.as_database_error().and_then(|v| v.code()), "security_cleanup_failed");
            }
        }
        if let Ok(keys) = sqlx::query_scalar::<_, String>(
            "SELECT storage_key FROM file_deletions ORDER BY queued_at LIMIT 50",
        )
        .fetch_all(&s.db)
        .await
        {
            for key in keys {
                if !key.starts_with('D')
                    || key.contains('/')
                    || key.contains('\\')
                    || key.contains("..")
                {
                    continue;
                }
                let referenced: bool = sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM documents WHERE storage_key=$1 OR result->>'output_key'=$1)").bind(&key).fetch_one(&s.db).await.unwrap_or(true);
                if referenced {
                    continue;
                }
                let removed = match tokio::fs::remove_file(s.storage.join(&key)).await {
                    Ok(()) => true,
                    Err(e) => e.kind() == std::io::ErrorKind::NotFound,
                };
                if removed {
                    let _ = sqlx::query("DELETE FROM file_deletions WHERE storage_key=$1")
                        .bind(&key)
                        .execute(&s.db)
                        .await;
                }
            }
        }
        tokio::time::sleep(Duration::from_secs(30)).await;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn trusted_proxy_cidr_respects_network_and_family() {
        let network: ProxyNetwork = "10.42.0.0/16".parse().unwrap();
        assert!(network.contains("10.42.99.1".parse().unwrap()));
        assert!(!network.contains("10.43.0.1".parse().unwrap()));
        assert!(!network.contains("::1".parse().unwrap()));
        assert!("10.0.0.1/33".parse::<ProxyNetwork>().is_err());
        let single: ProxyNetwork = "127.0.0.1".parse().unwrap();
        assert!(single.contains("127.0.0.1".parse().unwrap()));
        assert!(!single.contains("127.0.0.2".parse().unwrap()));
    }
    #[test]
    fn csrf_requires_exact_configured_origin_for_cookie_writes() {
        let origins = vec!["https://fsp.example".into()];
        assert!(origin_allowed(
            &origins,
            Some("https://fsp.example"),
            Some("same-origin"),
            true,
            true
        ));
        for value in [
            "null",
            "https://fsp.example.evil.test",
            "http://fsp.example",
            "https://sub.fsp.example",
        ] {
            assert!(!origin_allowed(&origins, Some(value), None, true, true));
        }
        assert!(!origin_allowed(&origins, None, None, true, true));
        assert!(!origin_allowed(
            &origins,
            Some("https://fsp.example"),
            Some("cross-site"),
            true,
            false
        ));
        assert!(origin_allowed(&origins, None, None, false, true));
    }
}
