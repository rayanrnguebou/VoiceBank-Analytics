# VoiceBank Analytics — Interface React

```bash
npm ci
npm start          # http://localhost:3000, API attendue sur REACT_APP_API_URL
CI=true npm test
npm run build
```

Variables (fichier `.env` dans ce dossier ou arguments de build Docker) :

- `REACT_APP_API_URL` : URL de l'API (défaut `http://localhost:8000`)
- `REACT_APP_POWER_BI_URL` : lien du rapport Power BI publié (le bouton est masqué si vide)
