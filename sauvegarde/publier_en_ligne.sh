#!/bin/sh
# Met en ligne les données de la base locale (Docker) sur la base Render (macOS / Linux).
# Copie clients, crédits, transactions, alertes, corrections ; jamais les comptes ni les paiements.
set -e
cd "$(dirname "$0")/.."
echo "Cette opération REMPLACE les données en ligne par celles de ton ordinateur."
printf "External Database URL de Render : "; stty -echo 2>/dev/null; read CIBLE; stty echo 2>/dev/null; echo
[ -n "$CIBLE" ] || { echo "Annulé."; exit 1; }
printf "Taper OUI pour continuer : "; read OK
[ "$OK" = "OUI" ] || { echo "Annulé."; exit 1; }
sh sauvegarde/sauvegarder.sh
docker compose exec -T postgres sh /voicebank_securite/migrer.sh
docker compose exec -T -e CIBLE="$CIBLE" postgres sh /voicebank_securite/publier.sh
