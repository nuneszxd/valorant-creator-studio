<#
.SYNOPSIS
  Inicia o Valorant Creator Studio (servidor local em 127.0.0.1). Ctrl+C encerra.
#>
param(
  [switch]$NoBrowser,
  [int]$Port = 0
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
$venvPy = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPy)) {
  Write-Host "Ambiente nao preparado. Rode setup.bat primeiro." -ForegroundColor Red
  exit 1
}

$cliArgs = @("-m", "vcs", "serve")
if (-not $NoBrowser) { $cliArgs += "--open" }
if ($Port -gt 0) { $cliArgs += @("--port", "$Port") }
& $venvPy @cliArgs
exit $LASTEXITCODE
