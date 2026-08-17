#!/bin/sh
set -e

# Creates app databases from .env (OLAP_DB_NAME / OLTP_DB_NAME).
# Runs only on first boot (empty volume).

: "${OLAP_DB_NAME:?OLAP_DB_NAME must be set in .env}"
: "${OLTP_DB_NAME:?OLTP_DB_NAME must be set in .env}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
	SELECT 'CREATE DATABASE ${OLAP_DB_NAME}'
	WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${OLAP_DB_NAME}')\gexec
	SELECT 'CREATE DATABASE ${OLTP_DB_NAME}'
	WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${OLTP_DB_NAME}')\gexec
EOSQL
