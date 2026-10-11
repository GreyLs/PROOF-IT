-- Run by a DBA once. Set its password outside SQL/source control.
CREATE ROLE proofit_monitor LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
GRANT pg_read_all_stats TO proofit_monitor;
ALTER ROLE proofit_monitor SET default_transaction_read_only = on;
ALTER ROLE proofit_monitor SET statement_timeout = '2s';
ALTER ROLE proofit_monitor SET lock_timeout = '1s';
-- pg_read_all_stats exposes operational statistics, not SELECT on business tables.
-- Keep PUBLIC schema/table grants restricted in the deployment.
