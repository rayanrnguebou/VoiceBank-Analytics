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
| **Questions de suite** | « et à Douala ? », « seulement BICEC », « en 2025 » reprennent la question précédente. |
| **Pertinence** | Une règle locale ne répond que si elle couvre toute la question ; sinon Gemini, ou réponse marquée « approximative ». |
| **Apprentissage** | Bouton « Réponse incorrecte ? » ; l'admin corrige, teste et enregistre la requête (RAG). |
| **Fiabilité mesurée** | 50 questions de référence, taux de bonnes réponses par catégorie et par source. |
| **Fraude** | Score Isolation Forest + XGBoost, alertes à traiter (fraude confirmée / faux positif). |
| **Crédit** | Probabilité de défaut, facteurs explicatifs (SHAP), crédits en cours les plus à risque. |
| **Données personnelles** | Noms, e-mails, téléphones masqués pour le rôle analyste ; jamais envoyés à Gemini pour les résumés. |
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
