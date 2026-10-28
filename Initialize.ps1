#requires -Version 7.0
# Initialise UNIQUEMENT une instance neuve; pas de schema Force implicite.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Instance.Common.ps1')
try {
    $context = Test-KoaBlankInstance -InstanceRoot $PSScriptRoot
    if ($context.initialized) { throw 'Base deja presente : sauvegarder et utiliser la procedure de migration du moteur, pas Initialize.' }
    $before = Set-KoaBlankEnvironment -Context $context
    try {
        $tool = Join-Path $context.engine_root '05_TOOLS/Initialize-KoaMediathequeDb.ps1'
        & pwsh -NoProfile -File $tool -DbPath $context.database -SchemaDir (Join-Path $context.engine_root 'schemas/sqlite')
        if ($LASTEXITCODE -ne 0) { throw "Initialisation du moteur échouée : code $LASTEXITCODE" }
    }
    finally { Restore-KoaBlankEnvironment -Previous $before }
}
catch {
    Write-Error $_.Exception.Message
    exit 1
}
