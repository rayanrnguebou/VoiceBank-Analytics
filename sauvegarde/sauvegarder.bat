@echo off
REM Sauvegarde complète de la base VoiceBank (Docker) dans le dossier sauvegardes\
REM Lancement : double-clic, ou depuis le dossier du projet : sauvegarde\sauvegarder.bat
REM « sauvegarder.bat auto » : sans pause finale (utilisé par la tâche planifiée).
cd /d "%~dp0.."
if not exist sauvegardes mkdir sauvegardes
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HHmm"') do set HORODATAGE=%%i
set FICHIER=sauvegardes\voicebank_%HORODATAGE%.dump
docker compose exec -T postgres sh -c "pg_dump -U \"$POSTGRES_USER\" -d voicebank_db -Fc" > "%FICHIER%"
if errorlevel 1 (
  echo ECHEC de la sauvegarde. Docker est-il lance ? ^(docker compose up -d^)
  echo %date% %time% ECHEC>> sauvegardes\journal.txt
  del "%FICHIER%" 2>nul
) else (
  echo Sauvegarde terminee : %FICHIER%
  echo %date% %time% OK %FICHIER%>> sauvegardes\journal.txt
  REM Ne garde que les 10 sauvegardes les plus recentes
  for /f "skip=10 delims=" %%f in ('dir /b /o-d sauvegardes\voicebank_*.dump') do del "sauvegardes\%%f"
)
if /i not "%~1"=="auto" pause
