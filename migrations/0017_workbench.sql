ALTER TABLE micro_tasks DROP CONSTRAINT micro_tasks_status_check;
ALTER TABLE micro_tasks ADD CONSTRAINT micro_tasks_status_check CHECK (status IN ('pending','accepted','declined','submitted','reviewing','reviewed'));
ALTER TABLE micro_tasks ADD COLUMN vacancy_id text REFERENCES vacancies(id) ON DELETE SET NULL;
ALTER TABLE micro_tasks ADD COLUMN contract jsonb;
ALTER TABLE micro_tasks ADD COLUMN review jsonb;
ALTER TABLE micro_tasks ADD COLUMN accepted_at timestamptz;
CREATE INDEX micro_tasks_vacancy_idx ON micro_tasks(vacancy_id,status);
CREATE TABLE career_messages (
 id bigserial PRIMARY KEY, candidate_id text NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
 role text NOT NULL CHECK(role IN ('user','assistant')), content text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX career_messages_owner_idx ON career_messages(candidate_id,id DESC);
CREATE TABLE notifications (
 id text PRIMARY KEY, user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 kind text NOT NULL, title text NOT NULL, entity_id text NOT NULL, vacancy_id text,
 read_at timestamptz, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX notification_owner_idx ON notifications(user_id,created_at DESC);
CREATE INDEX vacancy_company_status_idx ON vacancies(company_id,status);
CREATE TABLE task_drafts (
 id text PRIMARY KEY, company_id text NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
 vacancy_id text NOT NULL REFERENCES vacancies(id) ON DELETE CASCADE, contract jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
