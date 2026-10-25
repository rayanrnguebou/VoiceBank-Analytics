#!/bin/sh
# Copie les données métier de la base locale vers une autre base (ex. Render), en remplaçant
# les données de la cible. Lancé DANS le conteneur postgres par sauvegarde/publier_en_ligne.bat|.sh.
# Variable requise : CIBLE = URL PostgreSQL de destination (External Database URL de Render).
# Les comptes, mots de passe, paiements et journaux d'audit ne sont JAMAIS copiés.
set -e
: "${CIBLE:?CIBLE manquante (URL de la base de destination)}"
SOURCE_USER="${SOURCE_USER:-$POSTGRES_USER}"
SOURCE_DB="${SOURCE_DB:-voicebank_db}"
TABLES="clients credits transactions alertes_fraude logs_corrections"

echo "→ Vérification de la base de destination"
psql "$CIBLE" -v ON_ERROR_STOP=1 -tAc "SELECT 'Destination : ' || current_database() || ' (PostgreSQL ' || current_setting('server_version') || ')'"
for t in $TABLES; do
  psql "$CIBLE" -v ON_ERROR_STOP=1 -tAc "SELECT 1 FROM voicebank.$t LIMIT 0" >/dev/null \
    || { echo "Table voicebank.$t absente de la destination : démarre l'API en ligne une fois (INITIALISER_BASE=true)." >&2; exit 1; }
done

ARGS=""
for t in $TABLES; do ARGS="$ARGS --table=voicebank.$t"; done

echo "→ Copie des données (remplace celles de la destination, en une seule transaction)"
{
  echo "BEGIN;"
  echo "TRUNCATE voicebank.alertes_fraude, voicebank.transactions, voicebank.credits, voicebank.clients, voicebank.logs_corrections RESTART IDENTITY CASCADE;"
  # shellcheck disable=SC2086
  pg_dump -U "$SOURCE_USER" -d "$SOURCE_DB" --data-only --no-owner --no-privileges $ARGS \
    | grep -v -E "^(SET transaction_timeout|SELECT pg_catalog.set_config\('search_path')"
  echo "SET search_path = public;"
  echo "COMMIT;"
} | psql "$CIBLE" -v ON_ERROR_STOP=1 -q

psql "$CIBLE" -tAc "SELECT 'En ligne : ' || (SELECT COUNT(*) FROM voicebank.clients) || ' clients, '
  || (SELECT COUNT(*) FROM voicebank.transactions) || ' transactions, '
  || (SELECT COUNT(*) FROM voicebank.credits) || ' crédits, '
  || (SELECT COUNT(*) FROM voicebank.alertes_fraude) || ' alertes'"
echo "Publication terminée."
