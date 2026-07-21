#!/usr/bin/env bash
# MySQL 逻辑备份（可在宿主机 cron 或 compose 旁路容器执行）
# 依赖：mysqldump 客户端，或 docker exec shop_mysql
set -euo pipefail

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

FILE="${OUT_DIR}/flask_shop_${MYSQL_DB}_${STAMP}.sql.gz"

if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$CONTAINER"; then
  echo ">> backup via docker exec $CONTAINER"
  docker exec "$CONTAINER" mysqldump \
    -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" \
    --single-transaction --routines --triggers \
    "$MYSQL_DB" | gzip -c > "$FILE"
else
  echo ">> backup via local mysqldump $MYSQL_HOST:$MYSQL_PORT"
  mysqldump -h"$MYSQL_HOST" -P"$MYSQL_PORT" -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" \
    --single-transaction --routines --triggers \
    "$MYSQL_DB" | gzip -c > "$FILE"
fi

echo "OK $FILE ($(du -h "$FILE" | awk '{print $1}'))"

# 清理过期
find "$OUT_DIR" -name "flask_shop_*.sql.gz" -type f -mtime +"$KEEP_DAYS" -print -delete || true
echo "cleanup done keep_days=$KEEP_DAYS"
