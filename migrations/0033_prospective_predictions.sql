-- Immutable predictions, frozen before either side's explicit intention.
-- Synthetic context is retained for diagnostics, excluded from real calibration.
CREATE TABLE intelligence.prospective_predictions(
 id text PRIMARY KEY,
 owner_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 vacancy_id text NOT NULL REFERENCES vacancies(id) ON DELETE CASCADE,
 candidate_id text NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
 stage text NOT NULL CHECK(stage IN('vacancy','offer')),
 model_version text NOT NULL,
 prediction jsonb NOT NULL,
 synthetic boolean NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(vacancy_id,candidate_id,stage,model_version)
);
CREATE INDEX prospective_owner_time ON intelligence.prospective_predictions(owner_id,created_at);
CREATE FUNCTION intelligence.keep_prediction_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 RAISE EXCEPTION 'prospective prediction is immutable';
END;
$$;
CREATE TRIGGER prospective_immutable BEFORE UPDATE ON intelligence.prospective_predictions
 FOR EACH ROW EXECUTE FUNCTION intelligence.keep_prediction_immutable();
CREATE TABLE intelligence.prospective_outcomes(
 prediction_id text PRIMARY KEY REFERENCES intelligence.prospective_predictions(id) ON DELETE CASCADE,
 candidate_accepts boolean NOT NULL,
 employer_accepts boolean NOT NULL,
 candidate_decided_at timestamptz NOT NULL,
 employer_decided_at timestamptz NOT NULL,
 sealed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TRIGGER prospective_outcome_immutable BEFORE UPDATE ON intelligence.prospective_outcomes
 FOR EACH ROW EXECUTE FUNCTION intelligence.keep_prediction_immutable();
