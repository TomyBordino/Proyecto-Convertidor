@echo off
title Quant BYMA - Actualizar
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows\actualizar.ps1"
if errorlevel 1 (
  echo.
  echo Hubo un error. Lee el mensaje de arriba.
  pause
)
