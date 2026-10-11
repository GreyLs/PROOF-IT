-- The Windows portable cluster uses locale C. Explicit ICU case conversion keeps
-- Cyrillic matching equivalent to Rust/Unicode and portable across deployments.
CREATE FUNCTION fsp_fold(value text) RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT lower(value COLLATE "und-x-icu") $$;
