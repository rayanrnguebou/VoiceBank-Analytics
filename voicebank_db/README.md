# VoiceBank Analytics — Base de données PostgreSQL via Docker

**Auteur :** Nguebou Temgoua Rayan  
**Projet :** VoiceBank Analytics

---

## Prérequis

- Docker Desktop installé et démarré
- Python 3.9+
- Tes fichiers CSV dans le dossier `output_voicebank/`

---

## Structure des fichiers

```
voicebank_db/
├── docker-compose.yml          ← configuration Docker
├── .env                        ← variables d'environnement
├── charger_csv_postgres.py     ← script de chargement CSV
├── init/
│   └── 01_init_voicebank.sql  ← création automatique des tables
└── pgadmin/
    └── servers.json            ← connexion auto pgAdmin
```

---

## Étape 1 — Démarrer PostgreSQL + pgAdmin

```bash
cd voicebank_db
docker compose up -d
```

Attendre 15 secondes que PostgreSQL soit prêt, puis vérifier :

```bash
docker compose ps
```

Tu dois voir :
```
voicebank_postgres   running   0.0.0.0:5432->5432/tcp
voicebank_pgadmin    running   0.0.0.0:5050->80/tcp
```

---

## Étape 2 — Vérifier que les tables sont créées

```bash
docker exec -it voicebank_postgres psql -U voicebank_user -d voicebank_db -c "\dt voicebank.*"
```

Tu dois voir les 5 tables :
- `clients`
- `transactions`
- `credits`
- `alertes_fraude`
- `logs_vocaux`

---

## Étape 3 — Charger les CSV dans PostgreSQL

```bash
pip install psycopg2-binary pandas sqlalchemy tqdm
python charger_csv_postgres.py
```

Durée estimée : 5 à 15 minutes selon ton PC.

---

## Étape 4 — Accéder à pgAdmin

Ouvre ton navigateur sur : **http://localhost:5050**

```
Email    : rayan@voicebank.cm
Password : voicebank2024
```

Le serveur "VoiceBank Analytics" apparaît déjà dans la liste — connexion automatique !

---

## Étape 5 — Connexion Talend

Dans Talend Open Studio, crée une connexion PostgreSQL :

```
Host     : localhost
Port     : 5432
Database : voicebank_db
Schema   : voicebank
Username : voicebank_user
Password : voicebank2024
```

---

## Étape 6 — Connexion Power BI

Dans Power BI Desktop :
1. Obtenir les données → PostgreSQL
2. Serveur : `localhost:5432`
3. Base : `voicebank_db`
4. Identifiants : `voicebank_user` / `voicebank2024`
5. Importer les vues : `v_clients_par_banque`, `v_transactions_mensuelles`, etc.

---

## Commandes utiles Docker

```bash
# Démarrer
docker compose up -d

# Arrêter (données conservées)
docker compose stop

# Arrêter et supprimer tout
docker compose down -v

# Voir les logs PostgreSQL
docker logs voicebank_postgres

# Ouvrir un terminal PostgreSQL
docker exec -it voicebank_postgres psql -U voicebank_user -d voicebank_db
```

---

## Identifiants de connexion

| Service    | URL                    | Login                     | Mot de passe  |
|------------|------------------------|---------------------------|---------------|
| PostgreSQL | localhost:5432         | voicebank_user            | voicebank2024 |
| pgAdmin    | http://localhost:5050  | rayan@voicebank.cm        | voicebank2024 |
