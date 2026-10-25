@echo off
REM Restaure une sauvegarde : sauvegarde\restaurer.bat sauvegardes\voicebank_2026-10-25_0930.dump
REM ATTENTION : remplace le contenu actuel de la base par celui de la sauvegarde.
cd /d "%~dp0.."
if "%~1"=="" (
  echo Usage : sauvegarde\restaurer.bat sauvegardes\voicebank_AAAA-MM-JJ_HHMM.dump
  dir /b /o-d sauvegardes\voicebank_*.dump 2>nul
  exit /b 1
)
if not exist "%~1" ( echo Fichier introuvable : %~1 & exit /b 1 )
set /p OK=La base actuelle sera remplacee par %~1. Taper OUI pour continuer :
if /i not "%OK%"=="OUI" ( echo Annule. & exit /b 1 )
docker compose exec -T postgres sh -c "pg_restore -U \"$POSTGRES_USER\" -d voicebank_db --clean --if-exists --no-owner" < "%~1"
docker compose exec -T postgres sh /voicebank_securite/migrer.sh
docker compose restart api
echo Restauration terminee.
pause
