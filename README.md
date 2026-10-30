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
| **Connecteur « Mes données »** | Branche une base PostgreSQL, MySQL/MariaDB, SQL Server, Oracle ou des fichiers Excel/CSV : analyse de la structure et du sens métier, diagnostic de qualité, puis questions en français dans le dialecte de la base. |
| **Monnaie d'affichage** | Sélecteur en haut de l'écran (FCFA CEMAC / UEMOA, euro, dollar, livre, dollar canadien, franc suisse, yuan, naira) : réponses, résumé parlé, graphiques, indicateurs, alertes, crédit et tarifs suivent la monnaie choisie. FCFA ↔ euro à la parité officielle (655,957), autres taux BCE mis à jour toutes les 12 h. Les abonnements restent débités en FCFA. Pour une base connectée, la monnaie de ses montants est détectée (colonne « currency ») ou choisie. |
| **Français / English** | Sélecteur de langue (page d'accueil et barre latérale ; lien direct `?lang=en`). Interface, messages d'erreur, analyses, fiches des modèles, e-mails (dans la langue de chaque destinataire) et rapports PDF en anglais ; voix et dictée en anglais. Français par défaut. |
| **Comptes** | Créés par l'administrateur (pas d'inscription libre), mot de passe provisoire à changer à la 1re connexion, **double authentification** (obligatoire pour les administrateurs), protection contre le devinage de mots de passe sans blocage possible par un tiers, désactivation sans suppression. |
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

**Protections** : changer de mot de passe, de rôle ou désactiver un compte **déconnecte immédiatement** ses
sessions ; aucun compte n'est supprimé (l'audit reste lisible) ; on ne peut ni se désactiver soi-même ni retirer le
dernier administrateur. Chacun gère la sécurité de son compte (icône 🔑 en bas de la barre latérale) : mot de passe,
double authentification, e-mail de récupération.

#### Double authentification (code à 6 chiffres)

En plus du mot de passe, un code à 6 chiffres affiché par une application du téléphone (Google Authenticator,
Microsoft Authenticator, Authy…). **Obligatoire pour les administrateurs** (plateforme et organisations) : à leur
prochaine connexion, ils scannent un QR code avant de pouvoir continuer ; facultative pour les autres
(`DOUBLE_AUTH_ADMINS=facultative` la rend facultative pour tous). Aussi demandée après une connexion Google / Microsoft.
- 10 **codes de secours** à usage unique, affichés une fois (téléphone perdu) ; régénérables.
- Téléphone et codes perdus : un autre administrateur clique **Réinit. 2FA** (Comptes, ou Mon organisation → Membres).
- Un code déjà utilisé est refusé ; 5 codes faux bloquent l'adresse de l'essayeur.

#### Mots de passe faux : l'attaquant se bloque lui-même, pas sa victime

Avant, 5 essais faux bloquaient le compte 15 minutes : n'importe qui pouvait empêcher un administrateur de travailler.
- Les échecs sont comptés **par adresse** : au 5e, seule l'adresse de l'essayeur est bloquée pour ce compte
  (1 min, puis 5, 15, 60 min). Le titulaire, depuis la sienne, se connecte normalement.
- Attaque depuis de nombreuses adresses (20 échecs en une heure) : le compte passe 24 h en **mode protégé**. Les
  adresses d'où le titulaire s'est déjà connecté restent acceptées ; depuis un nouvel appareil, le mot de passe ne
  suffit plus.
- **Déblocage que le pirate ne peut pas déclencher** : un lien à usage unique part à l'adresse e-mail *du compte* ;
  il n'autorise que l'appareil qui l'ouvre. Se connecter avec Google / Microsoft, réinitialiser son mot de passe par
  e-mail, ou un administrateur (**Débloquer** dans Comptes) lèvent aussi la protection.

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

### Base sans expiration (Neon)

La base gratuite de Render **expire 30 jours après sa création** (puis est supprimée). Maintenant qu'elle contient de
vrais comptes, organisations et paiements, elle doit être chez [Neon](https://neon.tech) : PostgreSQL gratuit
**sans date d'expiration** (1 Go, mise en veille après 5 min sans requête, réveil en moins d'une seconde).

