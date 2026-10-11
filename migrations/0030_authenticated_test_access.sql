-- Retire only sessions issued to former anonymous guests; retain all user data.
-- Ordinary registered and password-authenticated test accounts are unaffected.
DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE is_guest);

-- Keep the existing synthetic fixture content aligned with password-only access.
UPDATE vacancies
SET description = 'Синтетическая вакансия для проверки: выберите резюме, отправьте отклик, выйдите и войдите с учетными данными работодателя, чтобы продолжить диалог.'
WHERE source_ref = 'DEMO_SHARED_V1'
  AND synthetic
  AND description = 'Синтетическая вакансия для проверки: выберите резюме, отправьте отклик, переключитесь в кабинет работодателя и продолжите диалог.';
