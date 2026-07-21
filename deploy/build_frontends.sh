#!/usr/bin/env bash
# 一键构建前端静态资源（供 Nginx 挂载）
# 用法：在仓库根目录 bash deploy/build_frontends.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo ">> build vue_shop (admin) — 生产同域 API baseURL 为空"
cd "$ROOT/vue_shop"
if [ ! -d node_modules ]; then npm install; fi
# 同域反代：API 与页面同源，baseURL=''
export VUE_APP_API_BASE="${VUE_APP_API_BASE:-}"
export NODE_ENV=production
npm run build

echo ">> build mall — 请求 /api/c（由 Nginx 反代）"
cd "$ROOT/mall"
if [ ! -d node_modules ]; then npm install; fi
npm run build

echo "done:"
echo "  vue_shop/dist  → Nginx /admin/"
echo "  mall/dist      → Nginx /"
