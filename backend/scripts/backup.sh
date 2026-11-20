#!/usr/bin/env bash
# Cópia de segurança completa (inclui anexos, guardados na base de dados).
# Uso: DATABASE_URL=postgresql://user:pass@host:5432/lumara ./scripts/backup.sh [pasta]
# Restaurar: pg_restore --clean --if-exists -d "$DATABASE_URL" ficheiro.dump
set -euo pipefail
DESTINO="${1:-./backups}"
URL="${DATABASE_URL/postgresql+psycopg/postgresql}"
mkdir -p "$DESTINO"
FICHEIRO="$DESTINO/lumara-$(date +%Y%m%d-%H%M%S).dump"
pg_dump --format=custom --no-owner "$URL" -f "$FICHEIRO"
# Mantém as últimas 30 cópias.
ls -1t "$DESTINO"/lumara-*.dump | tail -n +31 | xargs -r rm --
echo "Cópia criada: $FICHEIRO"