1. **neon.tech → Sign up** (avec Google ou GitHub) → **Create project** : nom `voicebank`, PostgreSQL 17 ou 18,
   région **la même que l'API sur Render** (Render → voicebank-api → *Settings → Region* : *Oregon* → *AWS US West 2
   (Oregon)* ; *Frankfurt* → *AWS Europe Central 1 (Frankfurt)*). Une région éloignée ralentirait chaque page.
2. Neon → **Connect** : **décoche « Connection pooling »**, copie l'adresse (`postgresql://…neon.tech/neondb?sslmode=require…`).
3. Neon → *Branches → main → Compute → Edit* : taille **0,25 à 0,5 CU** (suffisant ; le quota gratuit de 100 « CU-heures » par
   mois fait alors 200 à 400 heures d'activité, la base dormant le reste du temps).
4. Sur ton PC (Docker Desktop lancé) : `sauvegarde\passer_a_neon.bat` (ou `sh sauvegarde/passer_a_neon.sh`).
   Colle l'*External Database URL* de Render puis l'adresse Neon. Le script garde une copie dans
   `sauvegarde/copies/`, copie **tout** (comptes, organisations, paiements, double authentification, journaux,
   données), crée le compte en lecture seule, puis compare les deux bases table par table. **Rien n'est modifié sur
   Render.**
5. Render → voicebank-api → **Environment** : `DATABASE_URL` = l'adresse Neon, `READONLY_DATABASE_URL` = l'adresse
   affichée par le script → **Save, rebuild and deploy**. Vérifie : `https://voicebank-api.onrender.com/health`
   doit afficher `"database": "connectee"`, puis connecte-toi.
6. GitHub → *Settings → Secrets → Actions* : `BASE_EN_LIGNE_URL` = l'adresse Neon (sauvegarde de la nuit), puis
   *Actions → Sauvegarde en ligne → Run workflow*.
7. Quelques jours plus tard, tout fonctionnant : Render → voicebank-db → *Settings* → **Delete Database**.

Les sondes de Render (`/health/vivant`) ne touchent pas la base, et `/health/pret` (UptimeRobot) ne la réinterroge
pas si elle a répondu dans les 20 dernières minutes : la base peut dormir quand personne ne s'en sert.

### En ligne : sauvegarde de la nuit

La base en ligne n'a pas de sauvegarde longue : un workflow GitHub en fait une **chaque nuit**,
**chiffrée** (AES-256), conservée 30 jours dans l'onglet *Actions* du dépôt.

1. GitHub → dépôt → **Settings → Secrets and variables → Actions → New repository secret** :
   - `BASE_EN_LIGNE_URL` : l'adresse de la base Neon (ou, avant le passage à Neon, Render → voicebank-db →
     **Connect** → *External Database URL*) ;
   - `SAUVEGARDE_MOT_DE_PASSE` : une longue phrase secrète, notée en lieu sûr (sans elle, les
     sauvegardes sont illisibles).
2. Onglet **Actions → Sauvegarde en ligne → Run workflow** pour tester tout de suite.
3. **E-mail si la sauvegarde échoue** : ajoute aussi `BREVO_API_KEY` (la même que sur Render), `EMAIL_EXPEDITEUR`
   (adresse validée chez Brevo) et `ALERTE_EMAIL` (destinataire(s), séparés par des virgules). Chaque sauvegarde est
   aussi **relue** (déchiffrement et lecture du contenu) : une sauvegarde illisible compte comme un échec.

Restaurer une sauvegarde en ligne (Git Bash ou macOS / Linux) :

```bash
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -in voicebank_en_ligne_….dump.enc -out en_ligne.dump
docker run --rm -i -e URL="<External Database URL>" postgres:18-alpine \
  sh -c 'pg_restore --clean --if-exists --no-owner -d "$URL"' < en_ligne.dump
```

### Mettre en ligne les données de ton PC

