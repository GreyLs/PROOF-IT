CREATE TABLE intelligence.professional_attempts (
 id text PRIMARY KEY,user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 specialization text NOT NULL,mode text NOT NULL CHECK(mode IN ('express','full')),
 status text NOT NULL DEFAULT 'active' CHECK(status IN ('active','completed','abandoned')),
 contract jsonb NOT NULL,result jsonb,revision integer NOT NULL DEFAULT 0,
 item_started_at timestamptz NOT NULL DEFAULT now(),created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE users ADD COLUMN is_guest boolean NOT NULL DEFAULT false;
ALTER TABLE users ADD CONSTRAINT guest_requires_demo_identity CHECK(NOT is_guest OR synthetic);
CREATE INDEX professional_owner_idx ON intelligence.professional_attempts(user_id,created_at DESC);
CREATE TABLE intelligence.professional_responses (
 attempt_id text REFERENCES intelligence.professional_attempts(id) ON DELETE CASCADE,
 item_id text NOT NULL,family text NOT NULL,topic text NOT NULL,correct boolean NOT NULL,
 expected_correct double precision NOT NULL,theta_before double precision NOT NULL,
 elapsed_ms bigint NOT NULL,pilot boolean NOT NULL DEFAULT false,created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(attempt_id,item_id)
);
CREATE INDEX professional_item_idx ON intelligence.professional_responses(item_id);
CREATE TABLE intelligence.item_drafts (
 id text PRIMARY KEY,author_id text REFERENCES users(id) ON DELETE SET NULL,
 reviewer_id text REFERENCES users(id) ON DELETE SET NULL,
 specialization text NOT NULL,content jsonb NOT NULL,
 status text NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','pilot','active','rejected','quarantined')),
 calibration jsonb,review_note text NOT NULL DEFAULT '',version integer NOT NULL DEFAULT 1,
 created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE intelligence.assessment_experts (
 user_id text PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
 approved boolean NOT NULL DEFAULT false,created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE intelligence.integrity_signals (
 id bigserial PRIMARY KEY,user_id text REFERENCES users(id) ON DELETE CASCADE,
 attempt_id text REFERENCES intelligence.professional_attempts(id) ON DELETE CASCADE,
 kind text NOT NULL,count integer NOT NULL DEFAULT 1 CHECK(count BETWEEN 1 AND 20),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX integrity_owner_idx ON intelligence.integrity_signals(user_id,attempt_id);
CREATE TABLE intelligence.oidc_states (
 state_hash text PRIMARY KEY,user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 nonce text NOT NULL,verifier text NOT NULL,expires_at timestamptz NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE intelligence.oidc_links (
 user_id text PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
 issuer text NOT NULL,subject text NOT NULL,linked_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(issuer,subject)
);
CREATE TABLE intelligence.code_proofs (
 artifact_id text PRIMARY KEY,user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 fingerprint jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT now()
);
