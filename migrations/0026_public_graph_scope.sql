CREATE OR REPLACE VIEW intelligence.skill_support AS
WITH raw AS (
 SELECT q.candidate_id,'cert:'||q.id AS source_id,'qualification' AS source_kind,
 s.skill,0.85*exp(-ln(2.0)*greatest(0,extract(epoch FROM(now()-q.issued_at)))/15552000.0) AS weight
 FROM qualification_certificates q CROSS JOIN LATERAL jsonb_array_elements_text(q.skills) s(skill)
 WHERE q.revoked_at IS NULL AND q.valid_until>now()
 AND EXISTS(SELECT 1 FROM resume_profiles r WHERE r.id=q.resume_id AND r.visibility='employer_searchable' AND r.status='published')
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
