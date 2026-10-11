CREATE TABLE password_reset_tokens (
 token_hash text PRIMARY KEY,user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 expires_at timestamptz NOT NULL,created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX reset_user_idx ON password_reset_tokens(user_id);
CREATE TABLE mail_outbox (
 id text PRIMARY KEY,recipient text NOT NULL,purpose text NOT NULL CHECK(purpose IN ('verify','reset')),
 encrypted_body bytea NOT NULL,attempts integer NOT NULL DEFAULT 0,next_attempt_at timestamptz NOT NULL DEFAULT now(),
 lease_until timestamptz,created_at timestamptz NOT NULL DEFAULT now(),expires_at timestamptz NOT NULL
);
