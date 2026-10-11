-- The counterpart is an explicit capability, never a role supplied by a client.
CREATE TABLE demo_workspaces (
 id text PRIMARY KEY,
 candidate_user_id text NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
 employer_user_id text NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
 shared boolean NOT NULL DEFAULT false,
 expires_at timestamptz NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 CHECK(candidate_user_id <> employer_user_id)
);
