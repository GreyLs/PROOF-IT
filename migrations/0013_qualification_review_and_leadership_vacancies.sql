-- A completed candidate test remains explainable to its author and can be
-- escalated without exposing answer keys to employers.
ALTER TABLE qualification_tests ADD COLUMN last_attempt jsonb;

CREATE TABLE qualification_expert_reviews(
 id text PRIMARY KEY,
 qualification_test_id text NOT NULL UNIQUE REFERENCES qualification_tests(id) ON DELETE CASCADE,
 candidate_id text NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
 resume_id text NOT NULL REFERENCES resume_profiles(id) ON DELETE CASCADE,
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','in_review','resolved')),
 folder_key text NOT NULL UNIQUE,
 snapshot jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 reviewed_at timestamptz,
 resolution text NOT NULL DEFAULT ''
);
CREATE INDEX qualification_expert_reviews_queue_idx ON qualification_expert_reviews(status,created_at);

-- Management roles express scope through the role itself. A vacancy for a
-- lead, head, director or C-level position deliberately has no junior/middle/
-- senior selector. Historic synthetic vacancies are normalised on migration.
ALTER TABLE vacancies DROP CONSTRAINT vacancies_grade_check;
ALTER TABLE vacancies ADD CONSTRAINT vacancies_grade_check CHECK(grade IN ('junior','middle','senior',''));
UPDATE vacancies
SET grade=''
WHERE specialization LIKE 'lead_%'
   OR specialization LIKE 'head_%'
   OR specialization LIKE 'director_%'
   OR specialization LIKE 'executive_%';
