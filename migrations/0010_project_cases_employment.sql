ALTER TABLE expert_dialogues ADD COLUMN phase text NOT NULL DEFAULT 'project' CHECK (phase IN ('project','cases','finished'));
ALTER TABLE expert_dialogues ADD COLUMN case_state jsonb NOT NULL DEFAULT '[]';
ALTER TABLE expert_dialogues ADD COLUMN project_result jsonb;
ALTER TABLE expert_dialogues ADD COLUMN case_index integer NOT NULL DEFAULT 0 CHECK(case_index BETWEEN 0 AND 3);
-- Existing completed assessments remain historical records; active old protocols cannot skip cases.
UPDATE expert_dialogues SET status='expired' WHERE status='active';
UPDATE expert_dialogues SET phase='finished' WHERE status='completed';
ALTER TABLE candidates ADD COLUMN employment_document_id text;
ALTER TABLE candidates ADD COLUMN employment_check jsonb NOT NULL DEFAULT '{"status":"not_provided"}';
ALTER TABLE candidates ADD COLUMN employment_blocked boolean NOT NULL DEFAULT false;
ALTER TABLE documents DROP CONSTRAINT documents_kind_check;
ALTER TABLE documents ADD CONSTRAINT documents_kind_check CHECK(kind IN ('resume','vacancy','profile_export','employment'));
