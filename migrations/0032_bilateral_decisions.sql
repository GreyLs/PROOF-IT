-- Explicit intentions are distinct from applications, offers and employment outcomes.
CREATE TABLE intelligence.bilateral_decisions(
 vacancy_id text NOT NULL REFERENCES vacancies(id) ON DELETE CASCADE,
 candidate_id text NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
 stage text NOT NULL CHECK(stage IN('vacancy','offer')),
 candidate_accepts boolean, employer_accepts boolean,
 candidate_decided_at timestamptz, employer_decided_at timestamptz,
 revision integer NOT NULL DEFAULT 0,
 PRIMARY KEY(vacancy_id,candidate_id,stage)
);
