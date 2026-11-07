#!/usr/bin/env bash
# Backup MySQL + upload folder. Run from repo root or any cwd.
set -euo pipefail
umask 077
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
UPLOAD_METHOD="${UPLOAD_BACKUP_METHOD:-${MYSQL_BACKUP_METHOD:-local}}"
STAMP="$(date +%Y%m%d_%H%M%S)"
TEMP_UPLOAD="$(mktemp "$BACKUP_DIR/.uploads_${STAMP}.partial.XXXXXXXX")"
trap 'rm -f -- "$TEMP_UPLOAD"' EXIT
OUT="$BACKUP_DIR/uploads_${STAMP}_${TEMP_UPLOAD##*.}.tar.gz"
if [[ "$UPLOAD_METHOD" == docker ]]; then
  UPLOAD_SRC="${UPLOAD_BACKUP_SOURCE:-/app/flask_shop/static/upload}"
  UPLOAD_CONTAINER="${UPLOAD_BACKUP_CONTAINER:-shop_api}"
  echo ">> upload backup via docker exec $UPLOAD_CONTAINER"
  docker exec "$UPLOAD_CONTAINER" python -c 'import os,sys,tarfile; p=sys.argv[1]; assert os.path.isdir(p), "upload directory missing"; t=tarfile.open(fileobj=sys.stdout.buffer, mode="w|gz"); t.add(p, arcname="upload"); t.close()' "$UPLOAD_SRC" > "$TEMP_UPLOAD"
elif [[ "$UPLOAD_METHOD" == local ]]; then
  UPLOAD_SRC="${UPLOAD_BACKUP_SOURCE:-$ROOT/flask_shop/flask_shop/static/upload}"
  if [ ! -d "$UPLOAD_SRC" ]; then
    echo "Upload directory missing; backup incomplete" >&2
    exit 1
  fi
  tar -czf "$TEMP_UPLOAD" -C "$UPLOAD_SRC" .
else
  echo "UPLOAD_BACKUP_METHOD must be local or docker" >&2
  exit 1
fi
tar -tzf "$TEMP_UPLOAD" > /dev/null
mv -- "$TEMP_UPLOAD" "$OUT"
echo "OK $OUT ($(du -h "$OUT" | awk '{print $1}'))"

echo "==== 3) Private payment proofs ===="
TEMP_PROOF="$(mktemp "$BACKUP_DIR/.pay_proofs_${STAMP}.partial.XXXXXXXX")"
trap 'rm -f -- "$TEMP_UPLOAD" "$TEMP_PROOF"' EXIT
PROOF_OUT="$BACKUP_DIR/pay_proofs_${STAMP}_${TEMP_PROOF##*.}.tar.gz"
if [[ "$UPLOAD_METHOD" == docker ]]; then
  PROOF_SRC="${PROOF_BACKUP_SOURCE:-/app/private/pay_proofs}"
  docker exec "$UPLOAD_CONTAINER" python -c 'import os,sys,tarfile; p=sys.argv[1]; assert os.path.isdir(p), "private proof directory missing"; t=tarfile.open(fileobj=sys.stdout.buffer, mode="w|gz"); t.add(p, arcname="pay_proofs"); t.close()' "$PROOF_SRC" > "$TEMP_PROOF"
else
  PROOF_SRC="${PROOF_BACKUP_SOURCE:-$ROOT/flask_shop/instance/pay_proofs}"
  if [ ! -d "$PROOF_SRC" ]; then
    echo "Private proof directory missing; backup incomplete" >&2
    exit 1
  fi
  tar -czf "$TEMP_PROOF" -C "$PROOF_SRC" .
fi
tar -tzf "$TEMP_PROOF" > /dev/null
mv -- "$TEMP_PROOF" "$PROOF_OUT"
echo "OK $PROOF_OUT ($(du -h "$PROOF_OUT" | awk '{print $1}'))"

find "$BACKUP_DIR" -name "uploads_*.tar.gz" -type f -mtime +"${BACKUP_KEEP_DAYS}" -print -delete
find "$BACKUP_DIR" -name "pay_proofs_*.tar.gz" -type f -mtime +"${BACKUP_KEEP_DAYS}" -print -delete

echo "==== backup_all done ===="
