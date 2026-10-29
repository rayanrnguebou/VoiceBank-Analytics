@echo off
REM Copie TOUTE la base en ligne (Render, qui expire au bout de 30 jours) vers une base Neon gratuite et sans
REM expiration : comptes, organisations, abonnements, paiements, double authentification, journaux, donnees.
REM Rien n est modifie sur Render. Necessite Docker Desktop. Voir README, "Base sans expiration (Neon)".
cd /d "%~dp0.."
set /p SOURCE=1. Colle l External Database URL de Render (voicebank-db ^> Connect) puis Entree : 
set /p CIBLE=2. Colle l URL de la base Neon (Connect, Connection pooling decoche) puis Entree : 
if "%SOURCE%"=="" ( echo Annule. & pause & exit /b 1 )
if "%CIBLE%"=="" ( echo Annule. & pause & exit /b 1 )
set /p OK=Taper OUI pour copier : 
if /i not "%OK%"=="OUI" ( echo Annule. & pause & exit /b 1 )
if not exist "sauvegarde\copies" mkdir "sauvegarde\copies"
docker run --rm -e SOURCE -e CIBLE -e DOSSIER=/copies -e SECURITE=/securite -v "%CD%\voicebank_db\securite:/securite:ro" -v "%CD%\sauvegarde\copies:/copies" -w /copies postgres:18-alpine sh /securite/transferer_base.sh
set SOURCE=
set CIBLE=
pause
