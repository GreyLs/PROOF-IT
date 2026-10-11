FROM node:24-bookworm-slim AS web
WORKDIR /build/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM rust:1.89-bookworm AS rust
WORKDIR /build
COPY Cargo.toml Cargo.lock ./
COPY build.rs ./
COPY src/ src/
COPY migrations/ migrations/
COPY data/taxonomy.json data/question_bank.json data/interview_rubrics.json data/
COPY data/contracts/ data/contracts/
RUN cargo build --release --locked

FROM debian:bookworm-slim AS api
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && rm -rf /var/lib/apt/lists/* && useradd -m -u 10001 fsp
WORKDIR /app
COPY --from=rust /build/target/release/fsp-trajectory /usr/local/bin/fsp-trajectory
COPY --from=web /build/web/dist web/dist/
COPY data/candidates.csv data/vacancies.csv data/employers.csv data/fsp_achievements.csv data/assessment_attempts.csv data/
COPY docs/ docs/
COPY data/contracts/ data/contracts/
COPY validation/reports/current/ validation/reports/current/
RUN mkdir -p runtime/storage && chown -R fsp:fsp /app
USER fsp
ENV BIND_ADDR=0.0.0.0:8080 STORAGE_DIR=/app/runtime/storage
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s CMD curl -fsS http://127.0.0.1:8080/api/health || exit 1
ENTRYPOINT ["fsp-trajectory"]
