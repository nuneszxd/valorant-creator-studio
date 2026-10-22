@echo off
rem Verifica o ambiente. Use  doctor.bat -Deep  para testar a codificacao de video de verdade.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\doctor.ps1" %*
echo.
pause
