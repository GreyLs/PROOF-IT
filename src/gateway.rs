//! Local/API gateway for the independently deployable domain services.
//!
//! It deliberately performs no authentication or business decision.  It keeps
//! the public `/api` contract stable while the private services remain bound to
//! loopback (or to an internal container network in production).  Every domain
//! service repeats the normal perimeter/auth checks, so the gateway is not a
//! security boundary that can accidentally grant access.
use axum::{
    Router,
    body::{Body, to_bytes},
    extract::{ConnectInfo, Request, State},
    http::{HeaderValue, StatusCode},
    response::Response,
    routing::any,
};
use std::{collections::HashMap, sync::Arc, time::Duration};
use tower_http::{
    services::{ServeDir, ServeFile},
    set_header::SetResponseHeaderLayer,
    trace::TraceLayer,
};

const MAX_PROXY_BODY: usize = 20 * 1024 * 1024;

#[derive(Clone)]
struct GatewayState {
    client: reqwest::Client,
    targets: Arc<HashMap<&'static str, String>>,
    slots: Arc<tokio::sync::Semaphore>,
    upload_slots: Arc<tokio::sync::Semaphore>,
    failures: Arc<std::sync::Mutex<HashMap<&'static str, (u32, std::time::Instant)>>>,
}

fn target(name: &'static str, port: u16) -> String {
    std::env::var(format!("FSP_{}_URL", name.to_ascii_uppercase()))
        .unwrap_or_else(|_| format!("http://127.0.0.1:{port}"))
        .trim_end_matches('/')
        .to_owned()
}

fn service_for(path: &str) -> &'static str {
    if path.starts_with("/identity/") {
        "keycloak"
    } else if path.starts_with("/api/intelligence/") {
        "intelligence"
    } else if path.starts_with("/api/auth/")
        || path == "/api/account"
        || path.starts_with("/api/account/")
    {
        "identity"
    } else if path.starts_with("/api/career-consultant")
        || path == "/api/profile"
        || path.starts_with("/api/resumes")
        || path.starts_with("/api/forecasts/job-search/")
        || path.starts_with("/api/fsp/")
        || path.starts_with("/api/dialogues")
        || path.starts_with("/api/assessments")
    {
        "talent"
    } else if path.starts_with("/api/documents") {
        "documents"
    } else if path.starts_with("/api/integrations/")
        || (path.starts_with("/api/vacancies/") && path.ends_with("/integrations/talantix"))
    {
        "integrations"
    } else if path.starts_with("/api/notifications")
        || path == "/api/company"
        || path.starts_with("/api/forecasts/vacancy/")
        || path.starts_with("/api/candidates")
        || path.starts_with("/api/saved-searches")
        || path.starts_with("/api/invitations")
        || path.starts_with("/api/vacancies")
        || path.starts_with("/api/applications")
        || path.starts_with("/api/conversations")
        || path.starts_with("/api/tasks")
    {
        "recruitment"
    } else {
        "platform"
    }
}

fn copy_request_headers(
    builder: reqwest::RequestBuilder,
    headers: &axum::http::HeaderMap,
) -> reqwest::RequestBuilder {
    headers.iter().fold(builder, |request, (name, value)| {
        // The backend perimeter validates the public Host, so preserve it. Only
        // connection-specific hop-by-hop headers are invalid at the next hop.
        if name == axum::http::header::CONNECTION
            || name.as_str() == "x-forwarded-for"
            || name.as_str() == "x-real-ip"
            || name.as_str() == "forwarded"
        {
            request
        } else {
            request.header(name, value)
        }
    })
}

