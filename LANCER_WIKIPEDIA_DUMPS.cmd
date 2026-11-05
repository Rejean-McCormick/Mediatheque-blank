@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%~dp0tools\wiki\dump_import\Wikipedia_Dumps_UI.pyw"
) else (
  pythonw "%~dp0tools\wiki\dump_import\Wikipedia_Dumps_UI.pyw"
)
if errorlevel 1 (
  echo Impossible de lancer l'interface. Verifiez Python 3.11+ et Tkinter.
  pause
)
endlocal
