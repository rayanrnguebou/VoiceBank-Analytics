#!/bin/sh
# Exécuté automatiquement par l'image postgres au premier démarrage.
set -e
: "${VOICEBANK_APP_PASSWORD:?VOICEBANK_APP_PASSWORD manquant}"
: "${VOICEBANK_READER_PASSWORD:?VOICEBANK_READER_PASSWORD manquant}"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     -v app_pwd="$VOICEBANK_APP_PASSWORD" -v reader_pwd="$VOICEBANK_READER_PASSWORD" \
     -f /voicebank_securite/roles.sql
