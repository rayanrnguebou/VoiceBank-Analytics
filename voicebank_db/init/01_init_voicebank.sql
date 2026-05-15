-- ╔══════════════════════════════════════════════════════════╗
-- ║   VOICEBANK ANALYTICS — Initialisation Base de données   ║
-- ║   Auteur : Nguebou Temgoua Rayan                         ║
-- ║   Script exécuté automatiquement au démarrage Docker     ║
-- ╚══════════════════════════════════════════════════════════╝

-- ─────────────────────────────────────
-- Extensions utiles
-- ─────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";   -- recherche textuelle rapide

-- ─────────────────────────────────────
-- Schéma dédié VoiceBank
-- ─────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS voicebank;
SET search_path TO voicebank, public;

-- ══════════════════════════════════════════════════════════
-- TABLE 1 : CLIENTS
-- ══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS voicebank.clients (
    -- Identifiants
    id_client           VARCHAR(12)  PRIMARY KEY,          -- ex: CLI-000001
    numero_compte       VARCHAR(20)  NOT NULL UNIQUE,

    -- Informations personnelles
    nom                 VARCHAR(80)  NOT NULL,
    prenom              VARCHAR(80)  NOT NULL,
    sexe                VARCHAR(10),
    age                 INTEGER      CHECK (age BETWEEN 18 AND 100),
    date_naissance      DATE,
    nationalite         VARCHAR(50)  DEFAULT 'Camerounaise',

    -- Localisation
    pays_residence      VARCHAR(60)  NOT NULL,
    est_diaspora        VARCHAR(3)   CHECK (est_diaspora IN ('Oui','Non')),
    devise_residence    VARCHAR(10),
    telephone           VARCHAR(30),
    email               VARCHAR(120),

    -- Profession
    profession          VARCHAR(80),
    statut_civil        VARCHAR(20),
    niveau_education    VARCHAR(30),

    -- Informations bancaires
    banque              VARCHAR(60)  NOT NULL,
    ville_compte        VARCHAR(50)  NOT NULL,
    agence              VARCHAR(100),
    type_compte         VARCHAR(30),
    date_ouverture      DATE,
    statut_compte       VARCHAR(20)  CHECK (statut_compte IN ('Actif','Inactif','Suspendu')),

    -- Finances
    solde_fcfa          BIGINT       DEFAULT 0,

    -- Risque
    score_risque        VARCHAR(10)  CHECK (score_risque IN ('Faible','Moyen','Élevé')),
    a_fait_defaut_avant VARCHAR(3)   CHECK (a_fait_defaut_avant IN ('Oui','Non')),
    a_credit_immobilier VARCHAR(3)   CHECK (a_credit_immobilier IN ('Oui','Non')),
    a_credit_personnel  VARCHAR(3)   CHECK (a_credit_personnel IN ('Oui','Non')),

    -- Métadonnées
    created_at          TIMESTAMP    DEFAULT NOW(),
    updated_at          TIMESTAMP    DEFAULT NOW()
);

-- Index clients
CREATE INDEX IF NOT EXISTS idx_clients_banque        ON voicebank.clients(banque);
CREATE INDEX IF NOT EXISTS idx_clients_ville         ON voicebank.clients(ville_compte);
CREATE INDEX IF NOT EXISTS idx_clients_pays          ON voicebank.clients(pays_residence);
CREATE INDEX IF NOT EXISTS idx_clients_diaspora      ON voicebank.clients(est_diaspora);
CREATE INDEX IF NOT EXISTS idx_clients_statut        ON voicebank.clients(statut_compte);
CREATE INDEX IF NOT EXISTS idx_clients_risque        ON voicebank.clients(score_risque);
CREATE INDEX IF NOT EXISTS idx_clients_nom_trgm      ON voicebank.clients USING gin(nom gin_trgm_ops);


-- ══════════════════════════════════════════════════════════
-- TABLE 2 : TRANSACTIONS
-- ══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS voicebank.transactions (
    -- Identifiants
    id_transaction      VARCHAR(15)  PRIMARY KEY,          -- ex: TXN-00000001
    id_client           VARCHAR(12)  REFERENCES voicebank.clients(id_client) ON DELETE SET NULL,

    -- Contexte client
    nom_client          VARCHAR(160),
    pays_residence      VARCHAR(60),
    est_diaspora        VARCHAR(3),

    -- Localisation bancaire
    banque              VARCHAR(60),
    agence              VARCHAR(100),
    ville               VARCHAR(50),

    -- Détails transaction
    type_transaction    VARCHAR(40),
    categorie_depense   VARCHAR(50),
    montant_fcfa        BIGINT       NOT NULL CHECK (montant_fcfa > 0),
    devise_origine      VARCHAR(10),
    montant_devise_orig NUMERIC(18,2),

    -- Canal et statut
    canal               VARCHAR(30),
    statut              VARCHAR(20)  CHECK (statut IN ('Réussie','Échouée','Suspecte')),
    est_frauduleuse     VARCHAR(3)   CHECK (est_frauduleuse IN ('Oui','Non')),
    est_internationale  VARCHAR(3)   CHECK (est_internationale IN ('Oui','Non')),

    -- Temporel
    date_transaction    DATE         NOT NULL,
    heure_transaction   TIME,

    -- Soldes avant/après (si disponibles)
    solde_avant_fcfa    BIGINT,
    solde_apres_fcfa    BIGINT,

    -- Métadonnées
    created_at          TIMESTAMP    DEFAULT NOW()
);

