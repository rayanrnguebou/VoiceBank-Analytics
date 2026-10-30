#!/bin/sh
# Copie COMPLÈTE d'une base VoiceBank en ligne vers une nouvelle base vide (Render → Neon) :
# comptes, organisations, abonnements, paiements, double authentification, journaux, données.
# Lancé par sauvegarde/passer_a_neon.bat|.sh (dans un conteneur postgres:18), ou directement si
# pg_dump / pg_restore / psql (version 15 ou plus) sont installés.
# Variables : SOURCE (base actuelle), CIBLE (base Neon vide), DOSSIER (où garder la copie),
#             SECURITE (dossier de roles.sql, par défaut celui de ce script).
# La base source n'est JAMAIS modifiée. La cible doit être vide (sinon arrêt sans rien toucher).
set -eu
: "${SOURCE:?SOURCE manquante (URL de la base actuelle)}"
: "${CIBLE:?CIBLE manquante (URL de la base Neon)}"
DOSSIER="${DOSSIER:-.}"
SECURITE="${SECURITE:-$(dirname "$0")}"
TABLES="utilisateurs organisations paiements profils_facturation double_authentification sources_donnees
        clients transactions credits alertes_fraude logs_corrections journal_audit"

compter() { # $1 = URL : nombre de lignes de chaque table, une par ligne « table nombre »
  for t in $TABLES; do
    n=$(psql "$1" -X -tAc "SELECT COUNT(*) FROM voicebank.$t" 2>/dev/null || echo "absente")
    echo "$t $n"
  done
}
secret() { head -c 48 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 40; }

echo "→ 1/5 Vérification des deux bases"
psql "$SOURCE" -X -tAc "SELECT '  Source : ' || current_database() || ' (PostgreSQL ' || current_setting('server_version') || '), '
                        || (SELECT COUNT(*) FROM voicebank.utilisateurs) || ' comptes'"
psql "$CIBLE" -X -tAc "SELECT '  Cible  : ' || current_database() || ' (PostgreSQL ' || current_setting('server_version') || ')'"
deja=$(psql "$CIBLE" -X -tAc "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'voicebank'")
if [ "$deja" != "0" ]; then
  echo "La base cible contient déjà des tables VoiceBank : arrêt, rien n'a été modifié." >&2
  echo "(Si c'est un essai précédent : Neon → Branches → Reset, ou crée une nouvelle base vide.)" >&2
  exit 1
fi

echo "→ 2/5 Copie de la base actuelle (gardée aussi sur ton ordinateur)"
mkdir -p "$DOSSIER"
COPIE="$DOSSIER/avant_neon_$(date +%Y-%m-%d_%H%M).dump"
pg_dump "$SOURCE" -Fc --no-owner --no-acl -f "$COPIE"
echo "  $COPIE ($(du -h "$COPIE" | cut -f1))"

echo "→ 3/5 Restauration dans Neon"
# Quelques messages sans conséquence sont possibles (commentaire du schéma public, extensions déjà là) :
# le résultat est vérifié table par table à l'étape 5.
JOURNAL="$COPIE.restauration.txt"
pg_restore --no-owner --no-acl -d "$CIBLE" "$COPIE" 2> "$JOURNAL" || true
echo "  $(grep -c 'error:' "$JOURNAL" || true) message(s) de pg_restore (détail : $JOURNAL)"

echo "→ 4/5 Comptes à privilèges minimaux (lecture seule pour le SQL de l'IA)"
APP_PWD=$(secret); READER_PWD=$(secret)
psql "$CIBLE" -X -q -v app_pwd="$APP_PWD" -v reader_pwd="$READER_PWD" -f "$SECURITE/roles.sql" 2>&1 \
  | grep -v -e NOTICE -e '^$' | sed 's/^/  /' || true
LECTURE=$(echo "$CIBLE" | sed -E "s#^(postgres(ql)?://)[^@]*@#\1voicebank_reader:$READER_PWD@#")

echo "→ 5/5 Vérification : mêmes nombres de lignes des deux côtés"
compter "$SOURCE" > source.txt
compter "$CIBLE" > cible.txt
ok=1
while read -r t n; do
  m=$(grep "^$t " cible.txt | cut -d' ' -f2)
  if [ "$n" = "$m" ]; then echo "  OK  $t : $n"; else echo "  ÉCART $t : source $n, cible $m"; ok=0; fi
done < source.txt
rm -f source.txt cible.txt
if psql "$LECTURE" -X -tAc "SELECT COUNT(*) FROM voicebank.clients" >/dev/null 2>&1; then
  echo "  OK  le compte lecture seule lit les données"
else
  echo "  ÉCART : le compte lecture seule ne peut pas se connecter ou lire les données"; ok=0
fi
if psql "$LECTURE" -X -tAc "SELECT COUNT(*) FROM voicebank.utilisateurs" >/dev/null 2>&1; then
  echo "  ÉCART : le compte lecture seule voit la table des comptes"; ok=0
else
  echo "  OK  le compte lecture seule ne voit ni les comptes ni les mots de passe"
fi
[ "$ok" = 1 ] || { echo "Copie incomplète : NE CHANGE RIEN sur Render. La base actuelle est intacte." >&2; exit 1; }

cat <<FIN

Copie réussie. Dernière étape, sur Render → voicebank-api → Environment (puis « Save, rebuild and deploy ») :

  DATABASE_URL          = l'URL Neon que tu as collée (celle du propriétaire)
  READONLY_DATABASE_URL = $LECTURE

Et sur GitHub → Settings → Secrets → Actions : BASE_EN_LIGNE_URL = l'URL Neon (sauvegarde de la nuit).
Ces adresses contiennent des mots de passe : ne les colle nulle part ailleurs.
FIN
