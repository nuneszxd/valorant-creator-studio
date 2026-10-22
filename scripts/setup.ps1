<#
.SYNOPSIS
  Prepara o Valorant Creator Studio neste computador: ambiente Python (.venv), dependencias,
  interface compilada e arquivo .env.

.PARAMETER WithTranscription
  Instala tambem o faster-whisper (transcricao local; roda na CPU). O modelo so e baixado depois,
  com a sua permissao, na tela de analise.

.PARAMETER WithDev
  Instala as dependencias de teste (pytest).

.PARAMETER SkipFrontend
  Nao instala/compila a interface (so o backend).
#>
param(
  [switch]$WithTranscription,
  [switch]$WithDev,
  [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root

function Write-Step($text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host "ERRO: $text" -ForegroundColor Red; exit 1 }

function Find-Python {
  $candidates = @(
    @{ exe = "py"; args = @("-3.12") },
    @{ exe = "py"; args = @("-3.11") },
    @{ exe = "py"; args = @("-3") },
    @{ exe = "python"; args = @() },
    @{ exe = "python3"; args = @() }
  )
  foreach ($c in $candidates) {
    if (-not (Get-Command $c.exe -ErrorAction SilentlyContinue)) { continue }
    try {
      $out = & $c.exe @($c.args) -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
      if ($LASTEXITCODE -ne 0 -or -not $out) { continue }
      $parts = ($out | Select-Object -First 1).Trim().Split(".")
      if ([int]$parts[0] -gt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -ge 11)) { return $c }
    } catch { continue }
  }
  return $null
}

Write-Step "Verificando o Python (3.11 ou superior)"
$py = Find-Python
if (-not $py) {
  Fail "Python 3.11+ nao encontrado. Instale o Python 3.12 em https://www.python.org/downloads/ (marque 'Add python.exe to PATH') e rode este script de novo."
}
Write-Host ("Usando: {0} {1}" -f $py.exe, ($py.args -join " "))

$venv = Join-Path $root ".venv"
$venvPy = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPy)) {
  Write-Step "Criando o ambiente virtual (.venv)"
  & $py.exe @($py.args) -m venv $venv
  if ($LASTEXITCODE -ne 0) { Fail "Nao foi possivel criar o ambiente virtual." }
}

Write-Step "Instalando as dependencias do backend"
& $venvPy -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { Fail "Falha ao atualizar o pip." }
$extras = @()
if ($WithTranscription) { $extras += "transcribe" }
if ($WithDev) { $extras += "dev" }
$spec = "backend"
if ($extras.Count -gt 0) { $spec = "backend[" + ($extras -join ",") + "]" }
& $venvPy -m pip install -e $spec
if ($LASTEXITCODE -ne 0) { Fail "Falha ao instalar o backend ($spec). Veja a mensagem acima." }

if (-not $SkipFrontend) {
  Write-Step "Compilando a interface (precisa do Node.js)"
  if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Fail "Node.js nao encontrado. Instale o Node.js LTS em https://nodejs.org/ e rode este script de novo (ou use -SkipFrontend para so o backend)."
  }
  Push-Location -LiteralPath (Join-Path $root "frontend")
  try {
    & npm.cmd install --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { Fail "npm install falhou." }
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { Fail "A compilacao da interface falhou." }
  } finally {
    Pop-Location
  }
}

$envFile = Join-Path $root ".env"
if (-not (Test-Path -LiteralPath $envFile)) {
  Copy-Item -LiteralPath (Join-Path $root ".env.example") -Destination $envFile
  Write-Host "Criado .env a partir de .env.example (edite para adicionar chaves da Twitch/YouTube, se quiser)."
}

Write-Step "Verificando o ambiente"
& $venvPy -m vcs doctor
$doctorCode = $LASTEXITCODE

Write-Host ""
if ($doctorCode -eq 0) {
  Write-Host "Pronto. Para iniciar: start.bat" -ForegroundColor Green
} else {
  Write-Host "Instalado, mas ha pendencias acima (por exemplo, FFmpeg). Corrija e rode doctor.bat para conferir." -ForegroundColor Yellow
}
exit 0
