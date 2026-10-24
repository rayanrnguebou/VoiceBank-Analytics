# VoiceBank Analytics

Assistant bancaire vocal : on pose une question en français (au micro ou au clavier), l'API la
transforme en requête SQL, l'exécute sur la base PostgreSQL et l'interface affiche le résultat
sous forme de graphique, avec export PDF. Un modèle IA (Isolation Forest + XGBoost) note le
risque de fraude d'une transaction.

**Auteur : Nguebou Temgoua Rayan**

| Couche | Technologies |
|---|---|
| Interface | React 19, Tailwind, Recharts, jsPDF |
| API | FastAPI, SQLAlchemy, sqlglot (validation SQL), JWT |
| IA | Gemini (texte → SQL), Groq Whisper (voix → texte), scikit-learn, XGBoost |
| Données | PostgreSQL 16 (pg_trgm pour le RAG), Power BI |

## Fonctionnement

```
Voix ──Groq Whisper──▶ texte ─┐
Texte ────────────────────────┤
                              ▼
          1. correction RAG quasi identique (validée par un admin)
          2. règles locales (questions fréquentes, sans IA)
          3. correction RAG proche
          4. Gemini
                              ▼
          garde SQL : 1 seul SELECT, tables voicebank uniquement, fonctions système interdites
                              ▼
          exécution par un compte LECTURE SEULE, transaction READ ONLY, timeout 5 s, 1000 lignes max
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

### Créer les comptes utilisateurs

Les comptes sont définis dans `VOICEBANK_USERS` sous la forme `nom:role:hash_bcrypt`, séparés
par des virgules. `role` vaut `analyste` (consultation) ou `admin` (consultation + SQL manuel +
corrections RAG).

```bash
cd voicebank_api
pip install bcrypt
python -m app.outils.creer_hash        # demande le mot de passe, affiche le hash
```

Dans `.env`, mets la valeur entre **apostrophes simples** (le hash contient des `$`) :
`VOICEBANK_USERS='rayan:admin:$2b$12$...,analyste1:analyste:$2b$12$...'`

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
**Ne lance jamais `docker compose down -v`** : `-v` supprime le volume, donc les données.

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
TEST_PG_ADMIN_URL=postgresql://postgres:MDP@localhost:5432/postgres pytest     # 109 tests
cd ../voicebank-ui && CI=true npm test
```

Les tests créent une base `voicebank_test` jetable (données synthétiques), testent tous les
endpoints, et vérifient les protections : accès sans jeton, rôle insuffisant, jetons falsifiés,
injections SQL (19 attaques), SQL malveillant renvoyé par l'IA, empoisonnement du RAG, upload
audio dangereux, CORS, limitation des tentatives de connexion.

## Sécurité

- Authentification JWT (mots de passe hachés en bcrypt), rôles `analyste` / `admin`.
- 5 tentatives de connexion par minute et par IP ; limites sur les endpoints IA.
- Le SQL dynamique est validé (sqlglot) **et** exécuté avec un compte PostgreSQL en lecture seule.
- L'API se connecte avec un compte sans privilèges d'administration (`voicebank_app`).
- CORS limité à `ALLOWED_ORIGINS`, en-têtes de sécurité, erreurs internes jamais renvoyées au client.
- Uploads audio : extensions autorisées, 10 Mo max, aucun fichier écrit sur disque.
- Ports Docker liés à `127.0.0.1`, conteneur API sans root, secrets uniquement dans `.env`.
- L'historique navigateur est en `sessionStorage` (effacé à la fermeture et à la déconnexion).

## Déploiement Render

`render.yaml` déclare la base, l'API (Docker) et l'interface (site statique).

1. Render → New → Blueprint → choisis ce dépôt.
2. Renseigne les variables `sync: false` : `VOICEBANK_USERS`, `ALLOWED_ORIGINS` (URL de
   l'interface), `REACT_APP_API_URL` (URL de l'API), `GEMINI_API_KEY`, `GROQ_API_KEY`.
3. Initialise la base avec l'URL externe fournie par Render :
   `psql URL -f voicebank_db/init/01_init_voicebank.sql -f voicebank_db/init/02_corrections_rag.sql`
4. Si Render autorise la création de rôles, lance aussi `securite/roles.sql` et renseigne
   `READONLY_DATABASE_URL` avec le compte `voicebank_reader`. Sinon, laisse-la vide : le SQL
   sera exécuté en transaction READ ONLY avec le compte principal (qui n'est pas superutilisateur
   sur Render), en plus de la garde SQL.

## Structure

```
voicebank_api/      API FastAPI (app/), tests (tests/), Dockerfile
voicebank-ui/       Interface React, Dockerfile + nginx.conf
voicebank_db/       init/ (scripts SQL auto), securite/roles.sql, chargement des CSV
voicebank_ia/       entraînement des modèles + modèles sauvegardés
voicebank_whisper/  transcription vocale locale (secours de Groq)
pipeline_voicebank.py   génération du jeu de données
```
