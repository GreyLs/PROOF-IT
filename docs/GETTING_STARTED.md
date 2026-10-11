# Подготовка и запуск

## Проверка кода без рабочей БД

В корне проекта на Windows:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt -r requirements.forecasting.txt -r requirements.intelligence.txt
cargo test --locked
.\.venv\Scripts\python.exe -m pytest -q tests/test_evidence_methods.py tests/test_professional.py tests/test_horizon_engine.py tests/test_horizon_service.py tests/test_resume_bundles.py tests/test_pdf_layout.py tests/test_employment_dates.py
Push-Location web
npm ci
npm run build
Pop-Location
node --test tests/locale-quality.mjs tests/horizon-targets.mjs tests/decision-ui.mjs
```

Rust-тест с обращением к реальной локальной языковой модели помечен `ignore`; обычный запуск его пропускает. HTTP, браузерные сценарии, OCR и sandbox-проверки требуют работающего контура и выполняются отдельно. На Linux команды используют `.venv/bin/python`; Windows-сценарий `scripts.start_local` рассчитан на `.exe`-бинарник.

## Нативный контур Windows

1. Установить PostgreSQL 17, Rust, Node.js 24, Docker Desktop и Python 3.12. Создать отдельную БД `fsp_trajectory` с выделенным пользователем. Для развёртывания с реальными данными использовать production-роли из `deploy/production-grants.sql`.
2. Создать окружение Python как выше и дополнительно установить `requirements.worker.txt`, `requirements.processor.txt`, `requirements.controller.txt`. Скопировать `.env.example` в `.env` и заполнить `DATABASE_URL`. Для локального стенда согласованно задать `BASE_URL=http://localhost:1717`, `BIND_ADDR=127.0.0.1:1717`, `FSP_DEMO_MODE=true`.
3. Собрать веб-интерфейс и `cargo build --release --locked`. Вызвать `target/release/fsp-trajectory.exe --prepare` из корня: миграции и сценарный набор подготавливаются в указанной БД.
4. Подготовить identity и запустить Keycloak:

```powershell
.\.venv\Scripts\python.exe -m scripts.provision_identity --origin http://localhost:1717
docker compose --env-file "$env:LOCALAPPDATA/Proofit/private-ingress/keycloak.env" -f deploy/keycloak.compose.yml up -d
.\.venv\Scripts\python.exe -m scripts.configure_keycloak_origin
.\.venv\Scripts\python.exe -m scripts.start_local --cpu-only
```

Для проверки открыть `http://localhost:1717`; готовность API — `/api/health`. Рабочие секреты создаются в ignored `runtime/` и `%LOCALAPPDATA%/Proofit/private-ingress`, существующие значения сохраняются. Identity и роль пользователя проверяются на сервере. Для демонстрации использовать регистрацию или отдельно выданные оператором аккаунты; опубликованного универсального пароля нет.

`--cpu-only` отключает прогрев локальных языковых моделей. PDF AI-review и генеративные помощники требуют Ollama и моделей, заданных конфигурацией. Полный стек обработки изображений требует Tesseract; исполняемые практические задания — Docker. Эти зависимости не нужны для обычной проверки математических методов.

## Docker и production

`docker-compose.yml` — базовый профиль API/БД/worker. Он не заменяет полный нативный контур intelligence, forecasting и identity. `compose.production.yml` задаёт раздельные сервисы, приватные секреты и роли БД. Подготовка файлов: `python deploy/generate_secrets.py`; затем заполнить `deploy/production.env` по примеру и SMTP-секрет. Production требует HTTPS, настоящего SMTP, отдельной БД без синтетических пользователей и согласованной identity-конфигурации.

Полный порядок, маршруты и ограничения: [08_Operations_and_API.pdf](08_Operations_and_API.pdf). Не переносить `.env` и runtime-файлы с действующего стенда в Git. Для частной демонстрации адрес передаётся отдельно.

## Мониторинг и остановка

Мониторинг подключается отдельно: установить `requirements.monitoring.txt`, затем `python -m scripts.start_monitoring`. Grafana и Prometheus слушают локальные порты; индивидуальный пароль Grafana хранится в `runtime/monitoring/grafana-password`.

Нативные процессы останавливаются `python -m scripts.stop_local`; мониторинг — `python -m scripts.stop_monitoring`. Для Docker использовать `docker compose stop` с тем же env-file и compose-файлом. Удаление volumes не является штатной остановкой.
