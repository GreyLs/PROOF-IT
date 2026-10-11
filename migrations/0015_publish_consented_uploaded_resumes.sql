-- Prior versions always created a document-derived resume as private.  If the
-- candidate has already explicitly enabled discovery and both data consents,
-- restore that declared intent for a draft created from an uploaded document.
-- Manually created private resumes have no document_id and are deliberately
-- left untouched.
UPDATE resume_profiles r
SET visibility = 'employer_searchable',
    status = 'published',
    updated_at = now()
FROM candidates c
WHERE r.candidate_id = c.id
  AND r.document_id IS NOT NULL
  AND r.visibility = 'private'
  AND r.status IN ('draft', 'extracting')
  AND c.visibility = 'employer_searchable'
  AND c.consent_processing
  AND c.consent_publication
  AND NOT c.employment_blocked;
