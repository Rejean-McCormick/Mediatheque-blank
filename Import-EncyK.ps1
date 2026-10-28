#requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$Handoff,
    [Parameter(Mandatory = $true)] [string]$EvidenceRoot,
    [switch]$Accept
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Instance.Common.ps1')
try {
    $context = Test-KoaBlankInstance -InstanceRoot $PSScriptRoot -RequireDb:$Accept
    $py = Get-KoaInstancePython
    $tool = Join-Path $context.engine_root '05_TOOLS/ImportEncyKHandoff.py'
    $opts = @('--handoff', [IO.Path]::GetFullPath($Handoff), '--evidence-root', [IO.Path]::GetFullPath($EvidenceRoot))
    if ($Accept) {
        $opts += @('--accept', '--instance-root', $context.instance_root)
        $receiptDir = Join-Path $context.instance_root '03_IMPORTS/encyk_receipts'
        # L'écriture du reçu se fait uniquement sur acceptation explicite.
        New-Item -ItemType Directory -Path $receiptDir -Force | Out-Null
        $receipt = Join-Path $receiptDir ((Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N') + '.json')
        $opts += @('--receipt-out', $receipt)
    }
    $pyArgs = @($py.Args)
    & $py.Exe @pyArgs $tool @opts
    if ($LASTEXITCODE -ne 0) { throw "Transfert EncyK refusé : code $LASTEXITCODE" }
}
catch {
    Write-Error $_.Exception.Message
    exit 1
}
