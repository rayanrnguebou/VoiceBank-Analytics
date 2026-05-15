# VoiceBank Analytics - Interface React
# Auteur : Nguebou Temgoua Rayan

## Installation complète

# 1. Creer le projet React
npx create-react-app voicebank-ui
cd voicebank-ui

# 2. Installer les dependances
npm install axios recharts lucide-react
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p

# 3. Remplacer les fichiers
# Copie src/App.js        -> voicebank-ui/src/App.js
# Copie src/index.css     -> voicebank-ui/src/index.css
# Copie tailwind.config.js -> voicebank-ui/tailwind.config.js

# 4. Lancer
npm start
# -> http://localhost:3000

## Prerequis
# - API FastAPI lancee sur http://localhost:8000
# - Docker PostgreSQL demarre
# - Cle Gemini configuree dans .env

## Fonctionnalites
# - Toggle Dark / Light mode
# - Bouton microphone (Whisper via API)
# - Saisie texte avec suggestions rapides
# - KPIs globaux (clients, transactions, fraudes, credits)
# - Panel alertes fraude avec filtres
# - Graphiques (clients par banque, transactions mensuelles)
# - Bouton "Ouvrir Power BI" -> lien externe
# - Indicateur RAG vs Gemini sur chaque reponse

## Personnalisation
# Dans App.js, ligne 13 :
# const POWER_BI_URL = "https://app.powerbi.com/..."
# Remplace par ton vrai lien Power BI publie
