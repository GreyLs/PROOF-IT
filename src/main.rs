mod account;
mod api;
mod assessment;
mod auth;
mod demo;
mod cases;
mod certification;
mod config;
mod conversations;
mod db;
mod documents;
mod error;
mod evidence;
mod forecasting;
mod gateway;
mod intelligence;
mod interactions;
mod interview;
mod mail;
mod matching;
mod professional;
mod profiles;
mod providers;
mod research_lab;
mod resumes;
mod security;
mod service;
mod talantix;
mod workbench;

use axum::{
    Router,
    extract::DefaultBodyLimit,
    http::{HeaderValue, header},
    middleware,
};
use sqlx::postgres::PgPoolOptions;
use std::{sync::Arc, time::Duration};
use tower_http::{
    services::{ServeDir, ServeFile},
    set_header::SetResponseHeaderLayer,
    trace::TraceLayer,
};

#[derive(Clone)]
pub struct AppState {
    pub db: sqlx::PgPool,
    pub demo: bool,
    pub storage: Arc<std::path::PathBuf>,
    pub base_url: Arc<String>,
    pub forecast_url: Arc<String>,
    pub auth_slots: Arc<tokio::sync::Semaphore>,
    pub interview_slots: Arc<tokio::sync::Semaphore>,
    pub started: std::time::Instant,
    pub security: Arc<security::Security>,
    pub dummy_password_hash: Arc<String>,
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    dotenvy::dotenv().ok();
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "fsp_trajectory=info,tower_http=info".into()),
        )
        .init();
    let service = service::Service::from_env()?;
    let bind = std::env::var("BIND_ADDR").unwrap_or("127.0.0.1:8080".into());
    if service.is_gateway() {
        return gateway::run(bind).await;
    }
    let base_url = std::env::var("BASE_URL")
        .unwrap_or("http://localhost:8080".into())
        .trim_end_matches('/')
        .to_owned();
    let demo = std::env::var("FSP_DEMO_MODE").as_deref() == Ok("true");
    let preparing = std::env::args().any(|a| a == "--prepare" || a == "--seed");
    let security = Arc::new(security::Security::load(&base_url, demo, preparing)?);
    let db = PgPoolOptions::new()
        .max_connections(service.database_pool_limit())
        .min_connections(if service == service::Service::All { 2 } else { 1 })
        .acquire_timeout(Duration::from_secs(5))
        .after_connect(|conn, _| Box::pin(async move {
            sqlx::query("SELECT set_config('statement_timeout','15s',false),set_config('lock_timeout','5s',false),set_config('idle_in_transaction_session_timeout','30s',false),set_config('max_parallel_workers_per_gather',$1,false)")
                .bind(std::env::var("DATABASE_PARALLEL_WORKERS").unwrap_or_else(|_|"2".into())).execute(conn).await?;
            Ok(())
        }))
        .connect(&config::secret("DATABASE_URL")?)
        .await?;
    // Keep the embedded migration set current, including 0015 which restores
    // explicitly consented uploaded resumes created before per-resume
    // publication was synchronised.
    if preparing || !security.production {
        sqlx::migrate!("./migrations").run(&db).await?;
    }
    if security.production && !preparing {
        let excessive: bool = sqlx::query_scalar("SELECT r.rolsuper OR r.rolcreaterole OR r.rolcreatedb OR r.rolbypassrls OR d.datdba=r.oid OR has_schema_privilege(current_user,'public','CREATE') FROM pg_roles r JOIN pg_database d ON d.datname=current_database() WHERE r.rolname=current_user").fetch_one(&db).await?;
        anyhow::ensure!(
            !excessive,
            "Production runtime DB role must not own database/schema or have DDL/admin privileges"
        );
        let synthetic: bool = sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM users WHERE synthetic) OR EXISTS(SELECT 1 FROM candidates WHERE synthetic)").fetch_one(&db).await?;
        anyhow::ensure!(
            !synthetic,
            "Production requires a separate database without demonstration identities"
        );
    }
    let state = AppState {
        db,
        demo,
        storage: Arc::new(
            std::env::var("STORAGE_DIR")
                .unwrap_or("runtime/storage".into())
                .into(),
        ),
        base_url: Arc::new(base_url),
        forecast_url: Arc::new(
            std::env::var("FSP_FORECAST_URL")
                .unwrap_or_else(|_| "http://127.0.0.1:8090".into())
                .trim_end_matches('/')
                .to_owned(),
        ),
        auth_slots: Arc::new(tokio::sync::Semaphore::new(4)),
        interview_slots: Arc::new(tokio::sync::Semaphore::new(1)),
        started: std::time::Instant::now(),
        security,
        dummy_password_hash: Arc::new(auth::password_hash(&uuid::Uuid::new_v4().to_string())?),
    };
    tokio::fs::create_dir_all(state.storage.as_ref()).await?;
    if state.demo && !state.security.production && service.includes(service::Service::Identity) {
        demo::provision_shared(&state).await.map_err(|e| anyhow::anyhow!("Demo provisioning: {}", e.1))?;
    }
    if preparing {
        anyhow::ensure!(
            !state.security.production || !std::env::args().any(|a| a == "--seed"),
            "Production forbids synthetic seed"
        );
        if state.demo {
            db::seed(&state).await?;
        }
        return Ok(());
    }
    if service.runs_maintenance() {
        tokio::spawn(security::maintenance(state.clone()));
    }
    if service.includes(service::Service::Intelligence) {
        tokio::spawn(intelligence::dispatch(state.clone()));
        tokio::spawn(evidence::weekly_dispatch(state.clone()));
    }
    if !state.demo && service.runs_mail() {
        tokio::spawn(mail::dispatch(state.clone()));
    }
    if service.runs_talantix_dispatch() {
        tokio::spawn(talantix::dispatch(state.clone()));
    }
    let app = Router::new()
        .nest("/api", api::routes(service))
        .layer(DefaultBodyLimit::max(256 * 1024))
        .layer(tower_http::limit::RequestBodyLimitLayer::new(
            20 * 1024 * 1024,
        ))
        .layer(SetResponseHeaderLayer::if_not_present(
            header::X_CONTENT_TYPE_OPTIONS,
            HeaderValue::from_static("nosniff"),
        ))
        .layer(SetResponseHeaderLayer::if_not_present(
            header::X_FRAME_OPTIONS,
            HeaderValue::from_static("DENY"),
        ))
        .layer(SetResponseHeaderLayer::if_not_present(
            header::REFERRER_POLICY,
            HeaderValue::from_static("same-origin"),
        ))
        .layer(TraceLayer::new_for_http().make_span_with(|req: &axum::http::Request<axum::body::Body>| {
            tracing::info_span!("http_request",method=%req.method(),path=req.uri().path())
        }))
        .layer(middleware::from_fn_with_state(
            state.clone(),
            security::perimeter,
        ))
        .with_state(state);
    let app = if service.serves_ui() {
        app.fallback_service(
            ServeDir::new("web/dist").not_found_service(ServeFile::new("web/dist/index.html")),
        )
    } else {
        app
    };
    let listener = tokio::net::TcpListener::bind(&bind).await?;
    tracing::info!(address=%bind,"ФСП · Траектория запущена");
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
