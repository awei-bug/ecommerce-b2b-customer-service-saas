#!/usr/bin/env bash
# MySQL 逻辑备份（可在宿主机 cron 或 compose 旁路容器执行）
# 依赖：mysqldump 客户端，或 docker exec shop_mysql
set -euo pipefail
umask 077

KEEP_DAYS="${BACKUP_KEEP_DAYS:-7}"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT_DIR="${BACKUP_DIR:-./backups}"
mkdir -p "$OUT_DIR"

MYSQL_HOST="${MYSQL_HOST:-127.0.0.1}"
MYSQL_PORT="${MYSQL_PORT:-3307}"
MYSQL_USER="${MYSQL_USERNAME:-shop}"
MYSQL_PASSWORD="${MYSQL_PASSWORD:-change-me-db-password}"
MYSQL_DB="${MYSQL_DB:-flask_shop_saas}"
CONTAINER="${MYSQL_CONTAINER:-shop_mysql}"
METHOD="${MYSQL_BACKUP_METHOD:-local}"

if [[ ! "$MYSQL_DB" =~ ^[A-Za-z0-9_]+$ || ! "$KEEP_DAYS" =~ ^[0-9]+$ ]]; then
  echo "Invalid MYSQL_DB or BACKUP_KEEP_DAYS" >&2
  exit 1
fi
if [[ "$METHOD" != local && "$METHOD" != docker ]]; then
  echo "MYSQL_BACKUP_METHOD must be local or docker" >&2
  exit 1
fi

TEMP_FILE="$(mktemp "${OUT_DIR}/.flask_shop_${MYSQL_DB}_${STAMP}.partial.XXXXXXXX")"
trap 'rm -f -- "$TEMP_FILE"' EXIT
SUFFIX="${TEMP_FILE##*.}"
FILE="${OUT_DIR}/flask_shop_${MYSQL_DB}_${STAMP}_${SUFFIX}.sql.gz"
export MYSQL_PWD="$MYSQL_PASSWORD"

if [[ "$METHOD" == docker ]]; then
  echo ">> backup via docker exec $CONTAINER"
  docker exec -e MYSQL_PWD "$CONTAINER" mysqldump \
    -u"$MYSQL_USER" \
    --single-transaction --routines --triggers \
    "$MYSQL_DB" | gzip -c > "$TEMP_FILE"
else
  echo ">> backup via local mysqldump $MYSQL_HOST:$MYSQL_PORT"
  mysqldump -h"$MYSQL_HOST" -P"$MYSQL_PORT" -u"$MYSQL_USER" \
    --single-transaction --routines --triggers \
    "$MYSQL_DB" | gzip -c > "$TEMP_FILE"
fi

BYTES="$(gzip -cd "$TEMP_FILE" | wc -c)"
if [[ "$BYTES" -eq 0 ]]; then
  echo "Backup is empty" >&2
  exit 1
fi
mv -- "$TEMP_FILE" "$FILE"
echo "OK $FILE ($(du -h "$FILE" | awk '{print $1}'))"

# 清理过期
find "$OUT_DIR" -name "flask_shop_${MYSQL_DB}_[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]_[0-9][0-9][0-9][0-9][0-9][0-9]*.sql.gz" -type f -mtime +"$KEEP_DAYS" -print -delete
echo "cleanup done keep_days=$KEEP_DAYS"
