-- Up to three independently publishable resumes for one candidate. A resume is
-- a targeting artefact, not a second identity or a second contact record.
CREATE TABLE resume_profiles(
 id text PRIMARY KEY,
 candidate_id text NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
 document_id text UNIQUE REFERENCES documents(id) ON DELETE SET NULL,
 target_position text NOT NULL,
 specialization text NOT NULL DEFAULT '',
 declared_grade text NOT NULL DEFAULT 'junior' CHECK(declared_grade IN ('junior','middle','senior')),
 experience_years double precision NOT NULL DEFAULT 0 CHECK(experience_years>=0 AND experience_years<=80),
 skills text[] NOT NULL DEFAULT '{}', about text NOT NULL DEFAULT '',
 expected_salary integer NOT NULL DEFAULT 0 CHECK(expected_salary>=0),
 work_format text NOT NULL DEFAULT 'удалённо',
 visibility text NOT NULL DEFAULT 'private' CHECK(visibility IN ('private','employer_searchable')),
 status text NOT NULL DEFAULT 'draft' CHECK(status IN ('extracting','draft','published','archived')),
 created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),version integer NOT NULL DEFAULT 1
);
CREATE INDEX resume_profiles_candidate_idx ON resume_profiles(candidate_id,updated_at DESC);
CREATE INDEX resume_profiles_public_idx ON resume_profiles(specialization,declared_grade) WHERE visibility='employer_searchable';

-- Legacy primary profiles become the first resume. This keeps existing users in
-- the product and lets them add two independent targets without a data migration.
INSERT INTO resume_profiles(id,candidate_id,target_position,specialization,declared_grade,experience_years,skills,about,expected_salary,work_format,visibility,status,created_at,updated_at)
 SELECT 'Rlegacy_'||id,id,CASE WHEN specialization='' THEN 'ИТ-специалист' ELSE specialization END,specialization,declared_grade,experience_years,skills,about,expected_salary,work_format,visibility,CASE WHEN visibility='employer_searchable' THEN 'published' ELSE 'draft' END,created_at,profile_updated_at
 FROM candidates
 ON CONFLICT(id) DO NOTHING;

CREATE TABLE qualification_tests(
 id text PRIMARY KEY,
 resume_id text NOT NULL UNIQUE REFERENCES resume_profiles(id) ON DELETE CASCADE,
 status text NOT NULL DEFAULT 'queued' CHECK(status IN ('waiting_resume','queued','processing','ready','in_progress','passed','cooldown','failed')),
 generation_status text NOT NULL DEFAULT 'queued' CHECK(generation_status IN ('waiting','queued','processing','ready','failed')),
 questions jsonb NOT NULL DEFAULT '[]', score integer CHECK(score BETWEEN 0 AND 100),passed boolean,
 attempts integer NOT NULL DEFAULT 0 CHECK(attempts>=0),available_at timestamptz NOT NULL DEFAULT now(),started_at timestamptz,finished_at timestamptz,
 seed text NOT NULL,worker_id text,lease_until timestamptz,error text,created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX qualification_tests_queue_idx ON qualification_tests(generation_status,available_at,created_at);
-- Historical primary profiles keep their already recorded assessment. A test is
-- queued only for a newly uploaded or explicitly created resume, never in bulk.

-- A candidate may declare FSP participation. It affects matching only after an
-- FSP-backed integration or an explicitly marked demo verification confirms it.
CREATE TABLE fsp_participations(
 id text PRIMARY KEY,candidate_id text NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
 event_name text NOT NULL,discipline text NOT NULL DEFAULT '',event_date date,result text NOT NULL DEFAULT '',source_url text NOT NULL DEFAULT '',
 status text NOT NULL DEFAULT 'declared' CHECK(status IN ('declared','verified','rejected','mock_verified')),
 verified_at timestamptz,synthetic boolean NOT NULL DEFAULT false,created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(candidate_id,event_name,event_date,result)
);
CREATE INDEX fsp_participations_candidate_idx ON fsp_participations(candidate_id,status);

ALTER TABLE invitations ADD COLUMN resume_id text REFERENCES resume_profiles(id) ON DELETE SET NULL;
ALTER TABLE applications ADD COLUMN resume_id text REFERENCES resume_profiles(id) ON DELETE SET NULL;
