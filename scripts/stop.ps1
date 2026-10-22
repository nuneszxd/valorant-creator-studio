<#
.SYNOPSIS
  Encerra uma instancia do Valorant Creator Studio em execucao (pede ao servidor local para parar).
#>
param([int]$Port = 8000)

try {
  Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$Port/api/system/shutdown" -TimeoutSec 10 | Out-Null
  Write-Host "Encerrando o Valorant Creator Studio (porta $Port)..."
} catch {
  Write-Host "Nenhuma instancia respondendo na porta $Port (ja estava encerrado?)."
}
