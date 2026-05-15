# VOICEBANK ANALYTICS - Guide de déploiement Render
# Auteur : Nguebou Temgoua Rayan

## Structure finale du projet GitHub

VoiceBank-Analytics/          <- racine du depot GitHub
|-- render.yaml               <- configuration Render (a la racine)
|-- docker-compose.yml        <- pour tester en local
|-- .gitignore
|-- voicebank_api/
|   |-- Dockerfile
|   |-- requirements.txt
|   |-- main.py               <- ton main_v2.py renomme
|   `-- .env.example          <- sans les vraies cles !
|-- voicebank_ui/
|   |-- Dockerfile
|   |-- nginx.conf
|   |-- package.json
|   |-- tailwind.config.js
|   `-- src/
|       |-- App.js
|       `-- index.css
|-- voicebank_db/
|   `-- init/
|       `-- 01_init_voicebank.sql
`-- voicebank_ia/
    `-- modeles_sauvegardes/
        |-- isolation_forest.pkl
        |-- xgb_fraude.json
        |-- xgb_credit.json
        |-- scaler_fraude.pkl
        `-- encoders_fraude.pkl


## ÉTAPES DE DÉPLOIEMENT SUR RENDER

### Étape 1 - Créer le dépôt GitHub

1. Va sur github.com et crée un nouveau dépôt
   Nom : VoiceBank-Analytics
   Visibilité : Public (nécessaire pour Render gratuit)

2. Dans ton terminal :
   git init
   git add .
   git commit -m "VoiceBank Analytics - Premier déploiement"
   git branch -M main
   git remote add origin https://github.com/TON_USERNAME/VoiceBank-Analytics.git
   git push -u origin main


### Étape 2 - Créer la base PostgreSQL sur Render

1. Va sur render.com et connecte-toi avec GitHub
2. Clique "New +" -> "PostgreSQL"
3. Remplis :
   Name     : voicebank-db
   Database : voicebank_db
   User     : voicebank_user
   Plan     : Free
4. Clique "Create Database"
5. Copie la "Internal Database URL" -> tu en auras besoin


### Étape 3 - Déployer l'API FastAPI

1. Clique "New +" -> "Web Service"
2. Connecte ton dépôt GitHub VoiceBank-Analytics
3. Remplis :
   Name         : voicebank-api
   Root Dir     : voicebank_api
   Runtime      : Python 3
   Build Cmd    : pip install -r requirements.txt
   Start Cmd    : uvicorn main:app --host 0.0.0.0 --port $PORT
   Plan         : Free

4. Dans "Environment Variables", ajoute :
   DATABASE_URL  = (colle l'Internal Database URL de l'étape 2)
   GEMINI_API_KEY = (ta clé Gemini)

5. Clique "Create Web Service"
6. Attends le déploiement (5-10 min)
7. Note l'URL de ton API : https://voicebank-api.onrender.com


### Étape 4 - Configurer l'URL de l'API dans React

Avant de déployer l'interface, modifie cette ligne dans voicebank_ui/src/App.js :

const API = "http://localhost:8000";

Remplace par :

const API = process.env.REACT_APP_API_URL || "http://localhost:8000";


### Étape 5 - Déployer l'interface React

1. Clique "New +" -> "Static Site"
2. Connecte ton dépôt GitHub
3. Remplis :
   Name          : voicebank-ui
   Root Dir      : voicebank_ui
   Build Cmd     : npm install && npm run build
   Publish Dir   : build

4. Dans "Environment Variables", ajoute :
   REACT_APP_API_URL = https://voicebank-api.onrender.com

5. Clique "Create Static Site"
6. Attends le déploiement (3-5 min)
7. Ton interface est en ligne : https://voicebank-ui.onrender.com


### Étape 6 - Initialiser la base de données

1. Dans Render, clique sur "voicebank-api"
2. Va dans "Shell" (terminal en ligne)
3. Lance :
   python -c "
   from sqlalchemy import create_engine, text
   import os
   engine = create_engine(os.getenv('DATABASE_URL'))
   with open('init_db.sql') as f:
       sql = f.read()
   with engine.connect() as conn:
       conn.execute(text(sql))
       conn.commit()
   print('Base initialisee !')
   "


## TESTER EN LOCAL AVANT RENDER

docker compose up -d
# -> PostgreSQL  : http://localhost:5432
# -> pgAdmin     : http://localhost:5050
# -> API         : http://localhost:8000/docs
# -> Interface   : http://localhost:3000


## .gitignore recommande

.env
*.pkl
*.json
__pycache__/
node_modules/
build/
.DS_Store
*.pyc
modeles_sauvegardes/
graphiques_ia/
output_voicebank/


## URLS FINALES

API        : https://voicebank-api.onrender.com
Interface  : https://voicebank-ui.onrender.com
Docs API   : https://voicebank-api.onrender.com/docs

IMPORTANT : Sur le plan gratuit Render, les services s'endorment
après 15 minutes d'inactivité. Le premier chargement peut prendre
30-60 secondes. C'est normal !
