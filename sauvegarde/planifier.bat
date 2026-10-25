@echo off
REM Programme une sauvegarde automatique de la base locale, chaque jour a 20 h.
REM A lancer une seule fois (double-clic). Pour l'annuler : sauvegarde\annuler_planification.bat
REM Docker Desktop doit etre lance a l'heure de la sauvegarde ; sinon elle est notee ECHEC dans
REM sauvegardes\journal.txt et refaite le lendemain.
set SCRIPT=%~dp0sauvegarder.bat
schtasks /Create /F /SC DAILY /ST 20:00 /TN "VoiceBank Analytics - sauvegarde" /TR "\"%SCRIPT%\" auto"
if errorlevel 1 (
  echo Impossible de creer la tache planifiee.
) else (
  echo Sauvegarde automatique programmee chaque jour a 20:00.
  echo Pour changer l'heure : Planificateur de taches Windows ^> "VoiceBank Analytics - sauvegarde".
)
pause
