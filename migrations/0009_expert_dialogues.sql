CREATE TABLE expert_dialogues (
 id text PRIMARY KEY,
 candidate_id text NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
 mode text NOT NULL CHECK(mode IN ('profile','vacancy')),
 vacancy_id text REFERENCES vacancies(id) ON DELETE CASCADE,
 specialization text NOT NULL, grade text NOT NULL,
 profile_version integer NOT NULL,
 snapshot jsonb NOT NULL, messages jsonb NOT NULL DEFAULT '[]',
 evidence jsonb NOT NULL DEFAULT '[]', result jsonb,
 question_count integer NOT NULL DEFAULT 0 CHECK(question_count BETWEEN 0 AND 3),
 status text NOT NULL DEFAULT 'active' CHECK(status IN ('active','completed','expired')),
 revision integer NOT NULL DEFAULT 0,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 expires_at timestamptz NOT NULL DEFAULT now()+interval '24 hours'
);
CREATE INDEX expert_dialogues_owner_idx ON expert_dialogues(candidate_id,created_at DESC);
ALTER TABLE candidates ADD COLUMN assessment_method text NOT NULL DEFAULT 'legacy';
