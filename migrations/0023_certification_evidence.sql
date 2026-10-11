-- Bind a qualification outcome to the role actually assessed, never a mutable declaration.
ALTER TABLE qualification_tests ADD COLUMN target_specialization text;
ALTER TABLE qualification_tests ADD COLUMN target_grade text;
ALTER TABLE qualification_tests ADD COLUMN certified_grade text;
ALTER TABLE qualification_tests ADD COLUMN certified_specialization text;
ALTER TABLE qualification_tests ADD COLUMN certified_skills jsonb NOT NULL DEFAULT '[]';
ALTER TABLE qualification_tests ADD COLUMN certified_at timestamptz;
ALTER TABLE qualification_tests ADD COLUMN certified_score integer;
ALTER TABLE qualification_tests ADD COLUMN grade_changed_at timestamptz;
ALTER TABLE qualification_tests ADD COLUMN contract jsonb;
ALTER TABLE qualification_tests ADD COLUMN revision integer NOT NULL DEFAULT 0;
ALTER TABLE qualification_tests ADD COLUMN item_started_at timestamptz;
UPDATE qualification_tests q SET target_specialization=r.specialization,target_grade=r.declared_grade,
 certified_grade=CASE WHEN q.passed THEN r.declared_grade END,certified_specialization=CASE WHEN q.passed THEN r.specialization END,
 certified_at=CASE WHEN q.passed THEN q.finished_at END,certified_score=CASE WHEN q.passed THEN q.score END
 FROM resume_profiles r WHERE q.resume_id=r.id;
