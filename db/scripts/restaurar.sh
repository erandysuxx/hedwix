#!/usr/bin/env bash
# Restaura un respaldo de la base hedwix. Reemplaza (--drop) las colecciones que vengan en el respaldo.
# Uso: db/scripts/restaurar.sh db/backups/hedwix_AAAA-MM-DD_HHMM.archive.gz
set -euo pipefail
archivo="${1:?Uso: db/scripts/restaurar.sh db/backups/archivo.archive.gz}"
RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
set -a; source "$RAIZ/.env"; set +a

docker compose --project-directory "$RAIZ" exec -T mongo mongorestore --quiet \
  --username "$MONGO_ROOT_USER" --password "$MONGO_ROOT_PASSWORD" --authenticationDatabase admin \
  --nsInclude 'hedwix.*' --drop --archive --gzip < "$archivo"
echo "Restaurado: $archivo"
