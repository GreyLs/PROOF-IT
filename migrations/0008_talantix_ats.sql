-- Per-employer credentials and delivery state for the optional Talantix ATS connector.
-- Tokens are AES-GCM envelopes; plaintext tokens are never stored in PostgreSQL or audit logs.
CREATE TABLE ats_connections (
 company_id text PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
 provider text NOT NULL DEFAULT 'talantix' CHECK(provider='talantix'),
 status text NOT NULL DEFAULT 'connected' CHECK(status IN ('connected','reauthorize','error')),
 encrypted_access_token bytea NOT NULL,
 encrypted_refresh_token bytea,
 access_expires_at timestamptz NOT NULL,
 refresh_expires_at timestamptz,
 source_id bigint,
 last_checked_at timestamptz,
 last_error_code text,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ats_vacancy_mappings (
 company_id text NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
 vacancy_id text NOT NULL REFERENCES vacancies(id) ON DELETE CASCADE,
 provider text NOT NULL DEFAULT 'talantix' CHECK(provider='talantix'),
 external_vacancy_id bigint NOT NULL CHECK(external_vacancy_id>0),
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(company_id,vacancy_id),
 UNIQUE(company_id,provider,external_vacancy_id)
);

-- The queue deliberately uses at-most-once external submission.  An ambiguous
-- network outcome is sent to review rather than risking a duplicate person in ATS.
CREATE TABLE ats_outbox (
 id text PRIMARY KEY,
 company_id text NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
 provider text NOT NULL DEFAULT 'talantix' CHECK(provider='talantix'),
 event_type text NOT NULL CHECK(event_type IN ('application.created','invitation.accepted')),
 event_id text NOT NULL,
 candidate_id text NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
 vacancy_id text NOT NULL REFERENCES vacancies(id) ON DELETE CASCADE,
 status text NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','processing','sent','failed','needs_review','cancelled')),
 attempts integer NOT NULL DEFAULT 0 CHECK(attempts>=0),
 lease_until timestamptz,
 external_person_id bigint,
 last_error_code text,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 sent_at timestamptz,
 UNIQUE(company_id,provider,event_type,event_id)
);
CREATE INDEX ats_outbox_dispatch_idx ON ats_outbox(status,created_at) WHERE status IN ('queued','processing');
CREATE INDEX ats_outbox_company_idx ON ats_outbox(company_id,created_at DESC);
