#!/bin/sh
# Make sure the data volume exists and is writable, then drop root privileges.
set -e

DATA_DIR="${DATA_DIR:-/data}"
mkdir -p "$DATA_DIR/uploads"

if [ "$(id -u)" = "0" ] && [ "${PUID:-0}" != "0" ]; then
  chown -R "${PUID}:${PGID:-$PUID}" "$DATA_DIR"
  if command -v setpriv >/dev/null 2>&1; then
    exec setpriv --reuid="$PUID" --regid="${PGID:-$PUID}" --clear-groups "$@"
  fi
  echo "setpriv not found – running as root" >&2
fi

exec "$@"
