CREATE TABLE users (
 id text PRIMARY KEY, email text UNIQUE NOT NULL, password_hash text NOT NULL,
 role text NOT NULL CHECK(role IN ('candidate','employer')), email_verified boolean NOT NULL DEFAULT false,
 subject_id text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), synthetic boolean NOT NULL DEFAULT false
);
CREATE TABLE sessions (
 token_hash text PRIMARY KEY, user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 expires_at timestamptz NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX sessions_user_idx ON sessions(user_id);
CREATE TABLE email_tokens(token_hash text PRIMARY KEY,user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,expires_at timestamptz NOT NULL);
CREATE TABLE companies(
 id text PRIMARY KEY,name text NOT NULL,description text NOT NULL DEFAULT '',industry text NOT NULL DEFAULT 'ИТ',
 contact text NOT NULL DEFAULT '',verification_status text NOT NULL DEFAULT 'unverified',synthetic boolean NOT NULL DEFAULT false,
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE candidates(
 id text PRIMARY KEY, display_name text NOT NULL, full_name text NOT NULL DEFAULT '',email text NOT NULL DEFAULT '',phone text NOT NULL DEFAULT '',
 specialization text NOT NULL DEFAULT '',declared_grade text NOT NULL DEFAULT 'junior',confirmed_grade text,
 industry text NOT NULL DEFAULT 'ИТ',experience_years double precision NOT NULL DEFAULT 0 CHECK(experience_years>=0 AND experience_years<=80),
 skills text[] NOT NULL DEFAULT '{}',soft_skills text[] NOT NULL DEFAULT '{}',about text NOT NULL DEFAULT '',
 expected_salary integer NOT NULL DEFAULT 0 CHECK(expected_salary>=0),work_format text NOT NULL DEFAULT 'удалённо',
 visibility text NOT NULL DEFAULT 'private' CHECK(visibility IN ('private','employer_searchable')),
 consent_processing boolean NOT NULL DEFAULT false,consent_publication boolean NOT NULL DEFAULT false,
 test_score integer NOT NULL DEFAULT 0 CHECK(test_score BETWEEN 0 AND 100),test_valid_until timestamptz,
 grade_changed_at timestamptz,profile_updated_at timestamptz NOT NULL DEFAULT now(),
 fsp_id text,fsp_status text NOT NULL DEFAULT 'not_linked',fsp_score integer NOT NULL DEFAULT 0,
 achievements jsonb NOT NULL DEFAULT '[]',synthetic boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now(),version integer NOT NULL DEFAULT 1,
 CHECK(confirmed_grade IS NULL OR confirmed_grade IN ('junior','middle','senior')),
 CHECK(visibility='private' OR (consent_processing AND consent_publication))
);
CREATE INDEX candidates_category_idx ON candidates(specialization,confirmed_grade,test_score DESC) WHERE visibility='employer_searchable';
CREATE INDEX candidates_skills_idx ON candidates USING gin(skills);
CREATE TABLE vacancies(
 id text PRIMARY KEY,company_id text NOT NULL REFERENCES companies(id),title text NOT NULL,
 description text NOT NULL DEFAULT '',specialization text NOT NULL,grade text NOT NULL CHECK(grade IN ('junior','middle','senior')),
 skills text[] NOT NULL DEFAULT '{}',salary_from integer NOT NULL CHECK(salary_from>0),salary_to integer NOT NULL,
 currency text NOT NULL DEFAULT 'RUB' CHECK(currency='RUB'),work_format text NOT NULL DEFAULT 'гибрид',
 status text NOT NULL DEFAULT 'published' CHECK(status IN ('draft','published','closed')),
 origin text NOT NULL DEFAULT 'employer',source_ref text NOT NULL DEFAULT '',synthetic boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),CHECK(salary_to>=salary_from)
);
CREATE INDEX vacancies_category_idx ON vacancies(specialization,grade,status);
CREATE TABLE invitations(
 id text PRIMARY KEY,company_id text NOT NULL REFERENCES companies(id),candidate_id text NOT NULL REFERENCES candidates(id),vacancy_id text REFERENCES vacancies(id),
 title text NOT NULL,description text NOT NULL,salary_from integer NOT NULL CHECK(salary_from>0),salary_to integer NOT NULL,
 contact text NOT NULL,company_name text NOT NULL,currency text NOT NULL DEFAULT 'RUB' CHECK(currency='RUB'),
 status text NOT NULL DEFAULT 'sent' CHECK(status IN ('sent','viewed','accepted','declined')),
 created_at timestamptz NOT NULL DEFAULT now(),responded_at timestamptz,synthetic boolean NOT NULL DEFAULT false,
 idempotency_key text NOT NULL,CHECK(salary_to>=salary_from),UNIQUE(company_id,idempotency_key)
);
CREATE INDEX invitation_company_idx ON invitations(company_id,created_at DESC);
CREATE INDEX invitation_candidate_idx ON invitations(candidate_id,created_at DESC);
CREATE TABLE applications(
 id text PRIMARY KEY,vacancy_id text NOT NULL REFERENCES vacancies(id),candidate_id text NOT NULL REFERENCES candidates(id),
 status text NOT NULL DEFAULT 'sent' CHECK(status IN ('sent','viewed','interview','rejected','withdrawn')),
 message text NOT NULL DEFAULT '',created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(vacancy_id,candidate_id)
);
CREATE TABLE assessments(
 id text PRIMARY KEY,candidate_id text NOT NULL REFERENCES candidates(id),specialization text NOT NULL,grade text NOT NULL,
 blueprint_version text NOT NULL,seed text NOT NULL,items jsonb NOT NULL,answers jsonb,
 status text NOT NULL DEFAULT 'in_progress' CHECK(status IN ('in_progress','passed','failed','expired','completed_seed')),
 score integer,feedback jsonb,created_at timestamptz NOT NULL DEFAULT now(),expires_at timestamptz NOT NULL DEFAULT now()+interval '45 minutes',
 finished_at timestamptz,synthetic boolean NOT NULL DEFAULT false
);
CREATE INDEX assessment_candidate_idx ON assessments(candidate_id,created_at DESC);
CREATE TABLE micro_tasks(
 id text PRIMARY KEY,company_id text NOT NULL REFERENCES companies(id),candidate_id text NOT NULL REFERENCES candidates(id),
 title text NOT NULL,prompt text NOT NULL,response text,feedback text,score integer CHECK(score BETWEEN 0 AND 100),
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','submitted','reviewed')),
 created_at timestamptz NOT NULL DEFAULT now(),submitted_at timestamptz,reviewed_at timestamptz
);
CREATE INDEX micro_tasks_candidate_idx ON micro_tasks(candidate_id,created_at DESC);
CREATE TABLE documents(
 id text PRIMARY KEY,user_id text NOT NULL REFERENCES users(id),kind text NOT NULL CHECK(kind IN ('resume','vacancy','profile_export')),
 filename text NOT NULL,sha256 text NOT NULL,storage_key text NOT NULL,bytes bigint NOT NULL,
 status text NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','processing','review','completed','failed')),
 progress integer NOT NULL DEFAULT 0,result jsonb,error text,attempts integer NOT NULL DEFAULT 0,
 lease_until timestamptz,worker_id text,next_attempt_at timestamptz NOT NULL DEFAULT now(),
 created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(user_id,sha256,kind)
);
CREATE INDEX documents_queue_idx ON documents(status,next_attempt_at,created_at);
CREATE INDEX documents_user_idx ON documents(user_id,created_at DESC);
CREATE TABLE saved_searches(
 id text PRIMARY KEY,company_id text NOT NULL REFERENCES companies(id),name text NOT NULL,query jsonb NOT NULL,
 candidate_ids text[] NOT NULL DEFAULT '{}',created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE audit_events(id bigserial PRIMARY KEY,actor_id text NOT NULL,action text NOT NULL,entity_id text NOT NULL,details jsonb NOT NULL DEFAULT '{}',created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE system_meta(key text PRIMARY KEY,value jsonb NOT NULL);
