# Detiene el backend, la web y una ingesta en curso de Quant BYMA.
param([switch]$SoloWeb)
$root = Split-Path -Parent $PSScriptRoot
$logs = Join-Path $root "logs"
$puertos = if ($SoloWeb) { @(3000) } else { @(8000, 3000) }

$pids = Get-NetTCPConnection -LocalPort $puertos -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique
foreach ($id in $pids) { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue }

$archivos = if ($SoloWeb) { @("web.pid") } else { @("backend.pid", "web.pid", "ingesta.pid") }
foreach ($f in $archivos) {
    $ruta = Join-Path $logs $f
    if (Test-Path $ruta) {
        # taskkill /T cierra también los procesos hijos (npm -> node).
        & taskkill.exe /PID (Get-Content $ruta) /T /F 2>$null | Out-Null
        Remove-Item $ruta -ErrorAction SilentlyContinue
    }
}
if (-not $SoloWeb) { Write-Host "Quant BYMA detenido." -ForegroundColor Green }
