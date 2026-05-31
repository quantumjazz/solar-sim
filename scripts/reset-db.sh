#!/usr/bin/env bash
# Reset the solar-sim cohort database between pilot sessions.
#
# Stops the systemd service, moves the current DB aside as a dated
# backup, removes the live DB, and restarts the service. The first
# student to log in afterwards lands on a fresh app.
#
# Safe to re-run; refuses to act if SOLAR_SIM_DB is not set or the
# DB path is empty.

set -euo pipefail

if [[ -z "${SOLAR_SIM_DB:-}" ]]; then
    if [[ -f /home/victor/apps/solar-sim/.env.production ]]; then
        # shellcheck disable=SC1091
        set -a
        source /home/victor/apps/solar-sim/.env.production
        set +a
    fi
fi

DB_PATH="${SOLAR_SIM_DB:-/home/victor/apps/solar-sim/solar-sim.db}"
SERVICE_NAME="${SOLAR_SIM_SERVICE_NAME:-solar-sim}"

if [[ -z "${DB_PATH}" ]]; then
    echo "SOLAR_SIM_DB is empty — refusing to act." >&2
    exit 1
fi

if [[ ! -f "${DB_PATH}" ]]; then
    echo "No DB at ${DB_PATH}; nothing to back up. Restarting anyway."
else
    backup="${DB_PATH%.db}-$(date +%Y%m%d-%H%M%S).db.bak"
    echo "Backing up ${DB_PATH} -> ${backup}"
    sudo systemctl stop "${SERVICE_NAME}"
    cp "${DB_PATH}" "${backup}"
    rm -f "${DB_PATH}" "${DB_PATH}-wal" "${DB_PATH}-shm"
fi

sudo systemctl start "${SERVICE_NAME}"
sudo systemctl status "${SERVICE_NAME}" --no-pager | head -8
echo
echo "Done. A fresh DB will be created on first request."
