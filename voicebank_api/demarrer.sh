#!/bin/sh
# Démarrage du conteneur API. Sur Render (ou une démo), INITIALISER_BASE=true crée le schéma
# et, si DONNEES_DEMO=true, remplit une base VIDE avec des données fictives.
set -e
if [ "$INITIALISER_BASE" = "true" ]; then
  python -m app.outils.initialiser_base
  if [ "$DONNEES_DEMO" = "true" ]; then
    python -m app.outils.generer_demo --si-vide
  fi
fi
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips "*"
