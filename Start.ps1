#requires -Version 7.0
$ErrorActionPreference = "Stop"

$instance = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$engine = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\mediatheque")).Path

& (Join-Path $engine "Start-KoaGui.ps1") `
    -RootPath $engine `
    -ContentPath $instance `
    @args
