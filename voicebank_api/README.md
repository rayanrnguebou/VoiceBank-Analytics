# VoiceBank Analytics - API FastAPI
# Auteur : Nguebou Temgoua Rayan

## Installation

pip install fastapi uvicorn sqlalchemy psycopg2-binary pandas
            google-generativeai joblib xgboost python-multipart
            python-dotenv httpx

## Obtenir la cle Gemini GRATUITE

1. Va sur : https://aistudio.google.com/app/apikey
2. Connecte-toi avec ton compte Google
3. Clique "Create API Key"
4. Copie la cle dans le fichier .env : GEMINI_API_KEY=ta_cle_ici

## Structure du projet

VoiceBank Analytics/
├── voicebank_api/
│   ├── main.py        <- API FastAPI
│   └── .env           <- variables d'environnement
├── voicebank_ia/
│   └── modeles_sauvegardes/   <- modeles charges par l'API
├── voicebank_db/
└── output_voicebank/

## Lancement

cd voicebank_api
uvicorn main:app --reload --host 0.0.0.0 --port 8000

## Documentation interactive

http://localhost:8000/docs       <- Swagger UI
http://localhost:8000/redoc      <- ReDoc

## Endpoints disponibles

GET  /                           -> accueil API
GET  /health                     -> sante de l'API
GET  /dashboard                  -> KPIs globaux
GET  /stats/global               -> stats completes
GET  /clients                    -> liste clients (filtres disponibles)
GET  /clients/{id}               -> detail client + transactions + credits
GET  /transactions/recentes      -> dernieres transactions
GET  /alertes/fraude             -> alertes fraude par niveau
GET  /credits/portefeuille       -> portefeuille credit
POST /vocal/question             -> question en langage naturel -> SQL -> resultat
POST /sql/executer               -> executer SQL directement
POST /ia/analyser-transaction    -> analyser une transaction en temps reel

## Exemple - Question vocale

POST http://localhost:8000/vocal/question
{
    "texte": "Montre les 10 clients avec le plus grand solde"
}

Reponse :
{
    "status": "ok",
    "question": "Montre les 10 clients avec le plus grand solde",
    "sql": "SELECT nom, prenom, banque, solde_fcfa FROM voicebank.clients ORDER BY solde_fcfa DESC LIMIT 10",
    "total": 10,
    "data": [...],
    "duree_ms": 342
}
