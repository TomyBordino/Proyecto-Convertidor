@echo off
title Quant BYMA - Detener
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows\detener.ps1"
if errorlevel 1 (
  echo.
  echo Hubo un error. Lee el mensaje de arriba.
  pause
)
