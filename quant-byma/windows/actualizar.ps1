# Baja la última versión del código y vuelve a abrir Quant BYMA.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Write-Host "==> Cerrando Quant BYMA" -ForegroundColor Cyan
& (Join-Path $PSScriptRoot "detener.ps1")
Write-Host "==> Bajando la última versión" -ForegroundColor Cyan
& git -C $root pull
if ($LASTEXITCODE -ne 0) { throw "git pull falló. Revisá el mensaje de arriba." }
& (Join-Path $PSScriptRoot "iniciar.ps1")
