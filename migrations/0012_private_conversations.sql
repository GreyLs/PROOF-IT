-- A private thread is created only by an invitation or an application.  The
-- immutable scope key preserves the binding even if a vacancy is later closed.
CREATE TABLE private_conversations(
 id text PRIMARY KEY,
 candidate_id text NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
 company_id text NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
 vacancy_id text REFERENCES vacancies(id) ON DELETE SET NULL,
 resume_id text REFERENCES resume_profiles(id) ON DELETE SET NULL,
 scope_key text NOT NULL,
 origin text NOT NULL CHECK(origin IN ('invitation','application')),
 vacancy_title text NOT NULL DEFAULT '',
 resume_title text NOT NULL DEFAULT '',
 created_at timestamptz NOT NULL DEFAULT now(),
 last_message_at timestamptz,
 UNIQUE(candidate_id,company_id,scope_key)
);
CREATE INDEX private_conversations_candidate_idx ON private_conversations(candidate_id,COALESCE(last_message_at,created_at) DESC);
CREATE INDEX private_conversations_company_idx ON private_conversations(company_id,COALESCE(last_message_at,created_at) DESC);

-- read_at is set only for an incoming message, when the other participant has
-- opened the thread.  The platform keeps no content in audit events.
CREATE TABLE private_conversation_messages(
 id text PRIMARY KEY,
 conversation_id text NOT NULL REFERENCES private_conversations(id) ON DELETE CASCADE,
 sender_user_id text NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
 body text NOT NULL CHECK(char_length(body) BETWEEN 1 AND 4000),
 created_at timestamptz NOT NULL DEFAULT now(),
 read_at timestamptz
);
CREATE INDEX private_conversation_messages_history_idx ON private_conversation_messages(conversation_id,created_at,id);
CREATE INDEX private_conversation_messages_unread_idx ON private_conversation_messages(conversation_id,sender_user_id) WHERE read_at IS NULL;
