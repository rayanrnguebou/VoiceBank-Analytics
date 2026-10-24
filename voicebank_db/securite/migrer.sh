#!/bin/sh
# ╔══════════════════════════════════════════════════════════════════╗
# ║  Migration d'une base VoiceBank créée avec l'ANCIENNE version     ║
# ║  (superutilisateur voicebank_user / mot de passe en dur).         ║
# ║  Lancement : docker compose exec postgres sh /voicebank_securite/migrer.sh
# ║  Sans risque pour les données, et peut être relancé.              ║
# ╚══════════════════════════════════════════════════════════════════╝
set -e
BASE=voicebank_db

# Dans le conteneur, la connexion par socket local ne demande pas de mot de passe.
if psql -U "$POSTGRES_USER" -d "$BASE" -tAc "SELECT 1" >/dev/null 2>&1; then
  ADMIN="$POSTGRES_USER"
elif psql -U voicebank_user -d "$BASE" -tAc "SELECT 1" >/dev/null 2>&1; then
  ADMIN=voicebank_user
else
  echo "Impossible de se connecter à $BASE (ni $POSTGRES_USER ni voicebank_user)." >&2
  exit 1
fi
echo "→ Connecté en tant que $ADMIN"

# 1. Superutilisateur du .env, avec son mot de passe
psql -v ON_ERROR_STOP=1 -q -U "$ADMIN" -d "$BASE" -v nom="$POSTGRES_USER" -v mdp="$POSTGRES_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE %I SUPERUSER LOGIN', :'nom')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'nom') \gexec
ALTER ROLE :"nom" PASSWORD :'mdp';
SQL
echo "→ Superutilisateur $POSTGRES_USER prêt"

P="psql -v ON_ERROR_STOP=1 -q -U $POSTGRES_USER -d $BASE"

# 2. Schéma : ajoute ce qui manque (scripts idempotents, aucune donnée supprimée)
$P -f /docker-entrypoint-initdb.d/01_init_voicebank.sql 2>&1 | grep -v -e NOTICE -e '^$' || true
$P -f /docker-entrypoint-initdb.d/02_corrections_rag.sql 2>&1 | grep -v -e NOTICE -e '^$' || true
echo "→ Schéma à jour"

# 3. Comptes voicebank_app et voicebank_reader
$P -v app_pwd="$VOICEBANK_APP_PASSWORD" -v reader_pwd="$VOICEBANK_READER_PASSWORD" \
   -f /voicebank_securite/roles.sql 2>&1 | grep -v -e NOTICE -e '^$' || true
echo "→ Comptes applicatif et lecture seule prêts"

# 4. L'ancien compte (son mot de passe est public sur GitHub) ne peut plus se connecter
if [ "$POSTGRES_USER" != "voicebank_user" ]; then
  $P -c "ALTER ROLE voicebank_user NOSUPERUSER NOLOGIN" 2>/dev/null \
    && echo "→ Ancien compte voicebank_user désactivé (ses tables sont conservées)" || true
fi

$P -tAc "SELECT 'Données : ' || (SELECT COUNT(*) FROM voicebank.clients) || ' clients, '
               || (SELECT COUNT(*) FROM voicebank.transactions) || ' transactions, '
               || (SELECT COUNT(*) FROM voicebank.credits) || ' crédits'"
echo "Migration terminée. Redémarre l'API : docker compose restart api"
