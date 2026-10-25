#!/bin/sh
# Restaure une sauvegarde (remplace le contenu actuel) : sh sauvegarde/restaurer.sh sauvegardes/xxx.dump
set -e
cd "$(dirname "$0")/.."
[ -f "$1" ] || { echo "Usage : sh sauvegarde/restaurer.sh sauvegardes/voicebank_AAAA-MM-JJ_HHMM.dump"; exit 1; }
printf "La base actuelle sera remplacée par %s. Taper OUI pour continuer : " "$1"; read OK
[ "$OK" = "OUI" ] || { echo "Annulé."; exit 1; }
docker compose exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d voicebank_db --clean --if-exists --no-owner' < "$1"
docker compose exec -T postgres sh /voicebank_securite/migrer.sh
docker compose restart api
echo "Restauration terminée."
