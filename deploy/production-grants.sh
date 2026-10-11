#!/bin/sh
set -eu
export PGPASSWORD="$(cat /run/secrets/db_migrator_password)"
exec psql --host=postgres --username=fsp_migrator --dbname=fsp_trajectory --set=ON_ERROR_STOP=1 --file=/config/grants.sql
