# VoiceBank Analytics

![Tests](https://github.com/rayanrnguebou/VoiceBank-Analytics/actions/workflows/tests.yml/badge.svg)

Assistant bancaire vocal : on pose une question en français, au micro ou au clavier
(« crédits en défaut », puis « et à Douala ? »). L'API la traduit en SQL, l'exécute en lecture
seule et répond **par un graphique et une phrase lue à voix haute**. Autour de cet assistant :
détection de fraude avec traitement des alertes, score de crédit expliqué, apprentissage à partir
des corrections, mesure de la fiabilité et journal d'audit.

**Auteur : Nguebou Temgoua Rayan**

| Couche | Technologies |
|---|---|
| Interface | React 19, Tailwind, Recharts, jsPDF, Web Speech API (dictée et lecture) |
| API | FastAPI, SQLAlchemy, sqlglot (validation SQL), JWT, bcrypt |
| IA | Gemini (texte → SQL, résumés), Whisper (Groq ou local faster-whisper), scikit-learn, XGBoost (SHAP natif) |
| Données | PostgreSQL 15 (pg_trgm pour le RAG), Power BI |
| Qualité | 139 tests API, tests d'interface, GitHub Actions, jeu d'évaluation de 50 questions |

## Fonctionnalités

| | |
|---|---|
| **Question vocale ou écrite** | Le texte s'écrit pendant qu'on parle, puis Whisper le finalise. |
| **Réponse rédigée et parlée** | Résumé en 1-2 phrases (Gemini, ou calcul local), lu par le navigateur, puis une **analyse orale** plus poussée (tendance, concentration, risques, actions conseillées, question de suite) qui n'est pas affichée. Bouton « Lecture » pour arrêter, 🔊 pour couper la voix. |
| **Mode conversation** | La réponse se termine par une question (« Veux-tu voir les alertes critiques ? ») : le micro s'ouvre tout seul, on répond « oui », « non merci » ou une autre question, sans cliquer. L'écoute s'arrête seule après un silence ou si personne ne parle (7 s). Icône 💬 pour désactiver. |
| **Questions de suite** | « et à Douala ? », « seulement BICEC », « en 2025 » reprennent la question précédente. |
| **Pertinence** | Une règle locale ne répond que si elle couvre toute la question ; sinon Gemini, ou réponse marquée « approximative ». |
| **Apprentissage** | Bouton « Réponse incorrecte ? » ; l'admin corrige, teste et enregistre la requête (RAG). |
| **Fiabilité mesurée** | 50 questions de référence, taux de bonnes réponses par catégorie et par source. |
| **Fraude** | Score Isolation Forest + XGBoost, alertes à traiter (fraude confirmée / faux positif). |
| **Crédit** | Probabilité de défaut, facteurs explicatifs (SHAP), crédits en cours les plus à risque. |
| **Données personnelles** | Noms, e-mails, téléphones masqués pour le rôle analyste ; jamais envoyés à Gemini pour les résumés. |
| **Essai et abonnements** | Accueil « Visiteur ou Organisation », essai gratuit 3 jours en lecture seule, formules jour / semaine / mois / année payées en FCFA (MTN MoMo, Orange Money, carte). |
| **Connecteur « Mes données »** | Branche une base PostgreSQL, MySQL/MariaDB, SQL Server ou des fichiers Excel/CSV : analyse de la structure et du sens métier, diagnostic de qualité, puis questions en français dans le dialecte de la base. |
| **Monnaie d'affichage** | Sélecteur en haut de l'écran (FCFA CEMAC / UEMOA, euro, dollar, livre, dollar canadien, franc suisse, yuan, naira) : réponses, résumé parlé, graphiques, indicateurs, alertes, crédit et tarifs suivent la monnaie choisie. FCFA ↔ euro à la parité officielle (655,957), autres taux BCE mis à jour toutes les 12 h. Les abonnements restent débités en FCFA. Pour une base connectée, la monnaie de ses montants est détectée (colonne « currency ») ou choisie. |
| **Comptes** | Créés par l'administrateur (pas d'inscription libre), mot de passe provisoire à changer à la 1re connexion, blocage après 5 échecs, désactivation sans suppression. |
| **Audit** | Connexions, consultations de fiches, corrections, alertes traitées, gestion des comptes : journal en ajout seul. |

