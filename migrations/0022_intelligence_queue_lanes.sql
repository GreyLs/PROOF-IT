CREATE INDEX intelligence_jobs_cpu_lane_idx ON intelligence.jobs(status,created_at)
 WHERE kind NOT IN ('arena','item_draft') AND attempts<3;
CREATE INDEX intelligence_jobs_ai_lane_idx ON intelligence.jobs(status,created_at)
 WHERE kind IN ('arena','item_draft') AND attempts<3;
