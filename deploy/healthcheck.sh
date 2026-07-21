#!/usr/bin/env bash
# 探活：API +（可选）HTTP 入口
# 用法：
#   bash deploy/healthcheck.sh
#   API_URL=http://127.0.0.1:5000 bash deploy/healthcheck.sh
#   PUBLIC_URL=http://127.0.0.1:18080 bash deploy/healthcheck.sh
set -euo pipefail

API_URL="${API_URL:-http://127.0.0.1:5000}"
PUBLIC_URL="${PUBLIC_URL:-}"

echo ">> check API ${API_URL}/health/"
code=$(curl -s -o /tmp_shop_health_body -w "%{http_code}" "${API_URL}/health/" || true)
body=$(cat /tmp_shop_health_body 2>/dev/null || true)
rm -f /tmp_shop_health_body
if [ "$code" != "200" ]; then
  echo "FAIL api health HTTP $code $body"
  exit 1
fi
echo "OK api $body"

if [ -n "$PUBLIC_URL" ]; then
  echo ">> check public ${PUBLIC_URL}/healthz"
  pcode=$(curl -s -o /dev/null -w "%{http_code}" "${PUBLIC_URL}/healthz" || true)
  if [ "$pcode" != "200" ]; then
    echo "FAIL public healthz HTTP $pcode"
    exit 1
  fi
  echo "OK public healthz"
fi

echo "all green"
