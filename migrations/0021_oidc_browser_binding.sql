-- A separate short-lived Lax cookie supports cross-site authorization return
-- without weakening the Strict application session cookie.
ALTER TABLE intelligence.oidc_states ADD COLUMN browser_binding_hash text NOT NULL DEFAULT '';
