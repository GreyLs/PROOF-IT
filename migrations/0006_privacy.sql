ALTER TABLE users ADD COLUMN auth_epoch bigint NOT NULL DEFAULT 1;
ALTER TABLE sessions ADD COLUMN auth_epoch bigint NOT NULL DEFAULT 1;
CREATE TABLE contact_revocations (
 candidate_id text NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
 company_id text NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
 created_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(candidate_id,company_id)
);
