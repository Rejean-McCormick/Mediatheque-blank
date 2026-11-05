@echo off
setlocal
cd /d "%~dp0"
where pyw >nul 2>nul
if %errorlevel%==0 (
  start "" pyw -3 "%~dp0tools\wiki\WikipediaReferences_UI.pyw"
) else (
  start "" pythonw "%~dp0tools\wiki\WikipediaReferences_UI.pyw"
)
endlocal
