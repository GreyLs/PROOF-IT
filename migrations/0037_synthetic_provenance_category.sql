-- Imported synthetic ground truth is a distinct evidence class, not a
-- human certificate. Original imports have actual completed_seed history;
-- authored extensions use the server-owned synthetic_scenario marker.
-- One fail-closed category projection for discovery and decision tools.
-- A declared grade is never promoted to an assessed grade. A later failed
-- attempt does not erase a still-valid certificate; review signals alone
-- are not findings. Withheld/revoked certificates cannot resurrect a legacy
-- snapshot. Historical imports remain explicitly labelled synthetic.
CREATE OR REPLACE VIEW intelligence.resume_category_evidence AS
WITH profiles AS (
 SELECT candidate_id,id,target_position,specialization,declared_grade,
        experience_years,skills,expected_salary,work_format,visibility,status
 FROM resume_profiles
 UNION ALL
 SELECT c.id,'Rlegacy_'||c.id,coalesce(nullif(c.specialization,''),'IT specialist'),
        c.specialization,c.declared_grade,c.experience_years,c.skills,
        c.expected_salary,c.work_format,c.visibility,
        CASE WHEN c.visibility='employer_searchable' THEN 'published' ELSE 'draft' END
 FROM candidates c
 WHERE NOT EXISTS(SELECT 1 FROM resume_profiles r WHERE r.candidate_id=c.id)
), assessed AS (
 SELECT r.*,proof.grade AS confirmed_grade,proof.evidence AS grade_evidence,
        coalesce(proof.score,0) AS test_score,proof.method AS assessment_method,
        proof.valid_until AS test_valid_until,proof.scope AS category_scope,
        proof.id AS category_proof_id,
        coalesce(proof.evidence='qualification_test',false) AS qualification_passed,
        (r.visibility='employer_searchable' AND r.status='published'
         AND c.consent_processing AND c.consent_publication
         AND NOT c.employment_blocked AND proof.grade IS NOT NULL) AS employer_eligible
 FROM profiles r JOIN candidates c ON c.id=r.candidate_id
 LEFT JOIN qualification_tests q ON q.resume_id=r.id
 LEFT JOIN LATERAL (
   SELECT * FROM (
     SELECT qc.grade,'qualification_test'::text AS evidence,
            CASE WHEN qc.scope='role-reviewed' AND q.certified_grade=qc.grade
                   AND q.certified_specialization=qc.specialization
                 THEN coalesce(q.certified_score,0)
                 ELSE coalesce(qc.attempt->>'score','0')::numeric::integer END AS score,
            qc.assessment_version AS method,qc.valid_until,qc.scope,qc.id,
            qc.issued_at,3 AS priority
     FROM qualification_certificates qc
     WHERE qc.resume_id=r.id AND qc.candidate_id=c.id
       AND qc.specialization=r.specialization AND qc.revoked_at IS NULL
       AND qc.issued_at<=now() AND qc.valid_until>now()
       AND NOT EXISTS(SELECT 1 FROM intelligence.evidence_controls ec JOIN users u ON u.id=ec.user_id
          WHERE u.subject_id=c.id AND ec.evidence_id='cert:'||qc.id AND (ec.hidden OR ec.disputed))
       AND NOT EXISTS(SELECT 1 FROM intelligence.review_cases rc JOIN users u ON u.id=rc.user_id
          WHERE u.subject_id=c.id AND rc.artifact_id IN(qc.id,r.id) AND rc.established_violation)
     UNION ALL
     SELECT q.certified_grade,'qualification_test',coalesce(q.certified_score,0),
            'certification-3.0.0',q.certified_at+interval '180 days','role-knowledge',
            'historical:'||r.id,q.certified_at,2
     WHERE q.certified_grade IN('junior','middle','senior')
       AND q.certified_specialization=r.specialization
       AND q.certified_at<=now() AND q.certified_at>now()-interval '180 days'
       AND NOT EXISTS(SELECT 1 FROM qualification_certificates qc WHERE qc.resume_id=r.id)
       AND NOT EXISTS(SELECT 1 FROM intelligence.review_cases rc JOIN users u ON u.id=rc.user_id
          WHERE u.subject_id=c.id AND rc.artifact_id=r.id AND rc.established_violation)
       AND NOT EXISTS(SELECT 1 FROM intelligence.evidence_controls ec JOIN users u ON u.id=ec.user_id
          WHERE u.subject_id=c.id AND ec.evidence_id='historical:'||r.id AND (ec.hidden OR ec.disputed))
     UNION ALL
     SELECT c.confirmed_grade,
            CASE WHEN c.synthetic THEN 'synthetic_scenario' ELSE 'expert_dialogue' END,
            c.test_score,CASE WHEN c.synthetic THEN 'synthetic_scenario' ELSE c.assessment_method END,c.test_valid_until,
            CASE WHEN c.synthetic THEN 'synthetic-scenario' ELSE 'expert-dialogue' END,
            'legacy:'||c.id,c.profile_updated_at,1
     WHERE q.resume_id IS NULL AND c.specialization=r.specialization
       AND c.confirmed_grade IN('junior','middle','senior') AND c.test_valid_until>now()
       AND NOT EXISTS(SELECT 1 FROM qualification_certificates qc WHERE qc.resume_id=r.id)
       AND ((c.synthetic AND (c.assessment_method='synthetic_scenario' OR EXISTS(
          SELECT 1 FROM assessments a WHERE a.candidate_id=c.id AND a.synthetic
          AND a.status='completed_seed' AND a.specialization=r.specialization AND a.grade=c.confirmed_grade)))
        OR (c.assessment_method LIKE 'expert-dialogue%' AND EXISTS(
          SELECT 1 FROM expert_dialogues d WHERE d.candidate_id=c.id AND d.mode='profile'
          AND d.specialization=r.specialization AND d.grade=c.confirmed_grade
          AND d.status='completed' AND d.result->>'decision'='supported'
          AND d.updated_at>now()-interval '90 days')))
       AND NOT EXISTS(SELECT 1 FROM intelligence.review_cases rc JOIN users u ON u.id=rc.user_id
          WHERE u.subject_id=c.id AND rc.artifact_id IN(r.id,'legacy:'||c.id) AND rc.established_violation)
   ) available ORDER BY priority DESC,issued_at DESC,id DESC LIMIT 1
 ) proof ON true
)
SELECT * FROM assessed;
