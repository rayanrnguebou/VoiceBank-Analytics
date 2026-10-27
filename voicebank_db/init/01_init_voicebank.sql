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

-- Traitement des alertes par les analystes (v3)
ALTER TABLE voicebank.alertes_fraude ADD COLUMN IF NOT EXISTS decision        VARCHAR(20);
ALTER TABLE voicebank.alertes_fraude ADD COLUMN IF NOT EXISTS commentaire     TEXT;
ALTER TABLE voicebank.alertes_fraude ADD COLUMN IF NOT EXISTS traitee_par     VARCHAR(64);
ALTER TABLE voicebank.alertes_fraude ADD COLUMN IF NOT EXISTS date_traitement TIMESTAMP;
DO $$ BEGIN
    ALTER TABLE voicebank.alertes_fraude ADD CONSTRAINT chk_alerte_decision
        CHECK (decision IS NULL OR decision IN ('Fraude confirmée', 'Faux positif'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;


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
    utilisateur         VARCHAR(64),                       -- compte ayant posé la question
    date_requete        TIMESTAMP    DEFAULT NOW()
);


ALTER TABLE voicebank.logs_vocaux ADD COLUMN IF NOT EXISTS utilisateur VARCHAR(64);


-- ══════════════════════════════════════════════════════════
-- TABLE 6 : SIGNALEMENTS (réponses jugées fausses par un utilisateur)
-- ══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS voicebank.signalements (
    id_signalement      SERIAL       PRIMARY KEY,
    question            TEXT         NOT NULL,
    requete_sql         TEXT,
    source              VARCHAR(20),
    commentaire         TEXT,
    utilisateur         VARCHAR(64)  NOT NULL,
    statut              VARCHAR(10)  NOT NULL DEFAULT 'Ouvert'
                        CHECK (statut IN ('Ouvert', 'Corrigé', 'Rejeté')),
    traite_par          VARCHAR(64),
    date_traitement     TIMESTAMP,
    date_signalement    TIMESTAMP    DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_signalements_statut ON voicebank.signalements(statut);


-- ══════════════════════════════════════════════════════════
-- TABLE 7 : JOURNAL D'AUDIT (ajout seulement, jamais modifié)
-- ══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS voicebank.journal_audit (
    id_evenement        BIGSERIAL    PRIMARY KEY,
    date_evenement      TIMESTAMP    DEFAULT NOW(),
    utilisateur         VARCHAR(64),
    action              VARCHAR(40)  NOT NULL,
    detail              JSONB,
    adresse_ip          VARCHAR(64)
);
CREATE INDEX IF NOT EXISTS idx_audit_date   ON voicebank.journal_audit(date_evenement DESC);
CREATE INDEX IF NOT EXISTS idx_audit_action ON voicebank.journal_audit(action);


-- ══════════════════════════════════════════════════════════
-- TABLE 8 : ÉVALUATIONS DE FIABILITÉ (taux de bonnes réponses)
-- ══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS voicebank.evaluations (
    id_evaluation       SERIAL       PRIMARY KEY,
    date_evaluation     TIMESTAMP    DEFAULT NOW(),
    utilisateur         VARCHAR(64),
    nb_questions        INTEGER,
    nb_reussies         INTEGER,
    taux_reussite       NUMERIC(5,2),
    gemini_actif        BOOLEAN,
    details             JSONB
);


-- ══════════════════════════════════════════════════════════
-- TABLE 9 : COMPTES UTILISATEURS DE L'APPLICATION
-- Jamais lisible par le compte lecture seule ni par l'IA. Pas de suppression :
-- un compte est désactivé (traçabilité de l'audit).
-- ══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS voicebank.utilisateurs (
    nom                 VARCHAR(64)  PRIMARY KEY,
    role                VARCHAR(20)  NOT NULL CHECK (role IN ('analyste', 'admin')),
    hash_mdp            VARCHAR(100) NOT NULL,
    actif               BOOLEAN      NOT NULL DEFAULT TRUE,
    doit_changer_mdp    BOOLEAN      NOT NULL DEFAULT TRUE,
    mdp_provisoire_expire TIMESTAMP,
    echecs_connexion    INTEGER      NOT NULL DEFAULT 0,
    verrouille_jusqua   TIMESTAMP,
    version_jeton       INTEGER      NOT NULL DEFAULT 1,
    cree_par            VARCHAR(64),
    date_creation       TIMESTAMP    NOT NULL DEFAULT NOW(),
    date_modif_mdp      TIMESTAMP    NOT NULL DEFAULT NOW(),
    derniere_connexion  TIMESTAMP
);


-- Offre publique : visiteurs en essai (lecture seule) et clients abonnés
ALTER TABLE voicebank.utilisateurs ADD COLUMN IF NOT EXISTS email        VARCHAR(254);
ALTER TABLE voicebank.utilisateurs ADD COLUMN IF NOT EXISTS nom_complet  VARCHAR(120);
ALTER TABLE voicebank.utilisateurs ADD COLUMN IF NOT EXISTS profil       VARCHAR(30);
ALTER TABLE voicebank.utilisateurs ADD COLUMN IF NOT EXISTS essai_fin    TIMESTAMP;
ALTER TABLE voicebank.utilisateurs ADD COLUMN IF NOT EXISTS abonnement_fin TIMESTAMP;
ALTER TABLE voicebank.utilisateurs ADD COLUMN IF NOT EXISTS formule      VARCHAR(20);
ALTER TABLE voicebank.utilisateurs DROP CONSTRAINT IF EXISTS utilisateurs_role_check;
ALTER TABLE voicebank.utilisateurs ADD CONSTRAINT utilisateurs_role_check
    CHECK (role IN ('analyste', 'admin', 'visiteur', 'client'));
CREATE UNIQUE INDEX IF NOT EXISTS idx_utilisateurs_email ON voicebank.utilisateurs (LOWER(email));

-- ══════════════════════════════════════════════════════════
-- ORGANISATIONS CLIENTES : l'abonnement appartient à l'organisation et il est partagé par ses membres.
-- Celui qui s'abonne en devient l'administrateur ; il invite des analystes (nombre selon la formule).
-- Un particulier est une « organisation » d'une seule personne.
-- ══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS voicebank.organisations (
    id_org              SERIAL       PRIMARY KEY,
    nom                 VARCHAR(150) NOT NULL,
    type_org            VARCHAR(20)  NOT NULL DEFAULT 'organisation' CHECK (type_org IN ('organisation', 'particulier')),
    formule             VARCHAR(20),
    abonnement_fin      TIMESTAMP,
    actif               BOOLEAN      NOT NULL DEFAULT TRUE,
    cree_par            VARCHAR(64),
    date_creation       TIMESTAMP    NOT NULL DEFAULT LOCALTIMESTAMP
);
ALTER TABLE voicebank.utilisateurs ADD COLUMN IF NOT EXISTS id_org   INTEGER REFERENCES voicebank.organisations(id_org);
ALTER TABLE voicebank.utilisateurs ADD COLUMN IF NOT EXISTS role_org VARCHAR(20);
ALTER TABLE voicebank.utilisateurs DROP CONSTRAINT IF EXISTS utilisateurs_role_org_check;
ALTER TABLE voicebank.utilisateurs ADD CONSTRAINT utilisateurs_role_org_check CHECK (role_org IN ('admin', 'analyste'));
CREATE INDEX IF NOT EXISTS idx_utilisateurs_org ON voicebank.utilisateurs (id_org);

-- ══════════════════════════════════════════════════════════
-- TABLE 10 : INFORMATIONS DE FACTURATION (organisation ou particulier)
-- ══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS voicebank.profils_facturation (
    utilisateur         VARCHAR(64)  PRIMARY KEY REFERENCES voicebank.utilisateurs(nom),
    type_client         VARCHAR(20)  NOT NULL CHECK (type_client IN ('organisation', 'particulier')),
    informations        JSONB        NOT NULL,
    date_maj            TIMESTAMP    NOT NULL DEFAULT NOW()
);

-- ══════════════════════════════════════════════════════════
-- TABLE 11 : PAIEMENTS DES ABONNEMENTS
-- Le montant est fixé par le serveur ; un paiement n'active l'abonnement qu'une seule fois.
-- ══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS voicebank.paiements (
    id_paiement         SERIAL       PRIMARY KEY,
    reference           VARCHAR(64)  NOT NULL UNIQUE,
    utilisateur         VARCHAR(64)  NOT NULL REFERENCES voicebank.utilisateurs(nom),
    formule             VARCHAR(20)  NOT NULL,
    duree_jours         INTEGER      NOT NULL CHECK (duree_jours > 0),
    montant             INTEGER      NOT NULL CHECK (montant > 0),
    devise              CHAR(3)      NOT NULL DEFAULT 'XAF',
    statut              VARCHAR(20)  NOT NULL DEFAULT 'en_attente'
                        CHECK (statut IN ('en_attente', 'paye', 'echoue', 'annule')),
    fournisseur         VARCHAR(20)  NOT NULL,
    reference_fournisseur VARCHAR(100),
    date_creation       TIMESTAMP    NOT NULL DEFAULT NOW(),
    date_paiement       TIMESTAMP,
    abonnement_fin      TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_paiements_utilisateur ON voicebank.paiements (utilisateur, date_creation DESC);
ALTER TABLE voicebank.paiements ADD COLUMN IF NOT EXISTS id_org INTEGER REFERENCES voicebank.organisations(id_org);


-- ══════════════════════════════════════════════════════════
-- TABLE 11 bis : CODES DE RÉCUPÉRATION DU MOT DE PASSE (envoyés par e-mail)
-- Seule l'empreinte du code est conservée ; 15 minutes, 5 essais, un seul usage.
-- ══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS voicebank.codes_recuperation (
    id_code             SERIAL       PRIMARY KEY,
    utilisateur         VARCHAR(64)  NOT NULL REFERENCES voicebank.utilisateurs(nom) ON DELETE CASCADE,
    empreinte           CHAR(64)     NOT NULL,
    expire              TIMESTAMP    NOT NULL,
    tentatives          INTEGER      NOT NULL DEFAULT 0,
    utilise             BOOLEAN      NOT NULL DEFAULT FALSE,
    adresse_ip          VARCHAR(64),
    date_creation       TIMESTAMP    NOT NULL DEFAULT LOCALTIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_codes_recuperation ON voicebank.codes_recuperation (utilisateur, date_creation DESC);
-- « recuperation » : code à 6 chiffres ; « invitation » : lien d'activation d'un compte créé par un administrateur
ALTER TABLE voicebank.codes_recuperation ADD COLUMN IF NOT EXISTS type_code VARCHAR(20) NOT NULL DEFAULT 'recuperation';


-- ══════════════════════════════════════════════════════════
-- TABLE 12 : SOURCES DE DONNÉES DES ORGANISATIONS (connecteur)
-- Identifiants de connexion CHIFFRÉS ; seul le propriétaire peut interroger sa source.
-- ══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS voicebank.sources_donnees (
    id_source           SERIAL       PRIMARY KEY,
    proprietaire        VARCHAR(64)  NOT NULL REFERENCES voicebank.utilisateurs(nom),
    nom                 VARCHAR(80)  NOT NULL,
    type_source         VARCHAR(20)  NOT NULL CHECK (type_source IN ('postgresql', 'mysql', 'sqlserver', 'fichier')),
    config_chiffree     TEXT,
    resume_connexion    VARCHAR(200),
    statut              VARCHAR(20)  NOT NULL DEFAULT 'analyse' CHECK (statut IN ('analyse', 'pret', 'erreur')),
    erreur              VARCHAR(500),
    profil              JSONB,
    masquer_pii         BOOLEAN      NOT NULL DEFAULT TRUE,
    date_creation       TIMESTAMP    NOT NULL DEFAULT NOW(),
    date_analyse        TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_sources_proprietaire ON voicebank.sources_donnees (proprietaire);
-- Monnaie des montants de la base (NULL : détectée automatiquement, sinon FCFA)
ALTER TABLE voicebank.sources_donnees ADD COLUMN IF NOT EXISTS devise CHAR(3);

CREATE TABLE IF NOT EXISTS voicebank.sources_fichiers (
    id_fichier          SERIAL       PRIMARY KEY,
    id_source           INTEGER      NOT NULL REFERENCES voicebank.sources_donnees(id_source) ON DELETE CASCADE,
    nom_fichier         VARCHAR(200) NOT NULL,
    contenu             BYTEA        NOT NULL,
    taille              INTEGER      NOT NULL,
    date_ajout          TIMESTAMP    NOT NULL DEFAULT NOW()
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


-- Paramètres de la plateforme modifiables sans redéploiement (ex. mode maintenance)
CREATE TABLE IF NOT EXISTS voicebank.parametres (
    cle                 VARCHAR(50)  PRIMARY KEY,
    valeur              JSONB        NOT NULL,
    modifie_par         VARCHAR(64),
    date_modif          TIMESTAMP    NOT NULL DEFAULT LOCALTIMESTAMP
);

-- Sources partagées dans l'organisation
ALTER TABLE voicebank.sources_donnees ADD COLUMN IF NOT EXISTS id_org INTEGER REFERENCES voicebank.organisations(id_org);
-- Base proposée par défaut aux membres de l'organisation (à la connexion)
ALTER TABLE voicebank.organisations ADD COLUMN IF NOT EXISTS source_defaut INTEGER
    REFERENCES voicebank.sources_donnees(id_source) ON DELETE SET NULL;

-- Migration : chaque abonné existant devient l'administrateur de sa propre organisation
DO $$
DECLARE u RECORD; o INTEGER;
BEGIN
    FOR u IN SELECT nom, nom_complet, formule, abonnement_fin FROM voicebank.utilisateurs
             WHERE role = 'client' AND id_org IS NULL LOOP
        INSERT INTO voicebank.organisations (nom, type_org, formule, abonnement_fin, cree_par)
        SELECT COALESCE(f.informations->>'raison_sociale', f.informations->>'nom_complet', u.nom_complet, u.nom),
               COALESCE(f.type_client, 'particulier'), u.formule, u.abonnement_fin, u.nom
        FROM (SELECT 1) x LEFT JOIN voicebank.profils_facturation f ON f.utilisateur = u.nom
        RETURNING id_org INTO o;
        UPDATE voicebank.utilisateurs SET id_org = o, role_org = 'admin' WHERE nom = u.nom;
        UPDATE voicebank.sources_donnees SET id_org = o WHERE proprietaire = u.nom;
        UPDATE voicebank.paiements SET id_org = o WHERE utilisateur = u.nom;
    END LOOP;
END $$;


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

CREATE OR REPLACE TRIGGER trg_clients_updated_at
    BEFORE UPDATE ON voicebank.clients
    FOR EACH ROW EXECUTE FUNCTION voicebank.update_updated_at();

CREATE OR REPLACE TRIGGER trg_credits_updated_at
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
