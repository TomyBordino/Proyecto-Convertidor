# Detiene el backend, la web y una ingesta en curso de Quant BYMA.
param([switch]$SoloWeb)
# Nada de lo que pase acá debe cortar al script que lo llama (por ejemplo, Actualizar).
$ErrorActionPreference = "Continue"
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
        $id = Get-Content $ruta
        # El proceso puede haber terminado solo (p. ej. la ingesta): solo se cierra si sigue vivo.
        if (Get-Process -Id $id -ErrorAction SilentlyContinue) {
            # taskkill /T cierra también los procesos hijos (npm -> node).
            try { & taskkill.exe /PID $id /T /F *> $null } catch { }
        }
        Remove-Item $ruta -ErrorAction SilentlyContinue
    }
}
if (-not $SoloWeb) { Write-Host "Quant BYMA detenido." -ForegroundColor Green }
