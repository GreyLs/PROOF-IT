-- Retire sessions issued through the removed passwordless demonstration endpoint.
-- Profiles and uploaded documents remain available to the operator for recovery.
UPDATE users SET auth_epoch=auth_epoch+1 WHERE id IN ('demo-candidate','demo-employer');
DELETE FROM sessions WHERE user_id IN ('demo-candidate','demo-employer');
