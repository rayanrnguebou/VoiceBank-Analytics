#!/bin/sh
# Sauvegarde complète de la base VoiceBank (Docker) dans sauvegardes/ (macOS / Linux).
set -e
cd "$(dirname "$0")/.."
mkdir -p sauvegardes
FICHIER="sauvegardes/voicebank_$(date +%Y-%m-%d_%H%M).dump"
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d voicebank_db -Fc' > "$FICHIER"
echo "Sauvegarde terminée : $FICHIER"
ls -1t sauvegardes/voicebank_*.dump | tail -n +11 | xargs -r rm --
