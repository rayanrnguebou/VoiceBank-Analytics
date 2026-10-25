@echo off
REM Met en ligne les donnees de ta base locale (Docker) sur la base Render.
REM Copie : clients, credits, transactions, alertes, corrections apprises.
REM Ne copie JAMAIS : comptes, mots de passe, paiements, journal d'audit.
REM Ou trouver l'URL : Render > voicebank-db > Connect > External Database URL.
cd /d "%~dp0.."
echo Cette operation REMPLACE les donnees en ligne par celles de ton PC.
echo Une sauvegarde locale est faite avant, par securite.
set /p CIBLE=Colle l'External Database URL de Render puis Entree : 
if "%CIBLE%"=="" ( echo Annule. & pause & exit /b 1 )
set /p OK=Taper OUI pour continuer : 
if /i not "%OK%"=="OUI" ( echo Annule. & pause & exit /b 1 )
call "%~dp0sauvegarder.bat" auto
docker compose exec -T postgres sh /voicebank_securite/migrer.sh
docker compose exec -T -e CIBLE="%CIBLE%" postgres sh /voicebank_securite/publier.sh
set CIBLE=
pause
