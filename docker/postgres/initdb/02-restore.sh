#!/bin/sh
set -e

# Loads dumps exported from the host HighTower Postgres servers.
# Runs only on first boot (empty volume).
# DB names come from .env (OLAP_DB_NAME / OLTP_DB_NAME).

: "${OLAP_DB_NAME:?OLAP_DB_NAME must be set in .env}"
: "${OLTP_DB_NAME:?OLTP_DB_NAME must be set in .env}"

if [ -f /seed/olap.sql ]; then
  echo "Restoring OLAP dump into ${OLAP_DB_NAME}..."
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$OLAP_DB_NAME" -f /seed/olap.sql
else
  echo "WARNING: /seed/olap.sql missing — ${OLAP_DB_NAME} stays empty."
fi

if [ -f /seed/oltp.sql ]; then
  echo "Restoring OLTP dump into ${OLTP_DB_NAME}..."
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$OLTP_DB_NAME" -f /seed/oltp.sql
else
  echo "WARNING: /seed/oltp.sql missing — ${OLTP_DB_NAME} stays empty."
fi

echo "Postgres seed finished."