CREATE TABLE qualification_certificates(
 id text PRIMARY KEY, candidate_id text NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
 resume_id text NOT NULL REFERENCES resume_profiles(id) ON DELETE CASCADE,
 specialization text NOT NULL, grade text NOT NULL CHECK(grade IN ('junior','middle','senior')),
 skills jsonb NOT NULL DEFAULT '[]', assessment_version text NOT NULL,
 attempt jsonb NOT NULL, issued_at timestamptz NOT NULL DEFAULT now(),
 valid_until timestamptz NOT NULL DEFAULT now()+interval '180 days',
 revoked_at timestamptz, UNIQUE(resume_id,issued_at)
);
CREATE INDEX qualification_certificate_current_idx ON qualification_certificates(resume_id,issued_at DESC);
CREATE TABLE qualification_attempt_history(
 id text PRIMARY KEY,candidate_id text NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
 resume_id text NOT NULL REFERENCES resume_profiles(id) ON DELETE CASCADE,
 specialization text NOT NULL,grade text NOT NULL,result jsonb NOT NULL,
 finished_at timestamptz NOT NULL DEFAULT now(),available_at timestamptz NOT NULL
);
CREATE INDEX qualification_attempt_scope_idx ON qualification_attempt_history(candidate_id,specialization,grade,available_at DESC);
CREATE TABLE intelligence.review_cases(
 id text PRIMARY KEY,user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 artifact_id text NOT NULL, task_key text NOT NULL, evidence jsonb NOT NULL,
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','confirmed','dismissed','challenged')),
 reviewer_id text REFERENCES users(id) ON DELETE SET NULL, decision text,
 created_at timestamptz NOT NULL DEFAULT now(),resolved_at timestamptz,
 UNIQUE(user_id,artifact_id)
);
ALTER TABLE intelligence.code_proofs ADD COLUMN task_key text NOT NULL DEFAULT '';
ALTER TABLE intelligence.code_proofs ADD COLUMN language text NOT NULL DEFAULT '';
CREATE INDEX code_proofs_scope_idx ON intelligence.code_proofs(task_key,language,created_at DESC);
CREATE TABLE intelligence.company_twins(
 company_id text PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
 value jsonb NOT NULL DEFAULT '{}',version integer NOT NULL DEFAULT 1,updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE intelligence.provider_snapshots(
 id text PRIMARY KEY,provider text NOT NULL,subject_id text NOT NULL,
 value jsonb NOT NULL,status text NOT NULL,source_url text NOT NULL,
 fetched_at timestamptz NOT NULL DEFAULT now(),UNIQUE(provider,subject_id)
);
CREATE TABLE intelligence.followups(
 id text PRIMARY KEY,user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 invitation_id text REFERENCES invitations(id) ON DELETE CASCADE,
 day integer NOT NULL CHECK(day IN (30,60,90)),due_at timestamptz NOT NULL,
 result jsonb,confirmed_by_candidate boolean NOT NULL DEFAULT false,
 confirmed_by_employer boolean NOT NULL DEFAULT false,updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(invitation_id,day)
);
-- A graph projection shared by rank retrieval and explanation. Repeated evidence
-- of one source class is capped before combining independent proof classes.
CREATE VIEW intelligence.skill_support AS
WITH raw AS (
 SELECT q.candidate_id,'cert:'||q.id AS source_id,'qualification' AS source_kind,
 s.skill,0.85*exp(-ln(2.0)*greatest(0,extract(epoch FROM(now()-q.issued_at)))/15552000.0) AS weight
 FROM qualification_certificates q CROSS JOIN LATERAL jsonb_array_elements_text(q.skills) s(skill)
 WHERE q.revoked_at IS NULL AND q.valid_until>now()
 UNION ALL
 SELECT t.candidate_id,'task:'||t.id,'execution',s.skill,
 coalesce(t.score,0)::float8/100.0*0.8*exp(-ln(2.0)*greatest(0,extract(epoch FROM(now()-t.reviewed_at)))/7776000.0)
 FROM micro_tasks t CROSS JOIN LATERAL jsonb_array_elements_text(coalesce(t.contract->'skills','[]')) s(skill)
 WHERE t.status='reviewed' AND t.score>=70
 UNION ALL
 SELECT u.subject_id,'arena:'||a.id,'execution',s.skill,
 coalesce((a.result->>'score')::float8,0)/100.0*0.8*exp(-ln(2.0)*greatest(0,extract(epoch FROM(now()-a.updated_at)))/7776000.0)
 FROM intelligence.arena_attempts a JOIN users u ON u.id=a.user_id
 CROSS JOIN LATERAL jsonb_array_elements_text(coalesce(a.contract->'skills',a.result->'skills','[]')) s(skill)
 WHERE a.status='completed' AND a.kind IN ('python','sql','typescript') AND (a.result->>'score')::float8>=70
), visible AS (
 SELECT x.* FROM raw x WHERE NOT EXISTS(
 SELECT 1 FROM intelligence.evidence_controls ec JOIN users u ON u.id=ec.user_id
 WHERE u.subject_id=x.candidate_id AND ec.evidence_id=x.source_id AND (ec.hidden OR ec.disputed))
 AND NOT EXISTS(SELECT 1 FROM intelligence.review_cases rc JOIN users u ON u.id=rc.user_id WHERE u.subject_id=x.candidate_id AND rc.artifact_id=substring(x.source_id FROM position(':' IN x.source_id)+1) AND rc.status='confirmed')
), capped AS (
 SELECT candidate_id,lower(skill) AS skill,source_kind,max(weight) AS weight FROM visible GROUP BY candidate_id,lower(skill),source_kind
)
SELECT candidate_id,skill,1-exp(sum(ln(greatest(0.001,1-weight)))) AS strength,count(*) AS independent_sources
FROM capped GROUP BY candidate_id,skill;
CREATE TABLE intelligence.passports(
 id text PRIMARY KEY,user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 digest text NOT NULL UNIQUE,certificate_ids jsonb NOT NULL,
 issued_at timestamptz NOT NULL DEFAULT now(),expires_at timestamptz NOT NULL,
 revoked_at timestamptz
);
CREATE TABLE intelligence.weekly_campaigns(
 id text PRIMARY KEY,company_id text NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
 vacancy_id text NOT NULL REFERENCES vacancies(id) ON DELETE CASCADE,
 enabled boolean NOT NULL DEFAULT true,next_run_at timestamptz NOT NULL DEFAULT now(),
 last_run_at timestamptz,created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(company_id,vacancy_id)
);
ALTER TABLE intelligence.arena_attempts ADD COLUMN ai_assisted boolean NOT NULL DEFAULT false;
ALTER TABLE intelligence.arena_attempts ADD COLUMN defense jsonb;
ALTER TABLE companies ADD COLUMN dreamjob_employer_id text;