async fn proxy(
    State(state): State<GatewayState>,
    ConnectInfo(peer): ConnectInfo<std::net::SocketAddr>,
    request: Request,
) -> Response {
    let _permit = match state.slots.try_acquire() {
        Ok(permit) => permit,
        Err(_) => {
            return response(
                StatusCode::SERVICE_UNAVAILABLE,
                "gateway is busy; retry shortly",
            );
        }
    };
    let (parts, body) = request.into_parts();
    let path = parts.uri.path();
    if path.starts_with("/identity/admin") || path.starts_with("/identity/realms/master") {
        return response(StatusCode::NOT_FOUND, "not found");
    }
    let target_name = service_for(path);
    let _upload = if path.starts_with("/api/documents") && parts.method == axum::http::Method::POST
    {
        match state.upload_slots.try_acquire() {
            Ok(permit) => Some(permit),
            Err(_) => return response(StatusCode::SERVICE_UNAVAILABLE, "upload queue is busy"),
        }
    } else {
        None
    };
    {
        let failures = state.failures.lock().unwrap_or_else(|e| e.into_inner());
        if failures
            .get(target_name)
            .is_some_and(|(count, last)| *count >= 5 && last.elapsed() < Duration::from_secs(15))
        {
            return unavailable(target_name);
        }
    }
    let Some(target) = state.targets.get(target_name) else {
        return unavailable(target_name);
    };
    let body = match to_bytes(body, MAX_PROXY_BODY).await {
        Ok(body) => body,
        Err(_) => return response(StatusCode::PAYLOAD_TOO_LARGE, "request body exceeds 20 MB"),
    };
    let uri = format!("{}{}", target, parts.uri);
    // Only an explicitly configured, loopback Cloudflare connector may supply
    // the edge-validated client address. Direct remote peers cannot spoof it.
    let client_ip = if peer.ip().is_loopback()
        && std::env::var("TRUST_CLOUDFLARE_LOCAL_TUNNEL").is_ok_and(|v| v == "true")
    {
        parts
            .headers
            .get("cf-connecting-ip")
            .and_then(|v| v.to_str().ok())
            .and_then(|v| v.parse::<std::net::IpAddr>().ok())
            .unwrap_or(peer.ip())
    } else {
        peer.ip()
    };
    let upstream = copy_request_headers(
        state.client.request(parts.method, uri).body(body),
        &parts.headers,
    )
    .header("x-forwarded-for", client_ip.to_string())
    .send()
    .await;
    let upstream = match upstream {
        Ok(response) => response,
        Err(error) => {
            let mut failures = state.failures.lock().unwrap_or_else(|e| e.into_inner());
            let entry = failures
                .entry(target_name)
                .or_insert((0, std::time::Instant::now()));
            if entry.1.elapsed() > Duration::from_secs(15) {
                entry.0 = 0;
            }
            entry.0 += 1;
            entry.1 = std::time::Instant::now();
            tracing::warn!(service=target_name, error=%error.without_url(), "domain service unavailable");
            return unavailable(target_name);
        }
    };
    state
        .failures
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .remove(target_name);
    let status = upstream.status();
    let headers = upstream.headers().clone();
    let body = match upstream.bytes().await {
        Ok(body) => body,
        Err(_) => return response(StatusCode::BAD_GATEWAY, "upstream response interrupted"),
    };
    let mut response = Response::new(Body::from(body));
    *response.status_mut() = status;
    for (name, value) in &headers {
        if name != axum::http::header::CONNECTION && name != axum::http::header::TRANSFER_ENCODING {
            if name == axum::http::header::SET_COOKIE {
                response.headers_mut().append(name, value.clone());
            } else {
                response.headers_mut().insert(name, value.clone());
            }
        }
    }
    response
}

fn response(status: StatusCode, text: &'static str) -> Response {
    Response::builder()
        .status(status)
        .body(Body::from(text))
        .expect("response")
}

fn unavailable(service: &str) -> Response {
    tracing::warn!(service, "domain service is not ready");
    response(
        StatusCode::SERVICE_UNAVAILABLE,
        "service temporarily unavailable",
    )
}

