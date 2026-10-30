#!/bin/sh
# Copie TOUTE la base en ligne (Render, qui expire au bout de 30 jours) vers une base Neon gratuite et sans
# expiration : comptes, organisations, abonnements, paiements, double authentification, journaux, données.
# Rien n'est modifié sur Render. Nécessite Docker. Voir README, « Base sans expiration (Neon) ».
set -e
cd "$(dirname "$0")/.."
secret() { printf "%s" "$1" >&2; stty -echo 2>/dev/null; read -r v; stty echo 2>/dev/null; echo >&2; printf "%s" "$v"; }
SOURCE=$(secret "1. External Database URL de Render (voicebank-db → Connect) : ")
CIBLE=$(secret "2. URL de la base Neon (Connect, « Connection pooling » décoché) : ")
[ -n "$SOURCE" ] && [ -n "$CIBLE" ] || { echo "Annulé."; exit 1; }
printf "Taper OUI pour copier : "; read -r OK
[ "$OK" = "OUI" ] || { echo "Annulé."; exit 1; }
mkdir -p sauvegarde/copies
docker run --rm -e SOURCE="$SOURCE" -e CIBLE="$CIBLE" -e DOSSIER=/copies -e SECURITE=/securite \
  -v "$PWD/voicebank_db/securite:/securite:ro" -v "$PWD/sauvegarde/copies:/copies" -w /copies \
  postgres:18-alpine sh /securite/transferer_base.sh
