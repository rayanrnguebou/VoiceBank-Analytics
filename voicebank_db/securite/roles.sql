-- ╔══════════════════════════════════════════════════════════╗
-- ║  VOICEBANK — Comptes à privilèges minimaux (idempotent)  ║
-- ╚══════════════════════════════════════════════════════════╝
-- Variables psql attendues : app_pwd, reader_pwd
--   voicebank_app    : utilisé par l'API (lecture + écriture des journaux et du RAG)
--   voicebank_reader : exécute le SQL généré par l'IA (lecture seule, sans journaux)
-- Utilisable aussi sur une base existante :
--   psql "$URL_ADMIN" -v app_pwd=... -v reader_pwd=... -f roles.sql

\set ON_ERROR_STOP on

-- Migration pour les bases créées avec l'ancien script
ALTER TABLE voicebank.logs_vocaux ADD COLUMN IF NOT EXISTS utilisateur VARCHAR(64);

SELECT format('CREATE ROLE voicebank_app LOGIN PASSWORD %L', :'app_pwd')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'voicebank_app') \gexec
SELECT format('CREATE ROLE voicebank_reader LOGIN PASSWORD %L', :'reader_pwd')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'voicebank_reader') \gexec
ALTER ROLE voicebank_app    PASSWORD :'app_pwd'    NOSUPERUSER NOCREATEDB NOCREATEROLE;
ALTER ROLE voicebank_reader PASSWORD :'reader_pwd' NOSUPERUSER NOCREATEDB NOCREATEROLE;

-- Personne ne crée d'objets dans public
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

-- ── Lecteur : SELECT sur les données, rien d'autre
GRANT USAGE ON SCHEMA voicebank TO voicebank_reader;
GRANT SELECT ON voicebank.clients, voicebank.transactions, voicebank.credits,
                voicebank.alertes_fraude, voicebank.logs_corrections, voicebank.logs_vocaux,
                voicebank.v_dashboard_global, voicebank.v_clients_par_banque,
                voicebank.v_transactions_mensuelles, voicebank.v_portefeuille_credit
      TO voicebank_reader;
ALTER ROLE voicebank_reader SET default_transaction_read_only = on;
ALTER ROLE voicebank_reader SET statement_timeout = '10s';

-- ── Application : lecture + écriture limitée aux journaux et au RAG
GRANT USAGE ON SCHEMA voicebank TO voicebank_app;
GRANT SELECT ON ALL TABLES IN SCHEMA voicebank TO voicebank_app;
GRANT INSERT ON voicebank.logs_vocaux TO voicebank_app;
GRANT INSERT, UPDATE ON voicebank.logs_corrections TO voicebank_app;
GRANT USAGE ON SEQUENCE voicebank.logs_vocaux_id_log_seq, voicebank.logs_corrections_id_seq TO voicebank_app;
ALTER ROLE voicebank_app SET statement_timeout = '15s';
