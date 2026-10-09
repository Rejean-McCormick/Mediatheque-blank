#requires -Version 7.0
$ErrorActionPreference = "Stop"

$instance = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$engine = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\mediatheque")).Path

$previousContentRoot = $env:KOA_CONTENT_ROOT
try {
    $env:KOA_CONTENT_ROOT = $instance
    & (Join-Path $engine "05_TOOLS\Initialize-KoaMediathequeDb.ps1") @args
}
finally {
    $env:KOA_CONTENT_ROOT = $previousContentRoot
}
