-- An appeal preserves an established independent finding until dismissal.
ALTER TABLE intelligence.review_cases ADD COLUMN established_violation boolean NOT NULL DEFAULT false;
UPDATE intelligence.review_cases SET established_violation=true WHERE status='confirmed';
CREATE FUNCTION intelligence.preserve_review_finding() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.status='confirmed' THEN NEW.established_violation=true;
 ELSIF NEW.status='dismissed' THEN NEW.established_violation=false;
 ELSIF TG_OP='UPDATE' THEN NEW.established_violation=OLD.established_violation;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER review_finding BEFORE INSERT OR UPDATE ON intelligence.review_cases
FOR EACH ROW EXECUTE FUNCTION intelligence.preserve_review_finding();