Pour que le site public montre les mêmes données que ta base locale :
`sauvegarde\publier_en_ligne.bat` (ou `sh sauvegarde/publier_en_ligne.sh`), puis colle l'*External
Database URL* de Render (ou l'adresse Neon après le passage à Neon). Le script sauvegarde d'abord ta base locale, puis remplace en ligne les
clients, crédits, transactions, alertes et corrections apprises. **Les comptes, mots de passe,
paiements et journaux d'audit ne sont jamais copiés.** À relancer quand tes données changent.

## Langues (français / anglais)

- **Interface** : chaque texte est écrit en français dans le code, entouré de `tx("…")` ; la traduction anglaise est
  dans `voicebank-ui/src/traductions/en.json` (texte français → texte anglais, variables `{nom}`). Un texte absent
  du fichier reste en français.
- **API** : l'interface envoie `Accept-Language` ; les réponses JSON, erreurs, e-mails et rapports PDF sont traduits
  par `app/i18n.py` d'après `voicebank_api/app/traductions/en.json` (phrases exactes ou gabarits avec `{variable}`).
  Les valeurs codées (niveaux « Critique », statuts…) ne sont jamais traduites dans les réponses : l'interface filtre
  dessus et les affiche traduites.
- **Ajouter un texte** : écris-le en français avec `tx(...)` (interface) ou normalement (API), puis ajoute sa
  traduction dans le fichier `en.json` correspondant. Le test `test_version_anglaise.py` vérifie la cohérence des
  variables.
- La langue de chaque compte est mémorisée : les e-mails automatiques (alertes, résumé, rapports) partent dans la
  langue utilisée en dernier dans l'interface.

## Surveillance : être prévenu avant les utilisateurs

| Quoi | Outil (gratuit) | Mise en place |
|---|---|---|
| Erreurs de l'API et de l'interface | [Sentry](https://sentry.io) | Crée 2 projets (*Python / FastAPI* et *Browser JavaScript*). Copie leur **DSN** dans Render : `SENTRY_DSN` (API) et `REACT_APP_SENTRY_DSN` (interface). Sentry envoie un e-mail à chaque nouvelle erreur. Ni mots de passe, ni données des bases, ni adresses IP ne sont transmis. |
| Site hors ligne | [UptimeRobot](https://uptimerobot.com) | *New monitor* → HTTP(s), toutes les 5 min : `https://voicebank-api.onrender.com/health/pret` (répond 503 si la base est inaccessible) et `https://voicebank-ui.onrender.com`. Ajoute ton e-mail (et l'application mobile) comme contact d'alerte. Effet bonus : l'API reste éveillée. |
| Sauvegarde de la nuit | GitHub Actions + Brevo | Voir « Sauvegarder la base → En ligne » (e-mail en cas d'échec). |
| Tâches automatiques | GitHub Actions | GitHub prévient par e-mail quand le workflow « Tâches automatiques » échoue (réglage par défaut des notifications). |

## Connecteur : brancher les données d'une organisation

Menu **Mes données → Connecter une source** (abonnés et administrateur ; pendant l'essai, une source de
démonstration est explorable).

| Source | Ce qu'il faut |
|---|---|
| PostgreSQL, MySQL / MariaDB, SQL Server | adresse, port, base, **compte en lecture seule** (le formulaire donne le SQL pour le créer), serveur joignable depuis Internet |
| Oracle (12c et plus) | adresse, port (1521, ou 2484 en TCPS chiffré), **nom du service** (ex. `ORCLPDB1`), compte en lecture seule et **schéma** propriétaire des tables. Aucun client Oracle à installer. |
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

### Fraude et crédit sur la base de l'organisation

Quand une source est choisie, les pages **Risques** n'utilisent plus la banque de démonstration : les modèles
sont appris sur la base elle-même (résultat gardé 10 minutes, échantillon de 20 000 lignes).

- **Alertes de fraude** : les opérations récentes sont comparées aux habitudes de la base (montant par type
  d'opération, catégories rares, heure si elle existe, même dans une colonne séparée). Isolation Forest + rangs
  explicites, calibrés : environ 2 % des opérations ressortent comme très atypiques. Chaque alerte donne ses
  raisons (« 3 fois le montant habituel pour « virement » »), un niveau et la conduite à tenir ; filtres, export CSV.
  Si la base contient un indicateur de fraude, la page montre la part des fraudes connues repérées (contre 5 % au hasard).
- **Analyse de transaction** : le formulaire reprend les catégories réelles de la base ; le résultat explique le score.
- **Score de crédit** : si une table de crédits a un statut (« En défaut », « En retard »…), la page donne le taux
  de défaut par segment et classe les crédits en cours (régression logistique ; fiabilité mesurée en validation
  croisée, probabilités calibrées sur le taux réel du portefeuille). Si la fiabilité est faible, la page le dit.

**Suivi des alertes** : sur la base d'une organisation, chaque opération très atypique (niveau Élevé ou Critique,
environ 2 % des opérations) devient une alerte à traiter : personne assignée, commentaires, verdict
(« fraude confirmée », « fausse alerte » — expliqué en une phrase, obligatoire) ou « résolue », historique complet
(en ajout seul : il ne peut pas être modifié). Une fausse alerte ne revient plus ; la précision mesurée sur les
verdicts s'affiche dans la fiche du modèle et règle les e-mails immédiats (seulement les plus graves si le modèle se
trompe souvent, aussi le risque élevé s'il est fiable).

**Surveillance automatique** (chaque heure) : nouvelles alertes enregistrées, e-mail immédiat pour les plus graves,
résumé du matin à 7 h (heure de Douala), rapport PDF le lundi (hebdomadaire) et le 1er du mois (mensuel),
**relecture de la structure** des bases le dimanche (nouvelles tables et colonnes prises en compte ; e-mail si une
table ou une colonne a disparu ; une base injoignable garde son ancien profil et reste surveillée). Chacun
choisit ce qu'il reçoit (menu **Notifications**). Pour l'activer en ligne : Render crée `TACHES_CLE` ; recopie sa
valeur dans les secrets GitHub `TACHES_CLE`, avec `API_URL` (adresse de l'API) — le workflow « Tâches automatiques »
l'appelle chaque heure et réveille l'API. Sans ces secrets, l'API exécute les tâches seule quand elle est éveillée.

**Rapports PDF** (bouton sur la page des alertes) : synthèse de la période, points d'attention rédigés
automatiquement, alertes ouvertes les plus critiques, portefeuille de crédits, modèles utilisés, méthodologie ;
aucune donnée personnelle.

**Fiche des modèles** (menu Risques) : pour chaque modèle d'IA, les données utilisées, la méthode, les seuils, la
fiabilité mesurée, la précision sur vos verdicts, la **dérive** (indice PSI : les opérations récentes ressemblent-elles
à celles de l'apprentissage ?) et les limites — ce que demandent les régulateurs pour valider un modèle.

**Base par défaut de l'organisation** : l'administrateur clique « Définir par défaut » sur une source (Mes données) ;
chaque membre arrive alors directement dessus (il peut toujours revenir à la démonstration). Un guide
« Bien démarrer » accompagne l'administrateur d'une nouvelle organisation (brancher les données, base par défaut,
inviter l'équipe, première question).

### Villes et banques de tous les pays (Afrique, Europe…)

Les champs Pays, Ville et Banque se remplissent en tapant quelques lettres (sans accents ni majuscules) ; le
sigle ou le nom d'origine marche aussi (« bicec », « london » → Londres). Une valeur absente reste acceptée.

| Données | Contenu | Source |
|---|---|---|
| Villes | ~118 000 localités de 1 000 habitants ou plus, 196 pays (Afrique ~4 800, Europe ~63 000), noms français des grandes villes | [GeoNames](https://www.geonames.org) (CC BY 4.0), paquet `all-the-cities` |
| Banques d'Afrique | ~980 banques en activité des 54 pays, banques centrales (BEAC, BCEAO…), principales microfinances du Cameroun | pages « List of banks in … » de Wikipédia, vérifiées pays par pays : `voicebank-ui/outils/banques_afrique.txt` |
| Banques d'Europe et du reste du monde | ~12 000 établissements | registre SWIFT/BIC public (`PeterNotenboom/SwiftCodes`, MIT) |

Fichiers : `voicebank-ui/public/referentiel/{villes,banques}/<ISO>.json`, chargés à la demande (un pays à la fois).
Pour les régénérer (ex. après avoir ajouté une banque dans `banques_afrique.txt`), voir l'en-tête de
`voicebank-ui/outils/generer_referentiel.mjs`.

Dans les formulaires de démonstration (Analyse de transaction, Score de crédit), choisir un autre pays propose
ses banques et ses villes et passe l'opération en « internationale ». Les banques et villes apprises par le modèle
sont signalées ; pour les autres, le modèle estime leur effet par la moyenne des valeurs qu'il connaît et le dit.

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
- Il **invite** ses collègues (nom, e-mail, rôle). Chacun reçoit un
  **e-mail d'invitation** avec un lien d'activation (72 h, usage unique) pour choisir son mot de passe.
  Sans service d'e-mail, un mot de passe provisoire s'affiche une fois, à transmettre.
- **Comptes inclus** (administrateur compris) : Jour et Semaine 3, Mois 10, Année 25 (`COMPTES_JOUR`,
  `COMPTES_SEMAINE`, `COMPTES_MOIS`, `COMPTES_ANNEE`). Un **particulier** a un seul compte.
- Tous les membres **partagent** l'abonnement : à son échéance, toute l'organisation est bloquée jusqu'au
  renouvellement par un administrateur. Les analystes ne voient ni l'abonnement ni les paiements.
- **Rôles** :

  | Rôle | Peut |
  |---|---|
  | Administrateur | tout : membres, abonnement, bases, alertes, journal |
  | Analyste | interroger les bases, traiter les alertes (assigner, commenter, verdict) |
  | Lecteur | consulter (questions, tableaux, alertes) sans rien traiter |
  | Auditeur (contrôle interne) | consulter tout, lire le **journal** de l'organisation (alertes traitées, connexions, changements de droits), sans rien modifier |

- Les **bases connectées** sont partagées dans l'organisation ; l'administrateur peut **limiter un membre à
  certaines bases** (colonne « Bases » de la liste des membres). Une organisation ne voit jamais les membres ni
  les données d'une autre.
- **Connexion avec Google ou Microsoft** (comptes d'entreprise, facultatif) : voir ci-dessous.
- Les membres ne voient **pas** l'administration de la plateforme (comptes, audit, apprentissage…), réservée
  au super-administrateur ; seuls les visiteurs en essai la découvrent, anonymisée et en lecture seule.

#### Connexion avec un compte Google Workspace ou Microsoft 365

Les membres déjà invités peuvent se connecter avec le compte de leur entreprise (aucun compte n'est créé par ce
biais : l'adresse e-mail doit être celle d'un compte VoiceBank actif). Boutons affichés seulement si configurés :

- **Google** : [console.cloud.google.com](https://console.cloud.google.com/apis/credentials) → *Créer des
  identifiants* → *ID client OAuth* → *Application Web*. URI de redirection autorisée :
  `https://voicebank-ui.onrender.com/connexion-sso`. Renseigne `GOOGLE_CLIENT_ID` et `GOOGLE_CLIENT_SECRET` (API).
- **Microsoft** : [portail Entra ID](https://entra.microsoft.com) → *Inscriptions d'applications* → *Nouvelle
  inscription* (comptes de n'importe quel annuaire d'organisation), plateforme **Web**, URI de redirection
  `https://voicebank-ui.onrender.com/connexion-sso` ; puis *Certificats et secrets* → nouveau secret.
  Renseigne `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET` et, pour n'accepter qu'un seul annuaire,
  `MICROSOFT_TENANT` (son identifiant ; par défaut `organizations`).

Sécurité : code d'autorisation avec PKCE, état signé valable 10 minutes et à usage unique, jeton d'identité vérifié
(signature, audience, émetteur, expiration, nonce, adresse vérifiée chez Google).

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

Le modèle livré lit l'heure des transactions (XGBoost à contraintes monotones : un montant plus élevé, la nuit
ou l'international ne peuvent jamais « réduire » le risque) et a été réentraîné sur 60 000 transactions de
démonstration (AUC 0,72, affichée comme « fiabilité correcte »). Pour le réentraîner, le script
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
- La base PostgreSQL gratuite de Render **expire au bout de 30 jours** : `render.yaml` ne la crée plus, la base est
  chez Neon (gratuite, sans expiration) : voir « Base sans expiration (Neon) ». Pour un nouveau déploiement, crée la
  base Neon d'abord et mets son adresse dans `DATABASE_URL` : l'API crée le schéma et les données de démonstration au
  premier démarrage.
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

# Interface (Vite : http://localhost:3000)
cd voicebank-ui
npm ci
npm start            # développement ; npm run build pour la version en ligne
npm test             # tests (Vitest) ; npm run lint pour le contrôle du code
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
  politique de mot de passe, double authentification (TOTP) des administrateurs, échecs bloqués par adresse
  (jamais le compte), mode protégé avec déblocage par lien e-mail, révocation immédiate des sessions.
- La table des comptes est invisible pour le compte lecture seule et pour le SQL généré par l'IA.
- Déconnexion automatique après 15 min d'inactivité (avertissement 1 min avant) ; le jeton est
  renouvelé tant que l'utilisateur est actif, donc pas de coupure en pleine analyse.
- Interface sur Render : Content-Security-Policy, HSTS, micro autorisé uniquement pour le site.
- Dependabot propose chaque mois les mises à jour de sécurité des dépendances (testées par la CI) ;
  l'interface est construite avec Vite (0 vulnérabilité connue à l'`npm audit`).
- 5 tentatives de connexion par minute et par IP ; limites sur les endpoints IA.
- Le SQL dynamique est validé (sqlglot) **et** exécuté avec un compte PostgreSQL en lecture seule.
- L'API se connecte avec un compte sans privilèges d'administration (`voicebank_app`).
- CORS limité à `ALLOWED_ORIGINS`, en-têtes de sécurité, erreurs internes jamais renvoyées au client.
- Uploads audio : extensions autorisées, 10 Mo max, aucun fichier écrit sur disque.
- Ports Docker liés à `127.0.0.1`, conteneur API sans root, secrets uniquement dans `.env`.
- Noms, e-mails, téléphones et numéros de compte masqués pour le rôle analyste.
- Journal d'audit en ajout seul (le compte de l'API ne peut ni le modifier ni l'effacer).
- L'historique navigateur est en `sessionStorage` (effacé à la fermeture et à la déconnexion).
- Session de 12 h au plus, renouvellements compris (`SESSION_MAX_HEURES`) : un jeton volé ne se prolonge pas.
- Exports CSV protégés contre l'injection de formules ; fichiers Excel piégés (bombe de décompression) refusés.
- **Anti-robot** (facultatif, gratuit) sur l'inscription à l'essai et le mot de passe oublié : crée un widget sur
  [Cloudflare Turnstile](https://dash.cloudflare.com/?to=/:account/turnstile) (domaine `voicebank-ui.onrender.com`),
  puis renseigne `TURNSTILE_SECRET` (API) et `REACT_APP_TURNSTILE_SITE_KEY` (interface) sur Render. Sans ces clés,
  la vérification est simplement désactivée.
- **Connexion vérifiée aux bases des organisations** : l'option SSL « Vérifié » contrôle le certificat du serveur
  (autorité reconnue, nom du serveur) en plus du chiffrement ; à préférer dès que la base a un certificat valide.
- **Rotation de la clé des identifiants** (`CLE_SOURCES`) : mets la nouvelle clé dans `CLE_SOURCES` et l'ancienne
  dans `CLE_SOURCES_ANCIENNES`, redémarre, lance `python -m app.outils.rechiffrer_sources`, puis vide
  `CLE_SOURCES_ANCIENNES`. Aucune coupure : les deux clés fonctionnent pendant l'opération.

## Structure

```
voicebank_api/      API FastAPI, tests (tests/), evaluation/, Dockerfile
  app/main.py         assemblage : sécurité (en-têtes, CORS, maintenance), chargement des modèles
  app/api/            un routeur par domaine : auth, abonnement, demo, assistant, admin, organisation, sources…
  app/connecteur/     bases et fichiers des organisations (analyse, garde SQL, risques)
voicebank-ui/       Interface React (Vite), Dockerfile + nginx.conf ; outils/ : génération des villes et banques
voicebank_db/       init/ (scripts SQL auto), securite/roles.sql, chargement des CSV
voicebank_ia/       entraînement des modèles + modèles sauvegardés
voicebank_whisper/  transcription vocale locale (secours de Groq)
pipeline_voicebank.py   génération du jeu de données
```
