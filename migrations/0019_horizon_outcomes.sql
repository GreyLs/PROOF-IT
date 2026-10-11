CREATE TABLE intelligence.outcomes (
 decision_id text PRIMARY KEY REFERENCES intelligence.decisions(id) ON DELETE CASCADE,
 user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 actual_days double precision NOT NULL CHECK(actual_days>0 AND actual_days<=3650),
 predicted_days double precision, interval_low double precision, interval_high double precision,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX outcomes_owner_idx ON intelligence.outcomes(user_id,created_at DESC);