## Fonctionnement

```
Voix ──Whisper (Groq, sinon local)──▶ texte ─┐
Texte ───────────────────────────────────────┤
                                             ▼
   question de suite ? ──oui──▶ Gemini avec la question précédente (sinon filtre local)
                                             ▼ non
   1. correction RAG quasi identique (validée par un admin)
   2. règle locale qui couvre TOUTE la question
   3. correction RAG proche
   4. Gemini
   5. sans Gemini : réponse approximative signalée
                                             ▼
   garde SQL : 1 seul SELECT, tables voicebank uniquement, fonctions système interdites
                                             ▼
   exécution par un compte LECTURE SEULE, transaction READ ONLY, timeout 5 s, 1000 lignes max
                                             ▼
   masquage des données personnelles (analyste) → résumé → réponse
```

## Démarrage rapide (Docker)

```bash
cp .env.example .env
# Remplis .env : mots de passe, JWT_SECRET, VOICEBANK_USERS, clés Gemini / Groq
docker compose up -d --build
```

- Interface : http://localhost:3000
- API : http://localhost:8000/health (la doc `/docs` n'est active qu'en développement)
- pgAdmin (optionnel) : `docker compose --profile admin up -d` puis http://localhost:5050

Charger les données (CSV générés par `pipeline_voicebank.py`, dans `output_voicebank/`) :

```bash
ADMIN_DATABASE_URL=postgresql://voicebank_admin:MOT_DE_PASSE@localhost:5432/voicebank_db \
  python voicebank_db/charger_csv_postgres.py
```

### Comptes utilisateurs

**Pas d'inscription libre** : c'est une application bancaire, seul un administrateur crée des comptes.

1. **Premier administrateur** (une seule fois) : il est défini dans `VOICEBANK_USERS` sous la forme
   `nom:role:hash_bcrypt` (plusieurs comptes séparés par des virgules).

   ```bash
   cd voicebank_api
   pip install bcrypt
   python -m app.outils.creer_hash        # demande le mot de passe, affiche le hash
   ```

   Dans `.env`, mets la valeur entre **apostrophes simples** (le hash contient des `$`) :
   `VOICEBANK_USERS='rayan:admin:$2b$12$...'`. Sur Render, sans apostrophes.
   Au démarrage, l'API copie ces comptes dans la base (table `voicebank.utilisateurs`) s'ils n'y
   sont pas encore. Ensuite **la base fait foi** : un mot de passe changé ou un compte désactivé
   dans l'interface n'est pas écrasé par la configuration.

2. **Les autres comptes** : menu **Administration → Comptes** → identifiant + rôle → **Créer**.
   - Un mot de passe provisoire de 16 caractères s'affiche **une seule fois**, valable 72 h.
     Transmets-le par un autre canal que l'identifiant.
   - À la première connexion, la personne doit le remplacer (12 caractères minimum, 3 types de
     caractères, sans son identifiant) avant d'accéder à quoi que ce soit.

| Rôle | Droits |
|---|---|
| `analyste` | Questions, tableaux de bord, alertes, scores. Noms et coordonnées des clients masqués. |
| `admin` | Tout, plus : comptes, corrections (apprentissage), SQL manuel, fiabilité, audit. |

**Protections** : 5 mots de passe faux → compte bloqué 15 min (même message d'erreur que pour un
compte inconnu) ; **Réinitialiser** donne un nouveau mot de passe provisoire et débloque ; changer
de mot de passe, de rôle ou désactiver un compte **déconnecte immédiatement** ses sessions ; aucun
compte n'est supprimé (l'audit reste lisible) ; on ne peut ni se désactiver soi-même ni retirer le
dernier administrateur. Chacun peut changer son mot de passe (icône 🔑 en bas de la barre latérale).

#### Mot de passe oublié (code par e-mail)

Sur l'écran de connexion, **Mot de passe oublié ?** envoie un **code à 6 chiffres** valable 15 minutes à
l'adresse du compte (e-mail des visiteurs et abonnés ; pour les comptes internes, l'adresse saisie à la
création ou dans 🔑 → **E-mail de récupération**). Le code ne sert qu'une fois, est détruit après 5 essais
faux, 3 demandes par heure au plus ; la réponse est identique que le compte existe ou non ; le changement
débloque le compte, déconnecte toutes les sessions et un e-mail de confirmation est envoyé.

