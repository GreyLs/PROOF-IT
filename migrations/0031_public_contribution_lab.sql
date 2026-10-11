CREATE TABLE intelligence.github_challenges (
 user_id text PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
 github_id bigint NOT NULL, login text NOT NULL, nonce_hash text NOT NULL,
 expires_at timestamptz NOT NULL, consumed_at timestamptz
);
CREATE TABLE intelligence.github_accounts (
 user_id text PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
 github_id bigint NOT NULL UNIQUE, login text NOT NULL,
 proof_url text NOT NULL, verified_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE intelligence.github_defenses (
 id text PRIMARY KEY, user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 resume_id text NOT NULL REFERENCES resume_profiles(id) ON DELETE CASCADE,
 specialization text NOT NULL, target_grade text NOT NULL,
 repository text NOT NULL, pr_number integer NOT NULL, head_sha text NOT NULL,
 artifact_digest text NOT NULL, snapshot jsonb NOT NULL, questions jsonb NOT NULL,
 answers jsonb NOT NULL DEFAULT '{}', revision integer NOT NULL DEFAULT 0,
 status text NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','submitted','reviewed','revision_changed')),
 reviewer_id text REFERENCES users(id) ON DELETE SET NULL, review jsonb,
 created_at timestamptz NOT NULL DEFAULT now(), submitted_at timestamptz, reviewed_at timestamptz,
 UNIQUE(user_id,resume_id,repository,pr_number,head_sha)
);
CREATE INDEX github_defense_owner_idx ON intelligence.github_defenses(user_id,created_at DESC);
ALTER TABLE qualification_certificates ADD COLUMN scope text NOT NULL DEFAULT 'role-knowledge'
 CHECK(scope IN ('role-knowledge','role-reviewed'));
CREATE TABLE intelligence.role_attestations (
 id text PRIMARY KEY, user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 defense_id text NOT NULL UNIQUE REFERENCES intelligence.github_defenses(id) ON DELETE CASCADE,
 certificate_id text REFERENCES qualification_certificates(id) ON DELETE CASCADE,
 result jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE intelligence.form_assignments (
 user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 specialization text NOT NULL, target_grade text NOT NULL, version text NOT NULL,
 variant text NOT NULL CHECK(variant IN ('A','B')), assignment_hash text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(user_id,specialization,target_grade,version)
);
CREATE TABLE intelligence.market_snapshots (
 company_id text NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
 specialization text NOT NULL, grade text NOT NULL, industry text NOT NULL,
 snapshot_date date NOT NULL DEFAULT current_date, value jsonb NOT NULL,
 PRIMARY KEY(company_id,specialization,grade,industry,snapshot_date)
);
