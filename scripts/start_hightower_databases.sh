#!/usr/bin/env bash
set -euo pipefail

# Start the two Homebrew PostgreSQL clusters used by HighTower. Each setting
# can be overridden without editing this file.
OLAP_PG_BIN="${HIGHTOWER_OLAP_PG_BIN:-/opt/homebrew/opt/postgresql@14/bin}"
OLTP_PG_BIN="${HIGHTOWER_OLTP_PG_BIN:-/opt/homebrew/opt/postgresql@18/bin}"
OLAP_DATA_DIR="${HIGHTOWER_OLAP_DATA_DIR:-/opt/homebrew/var/postgresql@14}"
OLTP_DATA_DIR="${HIGHTOWER_OLTP_DATA_DIR:-/opt/homebrew/var/postgresql@18}"
OLAP_LOG="${HIGHTOWER_OLAP_LOG:-/opt/homebrew/var/log/postgresql@14.log}"
OLTP_LOG="${HIGHTOWER_OLTP_LOG:-/opt/homebrew/var/log/postgresql@18.log}"

start_cluster() {
    local label="$1"
    local pg_bin="$2"
    local data_dir="$3"
    local log_path="$4"
    local port="$5"
    local database="$6"

    if "${pg_bin}/pg_isready" -q -h 127.0.0.1 -p "${port}" -d "${database}"; then
        echo "${label} is already accepting connections on port ${port}."
        return
    fi

    if "${pg_bin}/pg_ctl" -D "${data_dir}" status >/dev/null 2>&1; then
        echo "${label} data directory is running, but not on expected port ${port}." >&2
        echo "Stop the conflicting cluster before retrying." >&2
        return 1
    fi

    echo "Starting ${label} on port ${port}..."
    "${pg_bin}/pg_ctl" \
        -D "${data_dir}" \
        -l "${log_path}" \
        -o "-p ${port}" \
        start

    if ! "${pg_bin}/pg_isready" -q -h 127.0.0.1 -p "${port}" -d "${database}"; then
        echo "${label} did not become ready; inspect ${log_path}." >&2
        return 1
    fi
    echo "${label} is accepting connections on port ${port}."
}

start_cluster \
    "HighTower OLAP" "${OLAP_PG_BIN}" "${OLAP_DATA_DIR}" "${OLAP_LOG}" \
    5433 askeverai_olap
start_cluster \
    "HighTower OLTP" "${OLTP_PG_BIN}" "${OLTP_DATA_DIR}" "${OLTP_LOG}" \
    5434 askeverai_oltp

echo "Both HighTower databases are ready."