Envoi des e-mails (sans configuration, le lien est remplacé par « demande à ton administrateur ») :
- **Brevo** (recommandé, gratuit jusqu'à 300 e-mails/jour, fonctionne sur Render) : crée un compte sur
  brevo.com, valide ton adresse d'expéditeur (**Expéditeurs**), crée une clé (**SMTP & API → Clés API**),
  puis renseigne `BREVO_API_KEY` et `EMAIL_EXPEDITEUR` ;
- ou **SMTP** (`SMTP_HOTE`, `SMTP_PORT`, `SMTP_UTILISATEUR`, `SMTP_MOT_DE_PASSE`, `EMAIL_EXPEDITEUR`),
  par exemple Gmail avec un « mot de passe d'application ». Render bloque le SMTP en offre gratuite.

## Clés IA (Gemini et Groq)

Les deux sont facultatives : sans elles, les questions fréquentes marchent (règles locales + RAG),
mais pas les questions libres (Gemini) ni le micro (Groq).

| Service | Où créer la clé | Variable |
|---|---|---|
| Gemini (texte → SQL) | https://aistudio.google.com/app/apikey | `GEMINI_API_KEY` (+ `GEMINI_MODEL`, défaut `gemini-3.5-flash-lite`) |
| Groq (voix → texte) | https://console.groq.com/keys | `GROQ_API_KEY` (+ `GROQ_WHISPER_MODEL`, défaut `whisper-large-v3`) |

Vérifier les clés : `cd voicebank_api && python -m app.outils.tester_ia`

**Micro sans clé Groq** : l'API bascule automatiquement sur le Whisper local du dossier
`voicebank_whisper` (faster-whisper, gratuit, hors ligne après le premier téléchargement du modèle).
Il prend aussi le relais si Groq est en panne. Détails et réglages : `voicebank_whisper/README.md`.

## Reprendre une base créée avec l'ancienne version

Si tu avais déjà lancé l'ancien `docker-compose` (base dans le volume `voicebank_postgres_data`),
tes données sont conservées. Il faut seulement mettre le schéma et les comptes à niveau, une fois :

```bash
docker rm -f voicebank_postgres voicebank_pgadmin voicebank_api voicebank_ui   # anciens conteneurs (pas les données)
docker compose up -d
docker compose exec postgres sh /voicebank_securite/migrer.sh
docker compose restart api
```

Le script crée le superutilisateur du `.env`, ajoute ce qui manque au schéma, crée
`voicebank_app` / `voicebank_reader` et désactive l'ancien compte `voicebank_user`
(dont le mot de passe était publié sur GitHub). Il peut être relancé sans risque.
**Relance-le après chaque mise à jour du projet** : il ajoute les nouvelles tables et colonnes
(signalements, audit, évaluations, traitement des alertes, comptes) sans toucher aux données.
Tant que la table des comptes n'existe pas, l'API reste utilisable avec `VOICEBANK_USERS` seul.
**Ne lance jamais `docker compose down -v`** : `-v` supprime le volume, donc les données.

## Sauvegarder la base

### En local (Docker)

Tes données n'existent que dans le volume Docker : sauvegarde-les.

| | Windows | macOS / Linux |
|---|---|---|
| Sauvegarder maintenant | double-clic sur `sauvegarde\sauvegarder.bat` | `sh sauvegarde/sauvegarder.sh` |
| **Sauvegarde automatique chaque jour à 20 h** | double-clic sur `sauvegarde\planifier.bat` (une fois) | `crontab -e` → `0 20 * * * sh /chemin/sauvegarde/sauvegarder.sh` |
| Restaurer | `sauvegarde\restaurer.bat sauvegardes\voicebank_AAAA-MM-JJ_HHMM.dump` | `sh sauvegarde/restaurer.sh sauvegardes/…dump` |

Les fichiers vont dans `sauvegardes/` (exclu de Git, les 10 plus récents sont gardés, résultat de
chaque sauvegarde dans `sauvegardes/journal.txt`). Docker Desktop doit être lancé à 20 h.
Copie-les de temps en temps hors de l'ordinateur (clé USB, disque externe, cloud privé).

### En ligne (Render)

La base gratuite de Render n'a pas de sauvegarde : un workflow GitHub en fait une **chaque nuit**,
**chiffrée** (AES-256), conservée 30 jours dans l'onglet *Actions* du dépôt.

1. GitHub → dépôt → **Settings → Secrets and variables → Actions → New repository secret** :
   - `RENDER_DATABASE_URL` : Render → voicebank-db → **Connect** → *External Database URL* ;
   - `SAUVEGARDE_MOT_DE_PASSE` : une longue phrase secrète, notée en lieu sûr (sans elle, les
     sauvegardes sont illisibles).
2. Onglet **Actions → Sauvegarde en ligne → Run workflow** pour tester tout de suite.

Restaurer une sauvegarde en ligne (Git Bash ou macOS / Linux) :

```bash
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -in voicebank_en_ligne_….dump.enc -out en_ligne.dump
docker run --rm -i -e URL="<External Database URL>" postgres:18-alpine \
  sh -c 'pg_restore --clean --if-exists --no-owner -d "$URL"' < en_ligne.dump
```

### Mettre en ligne les données de ton PC

Pour que le site public montre les mêmes données que ta base locale :
`sauvegarde\publier_en_ligne.bat` (ou `sh sauvegarde/publier_en_ligne.sh`), puis colle l'*External
Database URL* de Render. Le script sauvegarde d'abord ta base locale, puis remplace en ligne les
clients, crédits, transactions, alertes et corrections apprises. **Les comptes, mots de passe,
paiements et journaux d'audit ne sont jamais copiés.** À relancer quand tes données changent.

## Connecteur : brancher les données d'une organisation

Menu **Mes données → Connecter une source** (abonnés et administrateur ; pendant l'essai, une source de
démonstration est explorable).

| Source | Ce qu'il faut |
|---|---|
| PostgreSQL, MySQL / MariaDB, SQL Server | adresse, port, base, **compte en lecture seule** (le formulaire donne le SQL pour le créer), serveur joignable depuis Internet |
| Excel (.xlsx) / CSV | jusqu'à 5 fichiers de 10 Mo ; chaque feuille ou fichier devient une table |

**Ce que fait l'analyse, quel que soit le schéma** (noms en français ou en anglais, sans documentation) :
- rôle de chaque colonne : montant, date, statut, lieu, catégorie, taux, score, identifiant, indicateur de fraude ;
- entités (clients, comptes, crédits, transactions, agences…) et **domaine** (banque, microfinance, assurance, commerce) ;
- **relations** déclarées, ou déduites des noms (`customer_id` → `customers`) ;
- **données personnelles** (noms, e-mails, téléphones, numéros de compte, pièces d'identité) et **secrets**
  (mots de passe, jetons) : les premières sont masquées et jamais envoyées à l'IA, les seconds ne sont jamais lus ;
- **diagnostic de qualité** avec une note sur 100 : références orphelines, doublons, valeurs manquantes,
  montants négatifs, dates futures ou improbables, colonnes constantes, données anciennes ;
- **questions suggérées** adaptées à la base.

**Indicateurs et tableau de bord adaptés à la base** : quand une source est choisie dans « Données interrogées »,
les quatre indicateurs de l'assistant et le **Tableau de bord** sont calculés d'après sa structure — effectifs des
entités principales (clients, comptes, transactions…), nombre de fraudes s'il existe un indicateur de fraude,
montant total (encours de crédits en priorité), évolution mensuelle (nombre et montant, sans les dates futures)
et répartitions par lieu, statut ou catégorie. Jamais de regroupement sur une donnée personnelle ; montants dans
la monnaie choisie ; résultat gardé 10 minutes.

**Questions en français** (assistant, sélecteur « Données interrogées ») : Gemini écrit la requête dans le dialecte
de la base (PostgreSQL, MySQL, T-SQL, SQLite) à partir de la carte des données ; sans Gemini, un moteur local
comprend les formulations courantes — totaux, moyennes, comptages, « par mois », « par ville », « top 10 clients
par solde », filtres (« à Douala », « en retard », « en 2025 », « frauduleuses ») — même si la base est en anglais.

**Sécurité** : connexion en lecture seule (session en lecture seule, transaction toujours annulée, délai de 20 s),
garde SQL par dialecte (une seule requête SELECT, tables connues uniquement, fonctions système interdites),
identifiants chiffrés (`CLE_SOURCES`), adresses privées refusées en ligne (anti-SSRF), une source n'est visible
et interrogeable que par son propriétaire, l'analyse ne lit qu'un échantillon de 500 lignes par table.
En local avec Docker, une base installée sur le même PC se joint avec l'hôte `host.docker.internal`.

## Offre publique : essai gratuit et abonnements

L'accueil demande **« Tu es… » Visiteur ou Organisation** :

- **Visiteur** : s'inscrit avec nom, e-mail et mot de passe, et obtient un **essai gratuit de 3 jours**.
  Il voit **tout l'outil, administration comprise**, mais en **lecture seule** : le serveur refuse
  toute modification (alertes, corrections, comptes, évaluation…) et l'administration lui est
  montrée **anonymisée** (il ne voit ni les autres comptes, ni leurs questions, ni leurs adresses IP).
  Quota : 30 questions par jour (protège les coûts Gemini / Groq).
- **Organisation** : se connecte avec un compte créé par son administrateur (accès complet selon le rôle).
- **Abonnement** (Jour 500 · Semaine 2 000 · Mois 6 000 · Année 60 000 FCFA, modifiables avec
  `PRIX_JOUR`… sans toucher au code) : à la fin de l'essai, seule la page *Abonnement* reste accessible.
  Le visiteur choisit une formule, indique s'il est une **organisation** (raison sociale, secteur,
  effectif, ville, responsable, fonction, e-mail, téléphone, NIU et RCCM facultatifs) ou un
  **particulier** (nom, profession, ville, e-mail, téléphone), puis paie. Un achat s'ajoute à la
  durée restante ; pas de reconduction automatique.
- L'administrateur suit visiteurs, organisations clientes, paiements et revenus dans **Administration → Abonnements**.

### Organisations clientes : un abonnement partagé

- L'abonnement appartient à l'**organisation**. Celui qui paie le premier abonnement en devient
  l'**administrateur** ; il voit **Mon organisation → Membres**.
- Il **invite** ses collègues (nom, e-mail, rôle *Analyste* ou *Administrateur*). Chacun reçoit un
  **e-mail d'invitation** avec un lien d'activation (72 h, usage unique) pour choisir son mot de passe.
  Sans service d'e-mail, un mot de passe provisoire s'affiche une fois, à transmettre.
- **Comptes inclus** (administrateur compris) : Jour et Semaine 3, Mois 10, Année 25 (`COMPTES_JOUR`,
  `COMPTES_SEMAINE`, `COMPTES_MOIS`, `COMPTES_ANNEE`). Un **particulier** a un seul compte.
- Tous les membres **partagent** l'abonnement : à son échéance, toute l'organisation est bloquée jusqu'au
  renouvellement par un administrateur. Les analystes ne voient ni l'abonnement ni les paiements.
- Les **bases connectées** sont partagées dans l'organisation : l'administrateur les branche, tous les membres
  les interrogent. Une organisation ne voit jamais les membres ni les données d'une autre.
- Les membres ne voient **pas** l'administration de la plateforme (comptes, audit, apprentissage…), réservée
  au super-administrateur ; seuls les visiteurs en essai la découvrent, anonymisée et en lecture seule.

**E-mails professionnels** (vouvoiement, en-tête, récapitulatif, bouton, signature) : bienvenue à l'essai,
reçu de paiement, invitation, code de vérification, confirmation de changement de mot de passe. Signature
réglable : `EMAIL_SIGNATURE_NOM`, `EMAIL_SIGNATURE_FONCTION`, `EMAIL_CONTACT` (adresse de réponse).
**Administration → Abonnements → Envoyer un test** affiche la raison exacte d'un échec d'envoi.
Avec Brevo, si le test répond « Unrecognised IP address » : dans Brevo, **Sécurité → IP autorisées**,
désactive le blocage des adresses IP inconnues (l'adresse de Render change).

### Maintenance et mises à jour

Menu **Administration → Maintenance** (administrateur de la plateforme) :
- **Annoncer une maintenance** : message, début, fin. Un bandeau prévient tous les utilisateurs (page
  d'accueil et application) ; il disparaît après l'heure de fin.
- **Activer la maintenance** : tous les utilisateurs voient une page « Maintenance en cours » avec ton
  message et l'heure de retour prévue ; leurs requêtes et connexions sont refusées (réponse 503). Toi, tu
  restes connecté et tu peux tout tester (« Accès administrateur » sur la page de maintenance). Les
  paiements NotchPay continuent d'arriver. **Terminer la maintenance** : la page des utilisateurs revient
  toute seule à l'application.
- **Secours** : si la base est hors service, mets `MAINTENANCE=true` dans les variables Render de l'API.
- Pendant un **redéploiement** (serveur momentanément injoignable), l'application affiche « Le serveur ne
  répond pas : mise à jour ou redémarrage en cours, reconnexion automatique » et reprend seule.

### Paiement (NotchPay : MTN MoMo, Orange Money, cartes)

Intégration gratuite, sans abonnement : NotchPay prend seulement une commission par paiement.

1. Crée un compte sur [business.notchpay.co](https://business.notchpay.co) et fais valider ton
   identité (KYC) pour encaisser en réel.
2. **Settings → API Keys** : copie la *Public key* (d'abord celle de **test**, qui contient `test_`)
   et la *Hash key* des webhooks.
3. **Settings → Webhooks** : ajoute l'adresse `https://voicebank-api.onrender.com/paiements/notchpay/webhook`.
4. Render → voicebank-api → **Environment** : `NOTCHPAY_PUBLIC_KEY` et `NOTCHPAY_HASH_KEY`, puis Save.
5. Teste un paiement en mode test, puis remplace par les clés **live**.

Sécurité des paiements :
- le montant et la durée sont fixés **par le serveur** (un prix envoyé par le navigateur est ignoré) ;
- la saisie du paiement se fait sur la **page de NotchPay** : aucune donnée de carte ou de mobile
  money ne passe par VoiceBank ;
- l'abonnement n'est activé qu'après une **vérification serveur à serveur** auprès de NotchPay
  (statut payé, même référence, même montant, même devise) ;
- les webhooks sont **authentifiés** (HMAC SHA-256, comparaison à temps constant) et leur contenu est
  revérifié auprès de NotchPay ;
- activation **idempotente** et verrouillée : un paiement ne prolonge l'abonnement qu'une seule fois ;
- facturation et paiements sont **invisibles** pour le compte lecture seule et pour l'IA ;
- inscription : 3 par heure et par adresse IP, plafond quotidien, piège à robots, un essai par e-mail.

En local, `PAIEMENT_SIMULATION=true` dans `.env` permet de tester tout le parcours sans compte
marchand (refusé automatiquement sur Render et dès qu'une vraie clé est configurée).

## Mesurer la fiabilité

Dans l'interface (admin) : onglet **Fiabilité** → « Lancer l'évaluation ». En ligne de commande :

```bash
docker compose exec api python -m app.outils.evaluer
```

Les 50 questions sont dans `voicebank_api/evaluation/questions.json` (ajoute les tiennes).
Une réponse est juste si son résultat correspond à celui de la requête de référence.

## Réentraîner le modèle de fraude

Le script d'origine ne lisait jamais l'heure des transactions. Le nouveau script corrige ça et
enregistre la date, l'AUC et les bornes de normalisation (`meta_fraude.json`) :

```bash
docker compose run --rm -v ./voicebank_ia/modeles_sauvegardes:/app/voicebank_ia/modeles_sauvegardes api python -m app.outils.entrainer_fraude
docker compose up -d --build api
```

## Mettre en ligne (Render) avec des données de démonstration

1. Render → **New → Blueprint** → choisis ce dépôt (`render.yaml`).
2. Renseigne les secrets : `VOICEBANK_USERS`, `ALLOWED_ORIGINS` (URL de l'interface),
   `REACT_APP_API_URL` (URL de l'API), `GEMINI_API_KEY`, `GROQ_API_KEY`.
3. Au premier démarrage, l'API crée le schéma (`INITIALISER_BASE=true`) et remplit la base vide
   avec des **données fictives** (`DONNEES_DEMO=true`) : aucune vraie donnée en ligne.
4. Mets le lien de l'interface sur ton CV / GitHub.

**Limites de l'offre gratuite**
- L'API s'endort après 15 min sans visite : la page de connexion la réveille et affiche
  « Démarrage du serveur… » (jusqu'à une minute).
- La base PostgreSQL gratuite de Render **expire au bout de 30 jours**. Comme elle ne contient que des
  données de démonstration, il suffit de la recréer (Render → voicebank-db → supprimer, puis
  Blueprint → **Manual sync**) : l'API recrée le schéma et les données au démarrage, et le compte
  administrateur de `VOICEBANK_USERS`. Pour une base sans expiration, crée une base gratuite chez
  [Neon](https://neon.tech) et mets son URL dans `DATABASE_URL` (voicebank-api → Environment).
- Si l'adresse de l'API change (domaine personnalisé), mets-la à jour dans `REACT_APP_API_URL`
  et dans la ligne `connect-src` de `render.yaml`.

Générer les mêmes données de démo ailleurs (refuse d'écrire dans une base déjà remplie) :

```bash
ADMIN_DATABASE_URL=postgresql://admin:mdp@hote:5432/voicebank_db python -m app.outils.generer_demo
```

## Développement sans Docker

```bash
# API
cd voicebank_api
python -m venv venv && venv\Scripts\activate      # Windows (source venv/bin/activate sinon)
pip install -r requirements-dev.txt
copy .env.example .env                             # puis remplis-le
uvicorn main:app --reload

# Interface
cd voicebank-ui
npm ci
npm start
```

Sur une base déjà existante (créée avec l'ancienne version), applique la migration de sécurité
(elle crée les comptes `voicebank_app` et `voicebank_reader` et ajoute la colonne manquante) :

```bash
psql "postgresql://ADMIN@localhost:5432/voicebank_db" -v app_pwd=XXX -v reader_pwd=YYY \
     -f voicebank_db/securite/roles.sql
```

## Tests

```bash
cd voicebank_api
TEST_PG_ADMIN_URL=postgresql://postgres:MDP@localhost:5432/postgres pytest
cd ../voicebank-ui && CI=true npm test
```

Les tests créent une base `voicebank_test` jetable (données synthétiques), testent tous les
endpoints, et vérifient les protections : accès sans jeton, rôle insuffisant, jetons falsifiés,
injections SQL (19 attaques), SQL malveillant renvoyé par l'IA, empoisonnement du RAG, upload
audio dangereux, CORS, limitation des tentatives de connexion.

## Sécurité

- Authentification JWT (mots de passe hachés en bcrypt), rôles `analyste` / `admin`.
- Comptes créés par l'administrateur uniquement ; mot de passe provisoire à usage unique (72 h),
  politique de mot de passe, blocage après 5 échecs, révocation immédiate des sessions.
- La table des comptes est invisible pour le compte lecture seule et pour le SQL généré par l'IA.
- Déconnexion automatique après 15 min d'inactivité (avertissement 1 min avant) ; le jeton est
  renouvelé tant que l'utilisateur est actif, donc pas de coupure en pleine analyse.
- Interface sur Render : Content-Security-Policy, HSTS, micro autorisé uniquement pour le site.
- Dependabot propose chaque mois les mises à jour de sécurité des dépendances (testées par la CI).
- 5 tentatives de connexion par minute et par IP ; limites sur les endpoints IA.
- Le SQL dynamique est validé (sqlglot) **et** exécuté avec un compte PostgreSQL en lecture seule.
- L'API se connecte avec un compte sans privilèges d'administration (`voicebank_app`).
- CORS limité à `ALLOWED_ORIGINS`, en-têtes de sécurité, erreurs internes jamais renvoyées au client.
- Uploads audio : extensions autorisées, 10 Mo max, aucun fichier écrit sur disque.
- Ports Docker liés à `127.0.0.1`, conteneur API sans root, secrets uniquement dans `.env`.
- Noms, e-mails, téléphones et numéros de compte masqués pour le rôle analyste.
- Journal d'audit en ajout seul (le compte de l'API ne peut ni le modifier ni l'effacer).
- L'historique navigateur est en `sessionStorage` (effacé à la fermeture et à la déconnexion).

## Structure

```
voicebank_api/      API FastAPI (app/), tests (tests/), evaluation/, Dockerfile
voicebank-ui/       Interface React, Dockerfile + nginx.conf
voicebank_db/       init/ (scripts SQL auto), securite/roles.sql, chargement des CSV
voicebank_ia/       entraînement des modèles + modèles sauvegardés
voicebank_whisper/  transcription vocale locale (secours de Groq)
pipeline_voicebank.py   génération du jeu de données
```
