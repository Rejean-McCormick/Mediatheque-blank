@echo off
setlocal EnableExtensions DisableDelayedExpansion

REM GitSink - deux modes : manuel (invite + attente) / Runner (sans interaction).
REM ATTENTION : synchronise TOUS les changements de ce depot.
REM Ne pas substituer aux versions qui ont des protections specifiques.

set "GITSINK_MANUAL=0"
set "GITSINK_PUSHD=0"
set "GITSINK_RC=0"
set "GITSINK_MESSAGE_FILE="
set "commit_message=Automated-update"

REM Avec un argument (Runner V8.2), aucune invite ni attente.
if "%~1"=="" (
    set "GITSINK_MANUAL=1"
) else (
    set "commit_message=%~1"
)

pushd "%~dp0" >nul 2>&1
if errorlevel 1 (
    >&2 echo ERROR [GitSink]: Cannot enter the script directory.
    set "GITSINK_RC=10"
    goto :finish
)
set "GITSINK_PUSHD=1"

REM Le marqueur .git peut etre un dossier ou un fichier (worktree Git).
if not exist ".git" (
    >&2 echo ERROR [GitSink]: No .git marker next to GitSink.bat.
    set "GITSINK_RC=11"
    goto :finish
)

where git >nul 2>&1
if errorlevel 1 (
    >&2 echo ERROR [GitSink]: git.exe not found in PATH.
    set "GITSINK_RC=12"
    goto :finish
)

echo [GitSink] Repository: %CD%

if "%GITSINK_MANUAL%"=="1" (
    REM Lire le message sans "set /p", afin de rester compatible avec le controle V8.2.
    REM Le fichier temporaire preserve les caracteres speciaux du message.
    set "GITSINK_MESSAGE_FILE=%TEMP%\GitSink_message_%RANDOM%_%RANDOM%.txt"
    call :read_message
    if errorlevel 1 (
        >&2 echo ERROR [GitSink]: Unable to read commit message.
        set "GITSINK_RC=13"
        goto :finish
    )
) else (
    echo [GitSink] Commit message supplied by Runner.
)

echo [GitSink] git add --all
git -c core.longpaths=true add --all
if errorlevel 1 (
    >&2 echo ERROR [GitSink]: git add failed. No commit or push attempted.
    set "GITSINK_RC=20"
    goto :finish
)

REM git diff --quiet: 0=pas de modifications, 1=modifications, 2+=erreur.
git diff --cached --quiet
if errorlevel 2 (
    >&2 echo ERROR [GitSink]: Could not inspect staged changes. No push attempted.
    set "GITSINK_RC=21"
    goto :finish
)
if errorlevel 1 (
    echo [GitSink] git commit
    if "%GITSINK_MANUAL%"=="1" (
        git commit -F "%GITSINK_MESSAGE_FILE%"
    ) else (
        git commit -m "%commit_message%"
    )
    if errorlevel 1 (
        >&2 echo ERROR [GitSink]: git commit failed. No push attempted.
        set "GITSINK_RC=22"
        goto :finish
    )
) else (
    echo [GitSink] No staged changes to commit.
)

echo [GitSink] git push
git push
if errorlevel 1 (
    >&2 echo ERROR [GitSink]: git push failed.
    set "GITSINK_RC=23"
    goto :finish
)

echo [GitSink] SUCCESS: push completed.

:finish
if defined GITSINK_MESSAGE_FILE if exist "%GITSINK_MESSAGE_FILE%" del /q "%GITSINK_MESSAGE_FILE%" >nul 2>&1
if "%GITSINK_PUSHD%"=="1" popd
if "%GITSINK_MANUAL%"=="1" (
    echo.
    echo [GitSink] Finished. Exit code: %GITSINK_RC%
    powershell -NoProfile -Command "$null = Read-Host 'Appuyez sur Entree pour fermer'"
)
exit /b %GITSINK_RC%

:read_message
powershell -NoProfile -Command "$ErrorActionPreference = 'Stop'; $m = Read-Host 'Message de mise a jour (vide = Automated-update)'; if ([string]::IsNullOrWhiteSpace($m)) { $m = 'Automated-update' }; [System.IO.File]::WriteAllText($env:GITSINK_MESSAGE_FILE, $m, (New-Object System.Text.UTF8Encoding($false))); Write-Host ('[GitSink] Commit message: ' + $m)"
if errorlevel 1 exit /b 1
if not exist "%GITSINK_MESSAGE_FILE%" exit /b 1
exit /b 0
