#requires -Version 7.0
[CmdletBinding()]
param(
    [ValidateRange(1,65535)] [int]$Port = 8501,
    [string]$PythonCommand = 'python',
    [switch]$NoInstall,
    [switch]$ForceInstall
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Instance.Common.ps1')
try {
    $context = Test-KoaBlankInstance -InstanceRoot $PSScriptRoot -RequireDb
    $before = Set-KoaBlankEnvironment -Context $context
    try {
        $tool = Join-Path $context.engine_root 'Start-KoaGui.ps1'
        $opts = @('-RootPath', $context.engine_root, '-ContentPath', $context.instance_root,
                  '-HostName', '127.0.0.1', '-Port', $Port, '-PythonCommand', $PythonCommand)
        if ($NoInstall) { $opts += '-NoInstall' }
        if ($ForceInstall) { $opts += '-ForceInstall' }
        & pwsh -NoProfile -File $tool @opts
        if ($LASTEXITCODE -ne 0) { throw "Démarrage du moteur échoué : code $LASTEXITCODE" }
    }
    finally { Restore-KoaBlankEnvironment -Previous $before }
}
catch {
    Write-Error $_.Exception.Message
    exit 1
}
