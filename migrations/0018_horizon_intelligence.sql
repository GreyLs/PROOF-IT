-- New intelligence domain owns these tables; legacy state is read-only input.
CREATE SCHEMA IF NOT EXISTS intelligence;
CREATE TABLE intelligence.preferences (
 user_id text PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
 value jsonb NOT NULL DEFAULT '{}', updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE intelligence.evidence_controls (
 user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE, evidence_id text NOT NULL,
 hidden boolean NOT NULL DEFAULT false, disputed boolean NOT NULL DEFAULT false,
 reason text NOT NULL DEFAULT '', updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(user_id,evidence_id)
);
CREATE TABLE intelligence.decisions (
 id text PRIMARY KEY, user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 kind text NOT NULL, version text NOT NULL, features jsonb NOT NULL, result jsonb NOT NULL,
 input_hash text NOT NULL, status text NOT NULL DEFAULT 'active' CHECK(status IN ('active','disputed')),
 dispute_reason text NOT NULL DEFAULT '', created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX decisions_owner_idx ON intelligence.decisions(user_id,created_at DESC);
CREATE TABLE intelligence.jobs (
 id text PRIMARY KEY, user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 kind text NOT NULL, input jsonb NOT NULL,
 status text NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','running','done','failed')),
 result jsonb, error text, attempts integer NOT NULL DEFAULT 0,
 lease_until timestamptz, worker_id text, available_at timestamptz NOT NULL DEFAULT now(),
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 idempotency_key text NOT NULL, UNIQUE(user_id,idempotency_key)
);
CREATE INDEX jobs_dispatch_idx ON intelligence.jobs(available_at,created_at) WHERE status IN ('queued','running');
CREATE TABLE intelligence.arena_attempts (
 id text PRIMARY KEY, user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 kind text NOT NULL CHECK(kind IN ('python','sql','typescript','incident','design','review','adaptive')),
 status text NOT NULL DEFAULT 'active' CHECK(status IN ('active','completed')),
 contract jsonb NOT NULL, submission text NOT NULL DEFAULT '', result jsonb,
 revision integer NOT NULL DEFAULT 0, created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX arena_owner_idx ON intelligence.arena_attempts(user_id,created_at DESC);
CREATE TABLE intelligence.events (
 id bigserial PRIMARY KEY, user_id text REFERENCES users(id) ON DELETE CASCADE,
 topic text NOT NULL, payload jsonb NOT NULL DEFAULT '{}', created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX events_user_idx ON intelligence.events(user_id,id DESC);
CREATE INDEX resume_market_lookup_idx ON resume_profiles(specialization,declared_grade,status,visibility) INCLUDE(expected_salary);
