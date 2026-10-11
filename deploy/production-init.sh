#!/bin/sh
set -eu
export FSP_MIGRATOR_PASSWORD="$(cat /run/secrets/db_migrator_password)"
export FSP_API_PASSWORD="$(cat /run/secrets/db_api_password)"
export FSP_WORKER_PASSWORD="$(cat /run/secrets/db_worker_password)"
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set=ON_ERROR_STOP=1 <<'SQL'
\getenv migrator_password FSP_MIGRATOR_PASSWORD
\getenv api_password FSP_API_PASSWORD
\getenv worker_password FSP_WORKER_PASSWORD
CREATE ROLE fsp_migrator LOGIN PASSWORD :'migrator_password';
CREATE ROLE fsp_api LOGIN PASSWORD :'api_password';
CREATE ROLE fsp_worker LOGIN PASSWORD :'worker_password';
ALTER DATABASE fsp_trajectory OWNER TO fsp_migrator;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT ALL ON SCHEMA public TO fsp_migrator;
GRANT USAGE ON SCHEMA public TO fsp_api,fsp_worker;
SQL
