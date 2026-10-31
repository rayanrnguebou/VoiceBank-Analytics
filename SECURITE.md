# Sécurité de VoiceBank Analytics

## Signaler une faille

Écrivez à **rayannnguebou@gmail.com** (objet : « Sécurité VoiceBank »), en français ou en anglais, avec les étapes
pour reproduire. Réponse sous 72 h, correctif prioritaire, remerciements publics si vous le souhaitez.
Merci de ne pas publier la faille avant sa correction, de ne tester que sur vos propres comptes (l'essai gratuit
suffit) et de ne jamais lire, modifier ou supprimer les données d'autrui.

## Dossier pour un audit de sécurité externe

Ce qui suit sert de point de départ à un auditeur (test d'intrusion, revue de code).

### Périmètre

| Élément | Adresse / dossier |
|---|---|
| Interface (React, site statique) | https://voicebank-ui.onrender.com — `voicebank-ui/` |
| API (FastAPI) | https://voicebank-api.onrender.com — `voicebank_api/` |
| Base de données (PostgreSQL, Neon) | schéma `voicebank_db/init/`, droits `voicebank_db/securite/roles.sql` |
| API publique de score (logiciels bancaires) | `POST /api/v1/operations/score`, clé `vb_…` |
| Connecteur vers les bases des clients | `voicebank_api/app/connecteur/` (PostgreSQL, MySQL, SQL Server, Oracle, fichiers) |

Hors périmètre : attaques par déni de service volumétrique, hameçonnage, accès physique, services des hébergeurs
(Render, Neon, Brevo, Cloudflare).

### Points sensibles à examiner en priorité

1. **Isolation entre organisations** : une organisation ne doit jamais voir les bases, alertes, dossiers de
   recouvrement ni les clés d'API d'une autre (`_PORTEE` dans `connecteur/service.py`).
2. **Questions en langage naturel → SQL** : validation `garde_sql.py` (sqlglot, tables autorisées, lecture seule)
   puis exécution avec un compte PostgreSQL en lecture seule ; injection d'instructions dans les questions.
3. **Connecteur** : accès au réseau interne (SSRF, réaiguillage DNS) via l'adresse d'une base, identifiants chiffrés
   (`CLE_SOURCES`), lecture seule sur la base du client.
4. **Authentification** : jetons JWT (HS256, version de jeton, sessions révocables), double authentification,
   approbation sur téléphone, connexion Google/Microsoft (PKCE, nonce), récupération de compte, protection contre le
   devinage (`protection.py`).
5. **API de score** : clés hachées (SHA-256), restriction par adresse IP, modes observation et test, limites.
6. **Paiement** (NotchPay) : signature HMAC des notifications, montant recalculé côté serveur.
7. **Fichiers** : CSV/Excel (bombe de décompression, injection de formules), audio, taille des requêtes.

### Défenses en place

En-têtes de sécurité (CSP stricte, HSTS, X-Frame-Options), CORS limité, limites par adresse IP et par compte,
journal d'audit en ajout seul, alertes de sécurité par e-mail, masquage des données personnelles selon le rôle,
sauvegardes chiffrées chaque nuit et test de restauration chaque mois.

### Tests automatisés fournis

- `tests_e2e/attaques.py` : plus de 110 attaques rejouées à chaque modification (isolation, rôles, élévation de
  privilèges, jetons falsifiés, SQL, SSRF, comptes, paiement, fichiers, API de score).
- `voicebank_api/tests/` : tests de l'API (dont `test_securite_complements.py`).
- `tests_e2e/test_compatibilite.py` : 13 appareils et navigateurs.

Lancer en local : voir README, section « Tests ».

### Comptes de test

Un environnement de test séparé, avec des données fictives et des comptes dédiés (administrateur de plateforme,
administrateur et analyste de deux organisations, abonné individuel, essai gratuit), est fourni sur demande.
Ne jamais auditer avec des données réelles.
