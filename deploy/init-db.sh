#!/bin/sh
set -eu
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set=ON_ERROR_STOP=1 --set=app_password="$FSP_DB_PASSWORD" <<'SQL'
CREATE ROLE fsp_app LOGIN PASSWORD :'app_password';
ALTER DATABASE fsp_trajectory OWNER TO fsp_app;
GRANT ALL ON SCHEMA public TO fsp_app;
SQL
