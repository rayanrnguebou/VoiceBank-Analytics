#!/bin/sh
# Copie les données métier de la base locale vers une autre base (ex. Render), en remplaçant
# les données de la cible. Lancé DANS le conteneur postgres par sauvegarde/publier_en_ligne.bat|.sh.
# Variable requise : CIBLE = URL PostgreSQL de destination (External Database URL de Render).
# Les comptes, mots de passe, paiements et journaux d'audit ne sont JAMAIS copiés.
# Seules les colonnes présentes des DEUX côtés sont copiées : une colonne ajoutée à la main en local
# (ancien script de chargement, essai…) n'empêche pas la publication, elle est simplement ignorée.
set -e
: "${CIBLE:?CIBLE manquante (URL de la base de destination)}"
SOURCE_USER="${SOURCE_USER:-$POSTGRES_USER}"
SOURCE_DB="${SOURCE_DB:-voicebank_db}"
# Ordre d'insertion : les tables référencées d'abord
TABLES="clients credits transactions alertes_fraude logs_corrections"
SRC="psql -U $SOURCE_USER -d $SOURCE_DB -v ON_ERROR_STOP=1 -X -q"
DST="psql $CIBLE -v ON_ERROR_STOP=1 -X -q"

colonnes() {   # $1 = commande psql, $2 = table : colonnes dans l'ordre, une par ligne
  $1 -tA -c "SELECT column_name FROM information_schema.columns WHERE table_schema = 'voicebank'
             AND table_name = '$2' ORDER BY ordinal_position"
}

echo "→ Vérification de la base de destination"
$DST -tA -c "SELECT 'Destination : ' || current_database() || ' (PostgreSQL ' || current_setting('server_version') || ')'"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
for t in $TABLES; do
  colonnes "$DST" "$t" > "$TMP/$t.dst"
  [ -s "$TMP/$t.dst" ] || { echo "Table voicebank.$t absente de la destination : démarre l'API en ligne une fois (INITIALISER_BASE=true)." >&2; exit 1; }
  colonnes "$SRC" "$t" > "$TMP/$t.src"
  # Colonnes communes, dans l'ordre de la source
  grep -Fxf "$TMP/$t.dst" "$TMP/$t.src" > "$TMP/$t.cols" || true
  [ -s "$TMP/$t.cols" ] || { echo "Aucune colonne commune pour voicebank.$t" >&2; exit 1; }
  ignorees=$(grep -Fxvf "$TMP/$t.dst" "$TMP/$t.src" | tr '\n' ' ')
  [ -n "$ignorees" ] && echo "  $t : colonnes locales ignorées (absentes en ligne) : $ignorees"
  manquantes=$(grep -Fxvf "$TMP/$t.src" "$TMP/$t.dst" | tr '\n' ' ')
  [ -n "$manquantes" ] && echo "  $t : colonnes en ligne absentes en local (valeur par défaut) : $manquantes"
  # Compteurs automatiques (SERIAL / IDENTITY) à recaler après la copie (lus maintenant : la copie verrouille les tables)
  $DST -tA -c "SELECT column_name FROM information_schema.columns WHERE table_schema = 'voicebank'
               AND table_name = '$t' AND (column_default LIKE 'nextval%' OR is_identity = 'YES')" > "$TMP/$t.seq"
done

liste() { sed 's/.*/"&"/' "$TMP/$1.cols" | paste -sd, -; }

echo "→ Copie des données (remplace celles de la destination, en une seule transaction)"
{
  echo "BEGIN;"
  echo "TRUNCATE voicebank.alertes_fraude, voicebank.transactions, voicebank.credits, voicebank.clients, voicebank.logs_corrections RESTART IDENTITY CASCADE;"
  for t in $TABLES; do
    cols=$(liste "$t")
    echo "COPY voicebank.$t ($cols) FROM stdin;"
    $SRC -c "COPY (SELECT $cols FROM voicebank.$t) TO STDOUT"
    echo '\.'
  done
  # Compteurs automatiques recalés sur les données copiées
  for t in $TABLES; do
    while read -r c; do
      [ -n "$c" ] && echo "SELECT setval(pg_get_serial_sequence('voicebank.$t', '$c'), COALESCE((SELECT MAX(\"$c\") FROM voicebank.$t), 0) + 1, false);"
    done < "$TMP/$t.seq"
  done
  echo "COMMIT;"
} | $DST > /dev/null

$DST -tA -c "SELECT 'En ligne : ' || (SELECT COUNT(*) FROM voicebank.clients) || ' clients, '
  || (SELECT COUNT(*) FROM voicebank.transactions) || ' transactions, '
  || (SELECT COUNT(*) FROM voicebank.credits) || ' crédits, '
  || (SELECT COUNT(*) FROM voicebank.alertes_fraude) || ' alertes'"
echo "Publication terminée."
