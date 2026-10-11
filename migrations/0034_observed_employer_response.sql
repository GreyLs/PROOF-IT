-- No timestamp is invented for historical status-only records.
ALTER TABLE applications ADD COLUMN first_employer_response_at timestamptz;
