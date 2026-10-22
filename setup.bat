@echo off
rem Prepara o Valorant Creator Studio. Exemplos:  setup.bat   |   setup.bat -WithTranscription
rem A politica de execucao e liberada so para este processo (nada muda no sistema).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup.ps1" %*
echo.
pause
