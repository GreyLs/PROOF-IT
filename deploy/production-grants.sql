REVOKE ALL ON ALL TABLES IN SCHEMA public FROM fsp_api,fsp_worker;
GRANT SELECT,INSERT,UPDATE,DELETE ON users,sessions,email_tokens,companies,candidates,vacancies,
 invitations,applications,assessments,micro_tasks,documents,saved_searches,system_meta,auth_throttle,
 file_deletions,password_reset_tokens,mail_outbox,contact_revocations,ats_connections,
 ats_vacancy_mappings,ats_outbox,expert_dialogues,resume_profiles,qualification_tests,
 qualification_expert_reviews,fsp_participations,private_conversations,private_conversation_messages,
 career_messages,notifications,task_drafts TO fsp_api;
GRANT SELECT,INSERT ON audit_events TO fsp_api;
GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO fsp_api;
GRANT SELECT ON documents TO fsp_worker;
GRANT SELECT(id,full_name,about,consent_processing,employment_document_id,employment_check,employment_blocked) ON candidates TO fsp_worker;
GRANT UPDATE(employment_check,employment_blocked) ON candidates TO fsp_worker;
GRANT UPDATE(status,attempts,worker_id,lease_until,progress,updated_at,error,next_attempt_at,result,result_bytes) ON documents TO fsp_worker;
GRANT SELECT,INSERT,UPDATE ON system_meta TO fsp_worker;
ALTER ROLE fsp_api SET statement_timeout='15s';
ALTER ROLE fsp_api SET lock_timeout='5s';
ALTER ROLE fsp_api SET idle_in_transaction_session_timeout='30s';
ALTER ROLE fsp_worker SET statement_timeout='15s';
REVOKE CREATE ON SCHEMA public FROM fsp_api,fsp_worker;
GRANT USAGE ON SCHEMA intelligence TO fsp_api;
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA intelligence TO fsp_api;
GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA intelligence TO fsp_api;
