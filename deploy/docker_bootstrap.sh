#!/usr/bin/env sh
set -e
echo "[bootstrap] wait api..."
sleep 5
echo "[bootstrap] seed via docker_seed if present"
# run from host:
# docker cp deploy/docker_seed.py shop_api:/tmp/docker_seed.py
# docker exec shop_api python /tmp/docker_seed.py
echo "[bootstrap] health"
curl -fsS http://127.0.0.1:${HTTP_PUBLISH_PORT:-18080}/health/ || true
curl -fsS http://127.0.0.1:${HTTP_PUBLISH_PORT:-18080}/metrics/ || true
echo done