-- Index transactions (critiques pour les performances sur 1M+ lignes)
CREATE INDEX IF NOT EXISTS idx_txn_client          ON voicebank.transactions(id_client);
CREATE INDEX IF NOT EXISTS idx_txn_date            ON voicebank.transactions(date_transaction);
CREATE INDEX IF NOT EXISTS idx_txn_date_brin       ON voicebank.transactions USING brin(date_transaction);
CREATE INDEX IF NOT EXISTS idx_txn_fraude          ON voicebank.transactions(est_frauduleuse);
CREATE INDEX IF NOT EXISTS idx_txn_statut          ON voicebank.transactions(statut);
CREATE INDEX IF NOT EXISTS idx_txn_banque          ON voicebank.transactions(banque);
CREATE INDEX IF NOT EXISTS idx_txn_ville           ON voicebank.transactions(ville);
CREATE INDEX IF NOT EXISTS idx_txn_type            ON voicebank.transactions(type_transaction);
CREATE INDEX IF NOT EXISTS idx_txn_internationale  ON voicebank.transactions(est_internationale);
CREATE INDEX IF NOT EXISTS idx_txn_montant         ON voicebank.transactions(montant_fcfa);


-- ══════════════════════════════════════════════════════════
-- TABLE 3 : CREDITS
-- ══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS voicebank.credits (
    -- Identifiants
    id_credit           VARCHAR(12)  PRIMARY KEY,          -- ex: CRD-0000001
    id_client           VARCHAR(12)  REFERENCES voicebank.clients(id_client) ON DELETE SET NULL,

    -- Contexte client
    nom_client          VARCHAR(160),
    pays_residence      VARCHAR(60),
    est_diaspora        VARCHAR(3),

    -- Localisation
    banque              VARCHAR(60),
    ville               VARCHAR(50),

    -- Détails crédit
    type_credit         VARCHAR(50),
    objet_credit        VARCHAR(100),
    montant_fcfa        BIGINT       NOT NULL CHECK (montant_fcfa > 0),
    taux_interet_pct    NUMERIC(5,2) CHECK (taux_interet_pct BETWEEN 0 AND 100),
    duree_mois          INTEGER      CHECK (duree_mois > 0),
    mensualite_fcfa     BIGINT,

    -- Profil financier
    revenu_annuel_fcfa  BIGINT,
    score_credit        INTEGER      CHECK (score_credit BETWEEN 300 AND 850),
    score_risque_client VARCHAR(10),

    -- Garantie
    garantie            VARCHAR(50),

    -- Statut et dates
    statut_credit       VARCHAR(20)  CHECK (statut_credit IN ('En cours','Remboursé','En retard','Défaut')),
    date_debut          DATE,
    date_fin_prevue     DATE,

    -- Métadonnées
    created_at          TIMESTAMP    DEFAULT NOW(),
    updated_at          TIMESTAMP    DEFAULT NOW()
);

-- Index crédits
CREATE INDEX IF NOT EXISTS idx_credits_client      ON voicebank.credits(id_client);
CREATE INDEX IF NOT EXISTS idx_credits_statut      ON voicebank.credits(statut_credit);
CREATE INDEX IF NOT EXISTS idx_credits_banque      ON voicebank.credits(banque);
CREATE INDEX IF NOT EXISTS idx_credits_ville       ON voicebank.credits(ville);
CREATE INDEX IF NOT EXISTS idx_credits_type        ON voicebank.credits(type_credit);
CREATE INDEX IF NOT EXISTS idx_credits_score       ON voicebank.credits(score_credit);


