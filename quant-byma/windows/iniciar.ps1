# Levanta Quant BYMA (backend + web) en segundo plano y abre el navegador.
# Lo llama "Iniciar QuantBYMA.bat"; no hace falta ejecutarlo a mano.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$logs = Join-Path $root "logs"
New-Item -ItemType Directory -Force $logs | Out-Null
$py = Join-Path $backend ".venv\Scripts\python.exe"

function Paso($texto) { Write-Host ""; Write-Host "==> $texto" -ForegroundColor Cyan }

function Puerto-Abierto($puerto) {
    try {
        $c = New-Object Net.Sockets.TcpClient
        $c.Connect("127.0.0.1", $puerto)
        $c.Close()
        return $true
    } catch { return $false }
}

function Esperar-Url($url, $segundos) {
    $fin = (Get-Date).AddSeconds($segundos)
    while ((Get-Date) -lt $fin) {
        try { return Invoke-RestMethod $url -TimeoutSec 5 } catch { Start-Sleep -Seconds 2 }
    }
    return $null
}

function Huella($archivo) { (Get-FileHash $archivo -Algorithm SHA256).Hash }

Write-Host "Quant BYMA" -ForegroundColor Green

# 1. Entorno de Python (solo la primera vez o si cambian las dependencias)
if (-not (Test-Path $py)) {
    Paso "Creando el entorno de Python (solo la primera vez)"
    $base = Get-Command py -ErrorAction SilentlyContinue
    if ($base) { & py -3 -m venv (Join-Path $backend ".venv") }
    else { & python -m venv (Join-Path $backend ".venv") }
    if (-not (Test-Path $py)) { throw "No se encontró Python. Instalalo desde https://www.python.org (marcando 'Add to PATH')." }
}
$marcaPy = Join-Path $backend ".venv\.qb-deps"
$huellaPy = Huella (Join-Path $backend "pyproject.toml")
if (-not (Test-Path $marcaPy) -or (Get-Content $marcaPy) -ne $huellaPy) {
    Paso "Instalando dependencias de Python"
    Push-Location $backend
    & $py -m pip install --disable-pip-version-check -q -e .
    $ok = $LASTEXITCODE -eq 0
    Pop-Location
    if (-not $ok) { throw "Falló la instalación de dependencias de Python." }
    Set-Content $marcaPy $huellaPy
}

# 2. Dependencias y compilación de la web (solo si cambió el código)
$marcaNpm = Join-Path $frontend "node_modules\.qb-deps"
$huellaNpm = Huella (Join-Path $frontend "package-lock.json")
if (-not (Test-Path $marcaNpm) -or (Get-Content $marcaNpm) -ne $huellaNpm) {
    Paso "Instalando dependencias de la web (puede tardar unos minutos)"
    Push-Location $frontend
    & npm.cmd install --no-audit --no-fund
    $ok = $LASTEXITCODE -eq 0
    Pop-Location
    if (-not $ok) { throw "Falló npm install. ¿Está instalado Node.js? https://nodejs.org" }
    Set-Content $marcaNpm $huellaNpm
}
$version = "sin-git"
try {
    $v = & git -C $root rev-parse HEAD 2>$null
    if ($LASTEXITCODE -eq 0 -and $v) { $version = $v }
} catch { }
$marcaBuild = Join-Path $frontend ".next\.qb-version"
$buildId = Join-Path $frontend ".next\BUILD_ID"
if (-not (Test-Path $buildId) -or -not (Test-Path $marcaBuild) -or (Get-Content $marcaBuild) -ne $version) {
    if (Puerto-Abierto 3000) {
        Paso "Cerrando la web anterior para actualizarla"
        & (Join-Path $PSScriptRoot "detener.ps1") -SoloWeb
    }
    Paso "Compilando la web (solo después de cada actualización, 1-2 minutos)"
    Push-Location $frontend
    & npm.cmd run build
    $ok = $LASTEXITCODE -eq 0
    Pop-Location
    if (-not $ok) { throw "Falló la compilación de la web. Revisá el mensaje de arriba." }
    Set-Content $marcaBuild $version
}

