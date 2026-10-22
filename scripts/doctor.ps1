<#
.SYNOPSIS
  Mostra o que esta instalado/faltando (Python, FFmpeg, encoders, transcricao). Use -Deep para testar a codificacao de verdade.
#>
param([switch]$Deep)

$root = Split-Path -Parent $PSScriptRoot
$venvPy = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPy)) {
  Write-Host "Ambiente nao preparado. Rode setup.bat primeiro." -ForegroundColor Red
  exit 1
}
$cliArgs = @("-m", "vcs", "doctor")
if ($Deep) { $cliArgs += "--deep" }
& $venvPy @cliArgs
exit $LASTEXITCODE
