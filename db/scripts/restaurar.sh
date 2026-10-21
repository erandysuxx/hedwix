#!/usr/bin/env bash
# Restaura un respaldo de la base hedwix. Reemplaza (--drop) las colecciones que vengan en el respaldo.
# Uso: scripts/restaurar.sh backups/hedwix_AAAA-MM-DD_HHMM.archive.gz
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a

archivo="${1:?Uso: scripts/restaurar.sh backups/archivo.archive.gz}"
docker compose exec -T mongo mongorestore --quiet \
  --username "$MONGO_ROOT_USER" --password "$MONGO_ROOT_PASSWORD" --authenticationDatabase admin \
  --nsInclude 'hedwix.*' --drop --archive --gzip < "$archivo"
echo "Restaurado: $archivo"