# 3. Backend (con la actualización diaria automática de las 18:15 activada)
$marcaBackend = Join-Path $logs "backend.version"
if ((Puerto-Abierto 8000) -and (-not (Test-Path $marcaBackend) -or (Get-Content $marcaBackend) -ne $version)) {
    Paso "Reiniciando el backend con la versión nueva"
    & (Join-Path $PSScriptRoot "detener.ps1") -SoloBackend
    Start-Sleep -Seconds 2
}
if (Puerto-Abierto 8000) {
    Paso "El backend ya estaba corriendo"
} else {
    Paso "Iniciando el backend"
    $env:QB_SCHEDULER_ENABLED = "true"
    $p = Start-Process -FilePath $py -WorkingDirectory $backend -WindowStyle Hidden -PassThru `
        -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" `
        -RedirectStandardOutput (Join-Path $logs "backend.log") -RedirectStandardError (Join-Path $logs "backend-errores.log")
    Set-Content (Join-Path $logs "backend.pid") $p.Id
    Set-Content $marcaBackend $version
}

# 4. Web
if (Puerto-Abierto 3000) {
    Paso "La web ya estaba corriendo"
} else {
    Paso "Iniciando la web"
    $p = Start-Process -FilePath "cmd.exe" -WorkingDirectory $frontend -WindowStyle Hidden -PassThru `
        -ArgumentList "/c", "npm.cmd", "run", "start" `
        -RedirectStandardOutput (Join-Path $logs "web.log") -RedirectStandardError (Join-Path $logs "web-errores.log")
    Set-Content (Join-Path $logs "web.pid") $p.Id
}

Paso "Esperando a que todo responda"
$salud = Esperar-Url "http://127.0.0.1:8000/api/health" 90
if (-not $salud) { throw "El backend no respondió. Mirá logs\backend-errores.log." }
if (-not (Esperar-Url "http://127.0.0.1:3000" 90)) { throw "La web no respondió. Mirá logs\web-errores.log." }

# 5. Si los datos tienen más de 20 horas, actualizarlos en segundo plano
$ultima = $null
if ($salud.last_ingestion) { $ultima = [datetime]$salud.last_ingestion.at }
$pidIngesta = Join-Path $logs "ingesta.pid"
$corriendo = $false
if (Test-Path $pidIngesta) {
    $corriendo = [bool](Get-Process -Id (Get-Content $pidIngesta) -ErrorAction SilentlyContinue)
}
if (-not $corriendo -and (-not $ultima -or $ultima -lt (Get-Date).ToUniversalTime().AddHours(-20))) {
    Paso "Actualizando datos en segundo plano (10-20 minutos; la web se puede usar mientras tanto)"
    $p = Start-Process -FilePath $py -WorkingDirectory $backend -WindowStyle Hidden -PassThru `
        -ArgumentList "-m", "app.scheduler", "--once" `
        -RedirectStandardOutput (Join-Path $logs "ingesta.log") -RedirectStandardError (Join-Path $logs "ingesta-errores.log")
    Set-Content $pidIngesta $p.Id
}

# 6. Acceso directo en el escritorio (solo la primera vez)
$escritorio = [Environment]::GetFolderPath("Desktop")
$atajo = Join-Path $escritorio "Quant BYMA.lnk"
if (-not (Test-Path $atajo)) {
    $ws = New-Object -ComObject WScript.Shell
    $s = $ws.CreateShortcut($atajo)
    $s.TargetPath = Join-Path $root "Iniciar QuantBYMA.bat"
    $s.WorkingDirectory = $root
    $s.WindowStyle = 7
    $s.Description = "Abrir Quant BYMA"
    $s.Save()
    Paso "Creé el acceso directo 'Quant BYMA' en el escritorio"
}

Start-Process "http://localhost:3000"
Write-Host ""
Write-Host "Listo: Quant BYMA está abierto en el navegador." -ForegroundColor Green
Write-Host "Para cerrarlo, usá 'Detener QuantBYMA.bat'."
Start-Sleep -Seconds 3
