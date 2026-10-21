#!/usr/bin/env bash
# Respalda la base hedwix en backups/hedwix_AAAA-MM-DD_HHMM.archive.gz
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a

archivo="backups/hedwix_$(date +%F_%H%M).archive.gz"
docker compose exec -T mongo mongodump --quiet \
  --username "$MONGO_ROOT_USER" --password "$MONGO_ROOT_PASSWORD" --authenticationDatabase admin \
  --db hedwix --archive --gzip > "$archivo"
echo "Respaldo: $archivo ($(du -h "$archivo" | cut -f1))"