pub async fn run(bind: String) -> anyhow::Result<()> {
    let targets = HashMap::from([
        ("identity", target("identity", 8082)),
        ("talent", target("talent", 8083)),
        ("recruitment", target("recruitment", 8084)),
        ("documents", target("documents", 8085)),
        ("integrations", target("integrations", 8086)),
        ("platform", target("platform", 8087)),
        ("intelligence", target("intelligence", 8088)),
        ("keycloak", target("keycloak", 9091)),
    ]);
    let state = GatewayState {
        client: reqwest::Client::builder()
            .connect_timeout(Duration::from_secs(5))
            .timeout(Duration::from_secs(335))
            // Redirects are part of the public browser contract (e.g. OIDC).
            .redirect(reqwest::redirect::Policy::none())
            .no_proxy()
            .build()?,
        targets: Arc::new(targets),
        slots: Arc::new(tokio::sync::Semaphore::new(
            std::env::var("GATEWAY_MAX_INFLIGHT")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(256),
        )),
        upload_slots: Arc::new(tokio::sync::Semaphore::new(2)),
        failures: Arc::new(std::sync::Mutex::new(HashMap::new())),
    };
    let app = Router::new()
        .route("/api", any(proxy))
        .route("/api/{*path}", any(proxy))
        .route("/identity/{*path}", any(proxy))
        .route_service("/proofit", ServeFile::new("web/dist/index.html"))
        .fallback_service(
            ServeDir::new("web/dist").not_found_service(ServeFile::new("web/dist/index.html")),
        )
        .layer(axum::extract::DefaultBodyLimit::max(256 * 1024))
        .layer(tower_http::limit::RequestBodyLimitLayer::new(
            MAX_PROXY_BODY,
        ))
        .layer(SetResponseHeaderLayer::if_not_present(
            axum::http::header::X_CONTENT_TYPE_OPTIONS,
            HeaderValue::from_static("nosniff"),
        ))
        .layer(SetResponseHeaderLayer::if_not_present(
            axum::http::header::X_FRAME_OPTIONS,
            HeaderValue::from_static("DENY"),
        ))
        .layer(SetResponseHeaderLayer::if_not_present(
            axum::http::header::REFERRER_POLICY,
            HeaderValue::from_static("same-origin"),
        ))
        .layer(SetResponseHeaderLayer::if_not_present(
            axum::http::header::CONTENT_SECURITY_POLICY,
            HeaderValue::from_static("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; media-src 'self'; connect-src 'self'; frame-src 'self' blob:; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"),
        ))
        .layer(TraceLayer::new_for_http().make_span_with(|req: &axum::http::Request<Body>| {
            tracing::info_span!("gateway_request",method=%req.method(),path=req.uri().path())
        }))
        .with_state(state);
    let listener = tokio::net::TcpListener::bind(&bind).await?;
    tracing::info!(address=%bind, "FSP API gateway started");
    axum::serve(
        listener,
        app.into_make_service_with_connect_info::<std::net::SocketAddr>(),
    )
    .with_graceful_shutdown(async {
        let _ = tokio::signal::ctrl_c().await;
    })
    .await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::service_for;

    #[test]
    fn client_forwarding_headers_cannot_impersonate_another_ip() {
        let mut headers = axum::http::HeaderMap::new();
        headers.insert("x-forwarded-for", "203.0.113.1".parse().unwrap());
        headers.insert("x-real-ip", "203.0.113.2".parse().unwrap());
        headers.insert("forwarded", "for=203.0.113.3".parse().unwrap());
        headers.insert("host", "proof-it.example".parse().unwrap());
        let request =
            super::copy_request_headers(reqwest::Client::new().get("http://127.0.0.1/"), &headers)
                .build()
                .unwrap();
        assert!(!request.headers().contains_key("x-forwarded-for"));
        assert!(!request.headers().contains_key("x-real-ip"));
        assert!(!request.headers().contains_key("forwarded"));
        assert_eq!(request.headers()["host"], "proof-it.example");
    }

    #[test]
    fn every_public_domain_prefix_has_a_stable_owner() {
        assert_eq!(service_for("/api/auth/login"), "identity");
        assert_eq!(service_for("/api/profile"), "talent");
        assert_eq!(service_for("/api/dialogues/D1/messages"), "talent");
        assert_eq!(service_for("/api/documents/D1/file"), "documents");
        assert_eq!(service_for("/api/candidates/C1"), "recruitment");
        assert_eq!(
            service_for("/api/vacancies/V1/integrations/talantix"),
            "integrations"
        );
        assert_eq!(service_for("/api/integrations/talantix"), "integrations");
        assert_eq!(service_for("/api/openapi.json"), "platform");
    }
}
