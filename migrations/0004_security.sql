ALTER TABLE documents ADD COLUMN result_bytes bigint NOT NULL DEFAULT 0 CHECK(result_bytes>=0);
UPDATE documents SET result_bytes=coalesce(octet_length(result::text),0);
CREATE TABLE file_deletions(storage_key text PRIMARY KEY,queued_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX auth_throttle_cleanup_idx ON auth_throttle(window_start);
CREATE INDEX sessions_expiry_idx ON sessions(expires_at);
