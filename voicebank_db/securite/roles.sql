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
ALTER ROLE voicebank_app    PASSWORD :'app_pwd';
ALTER ROLE voicebank_reader PASSWORD :'reader_pwd';
-- Seul un superutilisateur peut toucher à l'attribut SUPERUSER. Sur une base hébergée (Neon, Render), on est
-- simple propriétaire : les comptes qu'on crée n'ont de toute façon aucun de ces droits.
SELECT format('ALTER ROLE %I NOSUPERUSER NOCREATEDB NOCREATEROLE', r)
FROM unnest(ARRAY['voicebank_app', 'voicebank_reader']) AS r
WHERE (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) \gexec

-- Personne ne crée d'objets dans public
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

-- ── Lecteur : SELECT sur les données, rien d'autre
GRANT USAGE ON SCHEMA voicebank TO voicebank_reader;
GRANT SELECT ON voicebank.clients, voicebank.transactions, voicebank.credits,
                voicebank.alertes_fraude, voicebank.logs_corrections, voicebank.logs_vocaux,
                voicebank.signalements, voicebank.journal_audit, voicebank.evaluations,
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
GRANT DELETE ON voicebank.logs_corrections TO voicebank_app;
GRANT INSERT ON voicebank.signalements, voicebank.journal_audit, voicebank.evaluations TO voicebank_app;
-- Comptes : créés et modifiés par l'API, jamais supprimés ; invisibles pour le lecteur.
GRANT SELECT, INSERT, UPDATE ON voicebank.utilisateurs TO voicebank_app;
REVOKE ALL ON voicebank.utilisateurs FROM voicebank_reader;
-- Abonnements : facturation et paiements, invisibles pour le lecteur et l'IA.
GRANT SELECT, INSERT, UPDATE ON voicebank.profils_facturation, voicebank.paiements TO voicebank_app;
GRANT USAGE ON SEQUENCE voicebank.paiements_id_paiement_seq TO voicebank_app;
REVOKE ALL ON voicebank.profils_facturation, voicebank.paiements FROM voicebank_reader;
-- Connecteur : sources des organisations (le propriétaire peut supprimer les siennes)
-- Paramètres de la plateforme (maintenance…)
GRANT SELECT, INSERT, UPDATE ON voicebank.parametres TO voicebank_app;
REVOKE ALL ON voicebank.parametres FROM voicebank_reader;
-- Organisations clientes (abonnement partagé), invisibles pour le lecteur et l'IA.
GRANT SELECT, INSERT, UPDATE ON voicebank.organisations TO voicebank_app;
GRANT USAGE ON SEQUENCE voicebank.organisations_id_org_seq TO voicebank_app;
REVOKE ALL ON voicebank.organisations FROM voicebank_reader;
-- Récupération du mot de passe : empreintes des codes, invisibles pour le lecteur et l'IA.
GRANT SELECT, INSERT, UPDATE, DELETE ON voicebank.codes_recuperation TO voicebank_app;
GRANT USAGE ON SEQUENCE voicebank.codes_recuperation_id_code_seq TO voicebank_app;
REVOKE ALL ON voicebank.codes_recuperation FROM voicebank_reader;
GRANT SELECT, INSERT, UPDATE, DELETE ON voicebank.sources_donnees, voicebank.sources_fichiers TO voicebank_app;
GRANT USAGE ON SEQUENCE voicebank.sources_donnees_id_source_seq, voicebank.sources_fichiers_id_fichier_seq TO voicebank_app;
REVOKE ALL ON voicebank.sources_donnees, voicebank.sources_fichiers FROM voicebank_reader;
GRANT UPDATE (statut, traite_par, date_traitement) ON voicebank.signalements TO voicebank_app;
GRANT UPDATE (traitee, decision, commentaire, traitee_par, date_traitement)
      ON voicebank.alertes_fraude TO voicebank_app;
GRANT USAGE ON SEQUENCE voicebank.logs_vocaux_id_log_seq, voicebank.logs_corrections_id_seq,
                        voicebank.signalements_id_signalement_seq,
                        voicebank.journal_audit_id_evenement_seq,
                        voicebank.evaluations_id_evaluation_seq TO voicebank_app;
-- Suivi des alertes, notifications, tâches planifiées : invisibles pour le lecteur et l'IA.
GRANT SELECT, INSERT, UPDATE ON voicebank.suivi_alertes, voicebank.preferences_notifications,
                                voicebank.taches_planifiees TO voicebank_app;
GRANT SELECT, INSERT ON voicebank.commentaires_alerte TO voicebank_app;      -- historique : ajout seul
GRANT SELECT, INSERT, DELETE ON voicebank.acces_sources TO voicebank_app;
REVOKE ALL ON voicebank.acces_sources FROM voicebank_reader;
GRANT USAGE ON SEQUENCE voicebank.suivi_alertes_id_suivi_seq,
                        voicebank.commentaires_alerte_id_commentaire_seq TO voicebank_app;
REVOKE ALL ON voicebank.suivi_alertes, voicebank.commentaires_alerte, voicebank.preferences_notifications,
              voicebank.taches_planifiees FROM voicebank_reader;
-- Le journal d'audit est en ajout seul : ni UPDATE ni DELETE pour l'application.
ALTER ROLE voicebank_app SET statement_timeout = '15s';

-- Double authentification et protection des connexions
GRANT SELECT, INSERT, UPDATE, DELETE ON voicebank.double_authentification TO voicebank_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON voicebank.echecs_connexion TO voicebank_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON voicebank.appareils_connus TO voicebank_app;
REVOKE ALL ON voicebank.double_authentification, voicebank.echecs_connexion, voicebank.appareils_connus FROM voicebank_reader;

-- Données personnelles : effacement d'un compte et durées de conservation, par des fonctions à droits limités
GRANT EXECUTE ON FUNCTION voicebank.pseudonymiser_compte(VARCHAR, VARCHAR), voicebank.appliquer_conservation()
      TO voicebank_app;
GRANT DELETE ON voicebank.logs_vocaux TO voicebank_app;              -- questions d'un compte effacé
GRANT DELETE ON voicebank.profils_facturation, voicebank.preferences_notifications TO voicebank_app;

-- Sessions (« Mes appareils ») : invisibles pour le lecteur et l'IA
GRANT SELECT, INSERT, UPDATE, DELETE ON voicebank.sessions TO voicebank_app;
REVOKE ALL ON voicebank.sessions FROM voicebank_reader;

-- Questions favorites : invisibles pour le lecteur et l'IA
GRANT SELECT, INSERT, UPDATE, DELETE ON voicebank.questions_favorites TO voicebank_app;
GRANT USAGE ON SEQUENCE voicebank.questions_favorites_id_favori_seq TO voicebank_app;
REVOKE ALL ON voicebank.questions_favorites FROM voicebank_reader;
