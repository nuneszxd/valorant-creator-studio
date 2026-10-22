@echo off
rem Inicia o Valorant Creator Studio (abre o navegador). Feche esta janela ou use Ctrl+C para encerrar.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" %*
echo.
pause
