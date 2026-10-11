use axum::{
    Json,
    http::StatusCode,
    response::{IntoResponse, Response},
};
use serde_json::json;

#[derive(Debug)]
pub struct AppError(pub StatusCode, pub String);
pub type Result<T> = std::result::Result<T, AppError>;
impl AppError {
    pub fn bad(s: impl Into<String>) -> Self {
        Self(StatusCode::BAD_REQUEST, s.into())
    }
    pub fn forbidden() -> Self {
        Self(
            StatusCode::FORBIDDEN,
            "Недостаточно прав для этого действия".into(),
        )
    }
    pub fn missing() -> Self {
        Self(StatusCode::NOT_FOUND, "Запись не найдена".into())
    }
    pub fn conflict(s: impl Into<String>) -> Self {
        Self(StatusCode::CONFLICT, s.into())
    }
    pub fn unavailable(s: impl Into<String>) -> Self {
        Self(StatusCode::SERVICE_UNAVAILABLE, s.into())
    }
}
impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        (
            self.0,
            Json(json!({"error":{"code":self.0.as_u16(),"message":self.1}})),
        )
            .into_response()
    }
}
impl From<sqlx::Error> for AppError {
    fn from(e: sqlx::Error) -> Self {
        if let sqlx::Error::Database(ref d) = e {
            if d.code().as_deref() == Some("23505") {
                return Self::conflict("Такая запись уже существует");
            }
        }
        tracing::error!(sqlstate=?e.as_database_error().and_then(|d| d.code()),"database failure");
        Self(
            StatusCode::INTERNAL_SERVER_ERROR,
            "Не удалось выполнить операцию. Повторите попытку.".into(),
        )
    }
}
impl From<std::io::Error> for AppError {
    fn from(e: std::io::Error) -> Self {
        tracing::error!(error=%e,"storage failure");
        Self(StatusCode::INTERNAL_SERVER_ERROR, "Ошибка хранилища".into())
    }
}
