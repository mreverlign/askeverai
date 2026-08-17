#!/usr/bin/env bash
# Export existing HighTower Postgres DBs into db-seed/ for Docker first-boot restore.
# All connection settings are required from .env (nothing hardcoded).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

if [[ ! -f .env ]]; then
  echo "ERROR: .env not found at ${ROOT}/.env"
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

SEED_DIR="${ROOT}/db-seed"
mkdir -p "${SEED_DIR}"

: "${HOST_OLAP_DB_HOST:?Set HOST_OLAP_DB_HOST in .env}"
: "${HOST_OLAP_DB_PORT:?Set HOST_OLAP_DB_PORT in .env}"
: "${HOST_OLAP_DB_NAME:?Set HOST_OLAP_DB_NAME in .env}"
: "${HOST_OLAP_DB_USER:?Set HOST_OLAP_DB_USER in .env}"
: "${HOST_OLTP_DB_HOST:?Set HOST_OLTP_DB_HOST in .env}"
: "${HOST_OLTP_DB_PORT:?Set HOST_OLTP_DB_PORT in .env}"
: "${HOST_OLTP_DB_NAME:?Set HOST_OLTP_DB_NAME in .env}"
: "${HOST_OLTP_DB_USER:?Set HOST_OLTP_DB_USER in .env}"

export PGPASSWORD="${HOST_OLAP_DB_PASSWORD:-}"

echo "Dumping OLAP ${HOST_OLAP_DB_HOST}:${HOST_OLAP_DB_PORT}/${HOST_OLAP_DB_NAME} (user=${HOST_OLAP_DB_USER}) -> db-seed/olap.sql"
pg_dump -h "${HOST_OLAP_DB_HOST}" -p "${HOST_OLAP_DB_PORT}" -U "${HOST_OLAP_DB_USER}" \
  --clean --if-exists --no-owner --no-privileges \
  -d "${HOST_OLAP_DB_NAME}" -f "${SEED_DIR}/olap.sql"

export PGPASSWORD="${HOST_OLTP_DB_PASSWORD:-}"

echo "Dumping OLTP ${HOST_OLTP_DB_HOST}:${HOST_OLTP_DB_PORT}/${HOST_OLTP_DB_NAME} (user=${HOST_OLTP_DB_USER}) -> db-seed/oltp.sql"
pg_dump -h "${HOST_OLTP_DB_HOST}" -p "${HOST_OLTP_DB_PORT}" -U "${HOST_OLTP_DB_USER}" \
  --clean --if-exists --no-owner --no-privileges \
  -d "${HOST_OLTP_DB_NAME}" -f "${SEED_DIR}/oltp.sql"

echo "Done. Next:"
echo "  docker compose down -v"
echo "  docker compose up --build"
