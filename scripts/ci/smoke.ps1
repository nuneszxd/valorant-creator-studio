# CI smoke test (Windows PowerShell 5.1): starts the app exactly like start.bat would, checks that the
# API and the compiled interface respond, then stops it with stop.ps1.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location -LiteralPath $root
$log = Join-Path $root "smoke.log"
function Log($text) { Write-Host $text; Add-Content -LiteralPath $log -Value $text }
$port = 8765
$venvPy = Join-Path $root ".venv\Scripts\python.exe"
$proc = $null

try {
  Log "Starting server on port $port"
  $proc = Start-Process -FilePath $venvPy -ArgumentList @("-m", "vcs", "serve", "--port", "$port") `
    -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $root "smoke.out") -RedirectStandardError (Join-Path $root "smoke.err")

  $health = $null
  for ($i = 0; $i -lt 60 -and -not $health; $i++) {
    try { $health = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/health" -TimeoutSec 3 } catch { Start-Sleep -Seconds 1 }
  }
  if (-not $health -or $health.status -ne "ok") { throw "API did not become healthy" }
  Log "health: $($health.status) v$($health.version)"

  $index = Invoke-WebRequest -Uri "http://127.0.0.1:$port/" -UseBasicParsing
  if ($index.Content -notmatch "Valorant Creator Studio") { throw "index.html not served (frontend not built?)" }
  if ($index.Content -notmatch 'id="root"') { throw "index.html has no root element" }
  Log "index served ($($index.Content.Length) bytes)"

  $asset = [regex]::Match($index.Content, 'src="(/assets/[^"]+\.js)"')
  if (-not $asset.Success) { throw "no JS asset referenced in index.html" }
  $js = Invoke-WebRequest -Uri ("http://127.0.0.1:$port" + $asset.Groups[1].Value) -UseBasicParsing
  Log "asset served: $($asset.Groups[1].Value) ($($js.Content.Length) chars)"

  $spa = Invoke-WebRequest -Uri "http://127.0.0.1:$port/candidates" -UseBasicParsing
  if ($spa.Content -notmatch 'id="root"') { throw "SPA fallback did not return index.html" }
  Log "SPA fallback ok"

  $caps = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/system/capabilities"
  Log "ffmpeg available: $($caps.ffmpeg.available)"
  $overview = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/overview"
  Log "overview recordings: $($overview.recordings.total)"

  & (Join-Path $root "scripts\stop.ps1") -Port $port
  for ($i = 0; $i -lt 40 -and -not $proc.HasExited; $i++) { Start-Sleep -Milliseconds 500 }
  if (-not $proc.HasExited) { throw "server did not stop after stop.ps1" }
  Log "server stopped cleanly (exit code $($proc.ExitCode))"
}
catch {
  Log "FAILED: $($_.Exception.Message)"
  if (Test-Path (Join-Path $root "smoke.err")) { Log "--- server stderr ---"; Get-Content (Join-Path $root "smoke.err") -Tail 40 | ForEach-Object { Log $_ } }
  if (Test-Path (Join-Path $root "smoke.out")) { Log "--- server stdout ---"; Get-Content (Join-Path $root "smoke.out") -Tail 20 | ForEach-Object { Log $_ } }
  if ($proc -and -not $proc.HasExited) { Stop-Process -Id $proc.Id -Force }
  exit 1
}
exit 0
