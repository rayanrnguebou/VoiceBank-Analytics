-- VOICEBANK ANALYTICS - Table logs_corrections + similarite textuelle
-- Auteur : Nguebou Temgoua Rayan
-- Execute ce script dans pgAdmin Query Tool

-- Extension pour la recherche par similarite (deja installee normalement)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Table des corrections
CREATE TABLE IF NOT EXISTS voicebank.logs_corrections (
    id           SERIAL       PRIMARY KEY,
    question     TEXT         NOT NULL,
    sql_correct  TEXT         NOT NULL,
    utilisee     INTEGER      DEFAULT 0,
    score_moyen  NUMERIC(4,2) DEFAULT 0,
    date_ajout   TIMESTAMP    DEFAULT NOW(),
    date_modif   TIMESTAMP    DEFAULT NOW()
);

-- Index de similarite trigram sur la colonne question
CREATE INDEX IF NOT EXISTS idx_corrections_question_trgm
ON voicebank.logs_corrections USING gin(question gin_trgm_ops);

-- Insertion des corrections de base (questions frequentes pre-entrainees)
INSERT INTO voicebank.logs_corrections (question, sql_correct) VALUES

('Montre les clients avec un credit en defaut',
'SELECT c.id_client, c.nom, c.prenom, c.banque, cr.type_credit, cr.montant_fcfa, cr.statut_credit FROM voicebank.credits cr JOIN voicebank.clients c ON cr.id_client = c.id_client WHERE cr.statut_credit = ''Défaut'' LIMIT 100'),

('clients credit defaut',
'SELECT c.id_client, c.nom, c.prenom, c.banque, cr.type_credit, cr.montant_fcfa, cr.statut_credit FROM voicebank.credits cr JOIN voicebank.clients c ON cr.id_client = c.id_client WHERE cr.statut_credit = ''Défaut'' LIMIT 100'),

('credits rembourses',
'SELECT c.id_client, c.nom, c.prenom, cr.type_credit, cr.montant_fcfa, cr.statut_credit FROM voicebank.credits cr JOIN voicebank.clients c ON cr.id_client = c.id_client WHERE cr.statut_credit = ''Remboursé'' LIMIT 100'),

('credits en retard',
'SELECT c.id_client, c.nom, c.prenom, cr.type_credit, cr.montant_fcfa, cr.statut_credit FROM voicebank.credits cr JOIN voicebank.clients c ON cr.id_client = c.id_client WHERE cr.statut_credit = ''En retard'' LIMIT 100'),

('clients diaspora francaise',
'SELECT id_client, nom, prenom, pays_residence, est_diaspora, solde_fcfa, banque FROM voicebank.clients WHERE est_diaspora = ''Oui'' AND pays_residence = ''France'' LIMIT 100'),

('clients diaspora',
'SELECT id_client, nom, prenom, pays_residence, est_diaspora, solde_fcfa, banque FROM voicebank.clients WHERE est_diaspora = ''Oui'' ORDER BY pays_residence LIMIT 100'),

('transactions frauduleuses',
'SELECT id_transaction, id_client, banque, ville, type_transaction, montant_fcfa, date_transaction, statut FROM voicebank.transactions WHERE est_frauduleuse = ''Oui'' ORDER BY montant_fcfa DESC LIMIT 100'),

('alertes critiques',
'SELECT id_alerte, id_transaction, id_client, score_anomalie, niveau_alerte, motif, date_alerte FROM voicebank.alertes_fraude WHERE niveau_alerte = ''Critique'' ORDER BY score_anomalie DESC LIMIT 100'),

('top clients solde',
'SELECT id_client, nom, prenom, banque, ville_compte, solde_fcfa FROM voicebank.clients ORDER BY solde_fcfa DESC LIMIT 10'),

('nombre clients par banque',
'SELECT banque, COUNT(*) as nb_clients, ROUND(AVG(solde_fcfa)) as solde_moyen FROM voicebank.clients GROUP BY banque ORDER BY nb_clients DESC'),

('volume transactions par ville',
'SELECT ville, COUNT(*) as nb_transactions, SUM(montant_fcfa) as volume_total FROM voicebank.transactions GROUP BY ville ORDER BY volume_total DESC'),

('clients risque eleve',
'SELECT id_client, nom, prenom, banque, ville_compte, solde_fcfa, score_risque FROM voicebank.clients WHERE score_risque = ''Élevé'' ORDER BY solde_fcfa DESC LIMIT 100'),

('transactions internationales',
'SELECT id_transaction, id_client, pays_residence, montant_fcfa, devise_origine, type_transaction, date_transaction FROM voicebank.transactions WHERE est_internationale = ''Oui'' ORDER BY montant_fcfa DESC LIMIT 100'),

('clients suspendus',
'SELECT id_client, nom, prenom, banque, ville_compte, statut_compte FROM voicebank.clients WHERE statut_compte = ''Suspendu'' LIMIT 100'),

('dashboard global',
'SELECT * FROM voicebank.v_dashboard_global');

-- Verification
SELECT COUNT(*) as nb_corrections FROM voicebank.logs_corrections;
