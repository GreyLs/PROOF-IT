use crate::{
    AppState, assessment, auth, conversations, documents, error::Result, forecasting, interactions,
    interview, matching, profiles, resumes, service::Service, talantix, workbench,
};
use axum::{
    Json, Router,
    extract::State,
    http::{StatusCode, header},
    response::{IntoResponse, Response},
    routing::{get, post, put},
};
use serde_json::{Value, json};

pub fn routes(service: Service) -> Router<AppState> {
    let mut router = Router::new().route("/health", get(health)).route(
        "/health/live",
        get(|| async { Json(json!({"status":"alive"})) }),
    );
    if service.includes(Service::Intelligence) {
        router = router.nest("/intelligence", crate::intelligence::routes());
    }
    if service.includes(Service::Platform) {
        router = router
            .route("/meta", get(meta))
            .route("/dashboard", get(dashboard))
            .route("/validation", get(validation))
            .route("/openapi.json", get(openapi));
    }
    if service.includes(Service::Identity) {
        router = router
            .route("/auth/register", post(auth::register))
            .route("/auth/demo-context", get(crate::demo::context))
            .route("/auth/verify", post(auth::verify))
            .route("/auth/login", post(auth::login))
            .route("/auth/logout", post(auth::logout))
            .route("/auth/logout-all", post(auth::logout_all))
            .route("/auth/reset-request", post(auth::request_reset))
            .route("/auth/reset-confirm", post(auth::confirm_reset))
            .route("/auth/me", get(auth::me))
            .route("/account/export", get(crate::account::export))
            .route("/account", axum::routing::delete(crate::account::delete))
            .route(
                "/account/contact-access",
                get(crate::account::grants).post(crate::account::revoke),
            );
    }
    if service.includes(Service::Talent) {
        router = router
            .route(
                "/career-consultant",
                get(workbench::career_history).post(workbench::career),
            )
            .route("/profile", get(profiles::own).put(profiles::update))
            .route("/resumes", get(resumes::list).post(resumes::create))
            .route(
                "/resumes/{id}",
                put(resumes::update).delete(resumes::remove),
            )
            .route("/resumes/{id}/test", get(crate::certification::get))
            .route(
                "/resumes/{id}/test/start",
                post(crate::certification::start),
            )
            .route(
                "/resumes/{id}/test/submit",
                post(crate::certification::submit),
            )
            .route(
                "/resumes/{id}/test/expert-review",
                post(resumes::test_dispute),
            )
            .route(
                "/forecasts/job-search/{id}",
                get(forecasting::candidate_job_search),
            )
            .route(
                "/fsp/participations",
                get(resumes::participation_list).post(resumes::participation_create),
            )
            .route(
                "/assessments",
                get(assessment::history).post(interview::retired),
            )
            .route("/assessments/{id}/submit", post(interview::retired))
            .route("/dialogues", get(interview::list).post(interview::start))
            .route("/dialogues/{id}", get(interview::get))
            .route("/dialogues/{id}/messages", post(interview::message))
            .route("/dialogues/{id}/cases", post(interview::prepare_cases));
    }
    if service.includes(Service::Recruitment) {
        router = router
            .route("/notifications", get(workbench::notifications))
            .route("/notifications/{id}/read", post(workbench::read_notice))
            .route("/vacancies/generate", post(workbench::vacancy_draft))
            .route(
                "/vacancies/bulk",
                post(workbench::bulk_vacancies)
                    .layer(axum::extract::DefaultBodyLimit::max(1024 * 1024)),
            )
            .route("/vacancies/{id}/market", get(workbench::vacancy_market))
            .route(
                "/vacancies/{id}/task-recipients",
                get(workbench::task_recipients),
            )
            .route("/tasks/generate", post(workbench::generate_task))
            .route("/tasks/dispatch", post(workbench::dispatch_task))
            .route("/tasks/{id}/decision", put(workbench::task_decide))
            .route("/tasks/{id}/run", post(workbench::task_run))
            .route("/tasks/{id}/submit", post(workbench::task_submit))
            .route("/company", put(profiles::company_update))
            .route("/candidates", get(matching::search))
            .route("/candidates/{id}", get(matching::detail))
            .route("/saved-searches", get(matching::saved).post(matching::save))
            .route(
                "/invitations",
                get(interactions::invitations).post(interactions::invite),
            )
            .route("/invitations/{id}", put(interactions::respond))
            .route(
                "/vacancies",
                get(interactions::vacancies).post(interactions::vacancy_create),
            )
            .route("/vacancies/recommended", get(interactions::recommendations))
            .route("/forecasts/vacancy/{id}", get(forecasting::vacancy_fill))
            .route("/vacancies/{id}", put(interactions::vacancy_update))
            .route("/vacancies/{id}/apply", post(interactions::apply))
            .route("/applications", get(interactions::applications))
            .route("/applications/{id}", put(interactions::application_status))
            .route("/conversations", get(conversations::list))
            .route("/conversations/{id}", get(conversations::get))
            .route("/conversations/{id}/messages", post(conversations::message))
            .route("/conversations/{id}/read", post(conversations::mark_read))
            .route(
                "/tasks",
                get(workbench::task_list).post(interactions::task_create),
            )
            .route("/tasks/{id}", put(interactions::task_respond));
    }
    if service.includes(Service::Documents) {
        router = router
            .route(
                "/documents",
                get(documents::list)
                    .post(documents::upload)
                    .layer(axum::extract::DefaultBodyLimit::max(20 * 1024 * 1024)),
            )
            .route("/documents/export-profile", post(documents::export_profile))
            .route(
                "/documents/{id}",
                get(documents::get)
                    .put(documents::review)
                    .delete(documents::delete),
            )
            .route("/documents/{id}/retry", post(documents::retry))
            .route("/documents/{id}/file", get(documents::original));
    }
    if service.includes(Service::Integrations) {
        router = router
            .route(
                "/integrations/talantix",
                get(talantix::status)
                    .put(talantix::connect)
                    .delete(talantix::disconnect),
            )
            .route("/integrations/talantix/catalogue", get(talantix::catalogue))
            .route("/integrations/talantix/source", put(talantix::set_source))
            .route(
                "/vacancies/{id}/integrations/talantix",
                put(talantix::map_vacancy),
            );
    }
    router
}
async fn health(State(s): State<AppState>) -> Result<Json<Value>> {
    let _: i32 = sqlx::query_scalar("SELECT 1").fetch_one(&s.db).await?;
    Ok(Json(
        json!({"status":"ok","version":env!("CARGO_PKG_VERSION"),"uptime_seconds":s.started.elapsed().as_secs()}),
    ))
}
async fn meta(State(s): State<AppState>) -> Json<Value> {
    Json(
        json!({"name":"ПРУФ-ИТ","demo":s.demo,"specializations":matching::taxonomy(),"grades":["junior","middle","senior"],"upload_limit_mb":20,"max_pages":40,"grade_change_cooldown_days":90}),
    )
}
async fn dashboard(State(s): State<AppState>, actor: auth::Actor) -> Result<Json<Value>> {
    // The inventory chart is an employer feature. Reuse its grouped counts
    // for the total so eligibility is evaluated once, in one snapshot.
    let categories:Vec<Value>=if actor.role=="employer" {
        sqlx::query_scalar("SELECT jsonb_build_object('specialization',r.specialization,'grade',r.confirmed_grade,'count',count(*)) FROM intelligence.resume_category_evidence r WHERE r.employer_eligible GROUP BY r.specialization,r.confirmed_grade ORDER BY r.specialization,r.confirmed_grade").fetch_all(&s.db).await?
    } else {vec![]};
    let candidate_count:i64=categories.iter().map(|v|v["count"].as_i64().unwrap_or(0)).sum();
    let stats: Value = if actor.role == "employer" {
        sqlx::query_scalar("SELECT jsonb_build_object('candidates',$2::bigint,'invitations',(SELECT count(*) FROM invitations WHERE company_id=$1),'accepted',(SELECT count(*) FROM invitations WHERE company_id=$1 AND status='accepted'),'vacancies',(SELECT count(*) FROM vacancies WHERE company_id=$1 AND status='published'))").bind(&actor.subject_id).bind(candidate_count).fetch_one(&s.db).await?
    } else {
        sqlx::query_scalar("SELECT jsonb_build_object('invitations',(SELECT count(*) FROM invitations WHERE candidate_id=$1),'new_invitations',(SELECT count(*) FROM invitations WHERE candidate_id=$1 AND status='sent'),'applications',(SELECT count(*) FROM applications WHERE candidate_id=$1),'tasks',(SELECT count(*) FROM micro_tasks WHERE candidate_id=$1 AND status='pending'))").bind(&actor.subject_id).fetch_one(&s.db).await?
    };
    Ok(Json(
        json!({"stats":stats,"categories":categories,"demo":s.demo}),
    ))
}
async fn validation(_actor: auth::Actor) -> Json<Value> {
    let audit = tokio::fs::read_to_string("validation/reports/current/data-audit.json")
        .await
        .ok()
        .and_then(|s| serde_json::from_str::<Value>(&s).ok());
    let benchmark = tokio::fs::read_to_string("validation/reports/current/employer-ranking.json")
        .await
        .ok()
        .and_then(|s| serde_json::from_str::<Value>(&s).ok());
    let load = tokio::fs::read_to_string("validation/reports/current/performance.json")
        .await
        .ok()
        .and_then(|s| serde_json::from_str::<Value>(&s).ok());
    Json(
        json!({"audit":audit,"benchmark":benchmark,"load":load,"limits":["Стенд содержит демонстрационные профили и результаты.","Benchmark проверяет контролируемые правила, а не рыночное качество найма.","Надёжность шкалы тестирования требует независимого пилота."]}),
    )
}
async fn openapi() -> Response {
    match tokio::fs::read("data/contracts/openapi.json").await {
        Ok(v) => ([(header::CONTENT_TYPE, "application/json")], v).into_response(),
        Err(_) => (
            StatusCode::SERVICE_UNAVAILABLE,
            "API specification is being generated",
        )
            .into_response(),
    }
}
