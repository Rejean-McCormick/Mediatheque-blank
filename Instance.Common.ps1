#requires -Version 7.0
Set-StrictMode -Version Latest

function Get-KoaInstancePython {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) { return @{Exe = $python.Source; Args = @()} }
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) { return @{Exe = $launcher.Source; Args = @('-3')} }
    throw 'Python 3.11+ introuvable. Installer Python avant de lancer cette instance.'
}

function Test-KoaBlankInstance {
    param([Parameter(Mandatory = $true)] [string]$InstanceRoot, [switch]$RequireDb)
    $py = Get-KoaInstancePython
    $script = Join-Path $InstanceRoot 'tools/instance_guard.py'
    $opts = @('--instance-root', $InstanceRoot)
    if ($RequireDb) { $opts += '--require-db' }
    $pyArgs = @($py.Args)
    $result = & $py.Exe @pyArgs $script @opts
    if ($LASTEXITCODE -ne 0) { throw "Précontrôle d'instance refusé. $($result -join ' ')" }
    return ($result | ConvertFrom-Json -ErrorAction Stop)
}

function Set-KoaBlankEnvironment {
    param([object]$Context)
    $root = [string] $Context.instance_root
    $vars = [ordered]@{
        KOA_ROOT = [string] $Context.engine_root
        KOA_APP_ROOT = [string] $Context.engine_root
        KOA_CONTENT_ROOT = $root
        KOA_DB_PATH = [string] $Context.database
        KOA_STORAGE_ROOT = [string] $Context.storage
        KOA_IMPORTS_ROOT = Join-Path $root '03_IMPORTS'
        KOA_EXPORTS_ROOT = Join-Path $root '04_EXPORTS'
        KOA_BACKUPS_ROOT = Join-Path $root '07_BACKUPS'
        KOA_LOGS_ROOT = Join-Path $root '08_LOGS'
    }
    $previous = @{}
    foreach ($key in $vars.Keys) {
        $previous[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
        [Environment]::SetEnvironmentVariable($key, $vars[$key], 'Process')
    }
    return $previous
}

function Restore-KoaBlankEnvironment {
    param([hashtable]$Previous)
    foreach ($key in $Previous.Keys) {
        [Environment]::SetEnvironmentVariable($key, $Previous[$key], 'Process')
    }
}
