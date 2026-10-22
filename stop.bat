@echo off
rem Encerra o Valorant Creator Studio que estiver rodando.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop.ps1" %*
pause
