CREATE TABLE intelligence.qualification_responses(
 id bigserial PRIMARY KEY,user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 resume_id text NOT NULL REFERENCES resume_profiles(id) ON DELETE CASCADE,
 item_id text NOT NULL,family text NOT NULL,topic text NOT NULL,pilot boolean NOT NULL DEFAULT false,
 correct boolean NOT NULL,theta_before double precision NOT NULL,expected_correct double precision NOT NULL,
 elapsed_ms bigint NOT NULL CHECK(elapsed_ms>=0),created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX qualification_response_item_idx ON intelligence.qualification_responses(item_id,created_at DESC);
CREATE INDEX qualification_response_family_idx ON intelligence.qualification_responses(family,created_at DESC);