-- ══════════════════════════════════════════════════════════
-- TABLE 4 : ALERTES FRAUDE (générée par le modèle IA)
-- ══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS voicebank.alertes_fraude (
    id_alerte           SERIAL       PRIMARY KEY,
    id_transaction      VARCHAR(15)  REFERENCES voicebank.transactions(id_transaction),
    id_client           VARCHAR(12)  REFERENCES voicebank.clients(id_client),
    score_anomalie      NUMERIC(6,4),                      -- score du modèle (0 à 1)
    niveau_alerte       VARCHAR(10)  CHECK (niveau_alerte IN ('Faible','Moyen','Élevé','Critique')),
    motif               TEXT,
    traitee             BOOLEAN      DEFAULT FALSE,
    date_alerte         TIMESTAMP    DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alertes_client      ON voicebank.alertes_fraude(id_client);
CREATE INDEX IF NOT EXISTS idx_alertes_niveau      ON voicebank.alertes_fraude(niveau_alerte);
CREATE INDEX IF NOT EXISTS idx_alertes_traitee     ON voicebank.alertes_fraude(traitee);


-- ══════════════════════════════════════════════════════════
-- TABLE 5 : LOGS REQUÊTES VOCALES (historique VoiceBank)
-- ══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS voicebank.logs_vocaux (
    id_log              SERIAL       PRIMARY KEY,
    texte_original      TEXT         NOT NULL,             -- ce que l'utilisateur a dit
    texte_transcrit     TEXT,                              -- résultat Whisper
    requete_sql         TEXT,                              -- SQL généré par le LLM
    succes              BOOLEAN      DEFAULT TRUE,
    duree_ms            INTEGER,                           -- temps de réponse en ms
    date_requete        TIMESTAMP    DEFAULT NOW()
);


-- ══════════════════════════════════════════════════════════
-- VUES UTILES (pour Power BI et les requêtes fréquentes)
-- ══════════════════════════════════════════════════════════

-- Vue : résumé clients par banque
CREATE OR REPLACE VIEW voicebank.v_clients_par_banque AS
SELECT
    banque,
    COUNT(*)                                          AS nb_clients,
    COUNT(*) FILTER (WHERE est_diaspora = 'Oui')     AS nb_diaspora,
    COUNT(*) FILTER (WHERE statut_compte = 'Actif')  AS nb_actifs,
    ROUND(AVG(solde_fcfa))                            AS solde_moyen_fcfa,
    COUNT(*) FILTER (WHERE score_risque = 'Élevé')   AS nb_risque_eleve
FROM voicebank.clients
GROUP BY banque
ORDER BY nb_clients DESC;

-- Vue : transactions par mois et par banque
CREATE OR REPLACE VIEW voicebank.v_transactions_mensuelles AS
SELECT
    DATE_TRUNC('month', date_transaction)             AS mois,
    banque,
    COUNT(*)                                          AS nb_transactions,
    SUM(montant_fcfa)                                 AS volume_fcfa,
    COUNT(*) FILTER (WHERE est_frauduleuse = 'Oui')  AS nb_fraudes,
    COUNT(*) FILTER (WHERE est_internationale = 'Oui') AS nb_internationales
FROM voicebank.transactions
GROUP BY DATE_TRUNC('month', date_transaction), banque
ORDER BY mois DESC, nb_transactions DESC;

-- Vue : portefeuille crédit
CREATE OR REPLACE VIEW voicebank.v_portefeuille_credit AS
SELECT
    banque,
    type_credit,
    COUNT(*)                                                    AS nb_dossiers,
    SUM(montant_fcfa)                                           AS encours_fcfa,
    COUNT(*) FILTER (WHERE statut_credit = 'En cours')          AS en_cours,
    COUNT(*) FILTER (WHERE statut_credit = 'En retard')         AS en_retard,
    COUNT(*) FILTER (WHERE statut_credit = 'Défaut')            AS en_defaut,
    ROUND(AVG(taux_interet_pct), 2)                             AS taux_moyen,
    ROUND(AVG(score_credit))                                    AS score_moyen
FROM voicebank.credits
GROUP BY banque, type_credit
ORDER BY encours_fcfa DESC;

-- Vue : tableau de bord global (pour Power BI)
CREATE OR REPLACE VIEW voicebank.v_dashboard_global AS
SELECT
    (SELECT COUNT(*) FROM voicebank.clients)                              AS total_clients,
    (SELECT COUNT(*) FROM voicebank.clients WHERE est_diaspora = 'Oui')  AS clients_diaspora,
    (SELECT COUNT(*) FROM voicebank.transactions)                         AS total_transactions,
    (SELECT SUM(montant_fcfa) FROM voicebank.transactions)                AS volume_total_fcfa,
    (SELECT COUNT(*) FROM voicebank.transactions WHERE est_frauduleuse = 'Oui') AS total_fraudes,
    (SELECT COUNT(*) FROM voicebank.credits)                              AS total_credits,
    (SELECT SUM(montant_fcfa) FROM voicebank.credits WHERE statut_credit = 'En cours') AS encours_credit_fcfa,
    (SELECT COUNT(*) FROM voicebank.credits WHERE statut_credit = 'Défaut') AS credits_defaut;


-- ══════════════════════════════════════════════════════════
-- TRIGGER : mise à jour automatique de updated_at
-- ══════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION voicebank.update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_clients_updated_at
    BEFORE UPDATE ON voicebank.clients
    FOR EACH ROW EXECUTE FUNCTION voicebank.update_updated_at();

CREATE TRIGGER trg_credits_updated_at
    BEFORE UPDATE ON voicebank.credits
    FOR EACH ROW EXECUTE FUNCTION voicebank.update_updated_at();


-- ══════════════════════════════════════════════════════════
-- MESSAGE DE CONFIRMATION
-- ══════════════════════════════════════════════════════════
DO $$
BEGIN
    RAISE NOTICE '✅ VoiceBank Analytics — Base de données initialisée avec succès !';
    RAISE NOTICE '   Tables créées : clients, transactions, credits, alertes_fraude, logs_vocaux';
    RAISE NOTICE '   Vues créées   : v_clients_par_banque, v_transactions_mensuelles, v_portefeuille_credit, v_dashboard_global';
END $$;
