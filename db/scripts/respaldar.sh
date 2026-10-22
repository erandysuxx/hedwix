#!/usr/bin/env bash
# Respalda la base hedwix en db/backups/hedwix_AAAA-MM-DD_HHMM.archive.gz. Se puede correr desde cualquier carpeta.
set -euo pipefail
RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
set -a; source "$RAIZ/.env"; set +a

archivo="$RAIZ/db/backups/hedwix_$(date +%F_%H%M).archive.gz"
mkdir -p "$RAIZ/db/backups"
docker compose --project-directory "$RAIZ" exec -T mongo mongodump --quiet \
  --username "$MONGO_ROOT_USER" --password "$MONGO_ROOT_PASSWORD" --authenticationDatabase admin \
  --db hedwix --archive --gzip > "$archivo"
echo "Respaldo: ${archivo#"$RAIZ"/} ($(du -h "$archivo" | cut -f1))"
