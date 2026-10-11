CREATE INDEX qualification_certificate_resume_idx ON qualification_certificates(resume_id,grade,valid_until) WHERE revoked_at IS NULL;
