#!/usr/bin/env bash
# Backup MySQL + upload folder. Run from repo root or any cwd.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export BACKUP_DIR="${BACKUP_DIR:-$ROOT/deploy/backups}"
export BACKUP_KEEP_DAYS="${BACKUP_KEEP_DAYS:-7}"
mkdir -p "$BACKUP_DIR"

# Load deploy/.env.prod if present (export KEY=VAL lines)
if [ -f "$ROOT/deploy/.env.prod" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/deploy/.env.prod"
  set +a
fi

echo "==== 1) MySQL dump ===="
bash "$ROOT/deploy/backup_mysql.sh"

echo "==== 2) Uploads ===="
UPLOAD_SRC="$ROOT/flask_shop/flask_shop/static/upload"
STAMP="$(date +%Y%m%d_%H%M%S)"
if [ -d "$UPLOAD_SRC" ]; then
  OUT="$BACKUP_DIR/uploads_${STAMP}.tar.gz"
  tar -czf "$OUT" -C "$ROOT/flask_shop/flask_shop/static" upload 2>/dev/null \
    || tar -czf "$OUT" -C "$UPLOAD_SRC" .
  echo "OK $OUT ($(du -h "$OUT" | awk '{print $1}'))"
else
  echo "SKIP no upload dir at $UPLOAD_SRC"
fi

# cleanup old upload packs
find "$BACKUP_DIR" -name "uploads_*.tar.gz" -type f -mtime +"${BACKUP_KEEP_DAYS}" -print -delete 2>/dev/null || true

echo "==== backup_all done ===="
ls -lt "$BACKUP_DIR" | head -20
