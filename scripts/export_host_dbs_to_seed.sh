#!/usr/bin/env bash
# Export existing HighTower Postgres DBs into db-seed/ for Docker first-boot restore.
# All connection settings are required from .env (nothing hardcoded).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"
ENV_FILE="${ROOT}/.env"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: .env not found at ${ENV_FILE}"
  exit 1
fi

# Load KEY=VALUE from .env without `source` (handles CRLF and skips comments).
load_env_file() {
  local file="$1"
  local line key value
  while IFS= read -r line || [[ -n "${line}" ]]; do
    line="${line%$'\r'}"
    [[ -z "${line}" || "${line}" =~ ^[[:space:]]*# ]] && continue
    [[ "${line}" == *=* ]] || continue
    key="${line%%=*}"
    value="${line#*=}"
    key="${key%"${key##*[![:space:]]}"}"
    key="${key#"${key%%[![:space:]]*}"}"
    [[ -n "${key}" ]] || continue
    export "${key}=${value}"
  done < "${file}"
}

load_env_file "${ENV_FILE}"

SEED_DIR="${ROOT}/db-seed"
mkdir -p "${SEED_DIR}"

required_vars=(
  HOST_OLAP_DB_HOST
  HOST_OLAP_DB_PORT
  HOST_OLAP_DB_NAME
  HOST_OLAP_DB_USER
  HOST_OLTP_DB_HOST
  HOST_OLTP_DB_PORT
  HOST_OLTP_DB_NAME
  HOST_OLTP_DB_USER
)

missing=()
for var in "${required_vars[@]}"; do
  if [[ -z "${!var:-}" ]]; then
    missing+=("${var}")
  fi
done

if ((${#missing[@]} > 0)); then
  echo "ERROR: missing required keys in ${ENV_FILE}:"
  for var in "${missing[@]}"; do
    echo "  - ${var}"
  done
  exit 1
fi

# pg_dump major version must be >= server major version.
# Set PG_DUMP in .env to an absolute path, or leave unset to auto-detect.
resolve_pg_dump() {
  if [[ -n "${PG_DUMP:-}" ]]; then
    if [[ ! -x "${PG_DUMP}" ]]; then
      echo "ERROR: PG_DUMP is set but not executable: ${PG_DUMP}"
      exit 1
    fi
    echo "${PG_DUMP}"
    return
  fi

  local candidates=()
  local brew_prefix=""
  if command -v brew >/dev/null 2>&1; then
    brew_prefix="$(brew --prefix 2>/dev/null || true)"
  fi
  if [[ -n "${brew_prefix}" ]]; then
    local ver
    for ver in 18 17 16 15 14; do
      candidates+=("${brew_prefix}/opt/postgresql@${ver}/bin/pg_dump")
    done
    candidates+=("${brew_prefix}/opt/postgresql/bin/pg_dump")
  fi
  candidates+=("$(command -v pg_dump || true)")

  local c
  for c in "${candidates[@]}"; do
    if [[ -n "${c}" && -x "${c}" ]]; then
      echo "${c}"
      return
    fi
  done

  echo "ERROR: pg_dump not found. Install matching Postgres client tools or set PG_DUMP in .env."
  exit 1
}

PG_DUMP_BIN="$(resolve_pg_dump)"
echo "Using pg_dump: ${PG_DUMP_BIN} ($("${PG_DUMP_BIN}" --version))"

export PGPASSWORD="${HOST_OLAP_DB_PASSWORD:-}"

echo "Dumping OLAP ${HOST_OLAP_DB_HOST}:${HOST_OLAP_DB_PORT}/${HOST_OLAP_DB_NAME} (user=${HOST_OLAP_DB_USER}) -> db-seed/olap.sql"
"${PG_DUMP_BIN}" -h "${HOST_OLAP_DB_HOST}" -p "${HOST_OLAP_DB_PORT}" -U "${HOST_OLAP_DB_USER}" \
  --clean --if-exists --no-owner --no-privileges \
  -d "${HOST_OLAP_DB_NAME}" -f "${SEED_DIR}/olap.sql"

export PGPASSWORD="${HOST_OLTP_DB_PASSWORD:-}"

echo "Dumping OLTP ${HOST_OLTP_DB_HOST}:${HOST_OLTP_DB_PORT}/${HOST_OLTP_DB_NAME} (user=${HOST_OLTP_DB_USER}) -> db-seed/oltp.sql"
"${PG_DUMP_BIN}" -h "${HOST_OLTP_DB_HOST}" -p "${HOST_OLTP_DB_PORT}" -U "${HOST_OLTP_DB_USER}" \
  --clean --if-exists --no-owner --no-privileges \
  -d "${HOST_OLTP_DB_NAME}" -f "${SEED_DIR}/oltp.sql"

echo "Done. Next:"
echo "  docker compose down -v"
echo "  docker compose up --build"
