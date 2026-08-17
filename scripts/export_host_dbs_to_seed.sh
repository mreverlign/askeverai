#!/usr/bin/env bash
# Export existing HighTower Postgres DBs into db-seed/ for Docker first-boot restore.
# All connection settings are read from .env (no hardcoded credentials).
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

: "${OLAP_DB_NAME:?Set OLAP_DB_NAME in .env}"
: "${OLAP_DB_USER:?Set OLAP_DB_USER in .env}"
: "${OLTP_DB_NAME:?Set OLTP_DB_NAME in .env}"
: "${OLTP_DB_USER:?Set OLTP_DB_USER in .env}"

# Source (host) servers used only for export. Prefer HOST_* so Docker
# OLAP_DB_HOST=postgres does not break dumping from the Mac HighTower DBs.
OLAP_HOST="${HOST_OLAP_DB_HOST:-${OLAP_DB_HOST:?Set HOST_OLAP_DB_HOST or OLAP_DB_HOST in .env}}"
OLAP_PORT="${HOST_OLAP_DB_PORT:-${OLAP_DB_PORT:?Set HOST_OLAP_DB_PORT or OLAP_DB_PORT in .env}}"
OLTP_HOST="${HOST_OLTP_DB_HOST:-${OLTP_DB_HOST:?Set HOST_OLTP_DB_HOST or OLTP_DB_HOST in .env}}"
OLTP_PORT="${HOST_OLTP_DB_PORT:-${OLTP_DB_PORT:?Set HOST_OLTP_DB_PORT or OLTP_DB_PORT in .env}}"

export PGPASSWORD="${OLAP_DB_PASSWORD:-}"

echo "Dumping OLAP ${OLAP_HOST}:${OLAP_PORT}/${OLAP_DB_NAME} (user=${OLAP_DB_USER}) -> db-seed/olap.sql"
pg_dump -h "${OLAP_HOST}" -p "${OLAP_PORT}" -U "${OLAP_DB_USER}" \
  --clean --if-exists --no-owner --no-privileges \
  -d "${OLAP_DB_NAME}" -f "${SEED_DIR}/olap.sql"

export PGPASSWORD="${OLTP_DB_PASSWORD:-}"

echo "Dumping OLTP ${OLTP_HOST}:${OLTP_PORT}/${OLTP_DB_NAME} (user=${OLTP_DB_USER}) -> db-seed/oltp.sql"
pg_dump -h "${OLTP_HOST}" -p "${OLTP_PORT}" -U "${OLTP_DB_USER}" \
  --clean --if-exists --no-owner --no-privileges \
  -d "${OLTP_DB_NAME}" -f "${SEED_DIR}/oltp.sql"

echo "Done. Next:"
echo "  docker compose down -v"
echo "  docker compose up --build"
