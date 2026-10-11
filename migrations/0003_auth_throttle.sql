CREATE TABLE auth_throttle (
    key_hash text PRIMARY KEY,
    window_start timestamptz NOT NULL DEFAULT now(),
    hits integer NOT NULL DEFAULT 1 CHECK (hits > 0)
);
