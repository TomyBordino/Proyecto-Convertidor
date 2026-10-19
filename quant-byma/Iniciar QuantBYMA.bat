@echo off
title Quant BYMA - Iniciar
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows\iniciar.ps1"
if errorlevel 1 (
  echo.
  echo Hubo un error. Lee el mensaje de arriba.
  pause
)
