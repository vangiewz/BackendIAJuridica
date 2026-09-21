# Prepara el backend en Windows: venv, dependencias, .env y comprobaciones.
#
#   powershell -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1
#
# Es seguro: no instala drivers ni CUDA, no toca el firewall, no cambia Git, no borra datos,
# no ejecuta migraciones y no sobrescribe un .env existente. Solo descarga modelos de
# Ollama si respondes que si.

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)   # raiz del backend

$Modelos = @("qwen3:8b", "qwen3-embedding:0.6b")
$PendienteManual = @()

function Paso($texto)  { Write-Host "`n== $texto" -ForegroundColor Cyan }
function Bien($texto)  { Write-Host "  OK     $texto" -ForegroundColor Green }
function Aviso($texto) { Write-Host "  AVISO  $texto" -ForegroundColor Yellow }

# --- 1. Python -------------------------------------------------------------
Paso "Python"
$py = $null
foreach ($candidato in @(@("py", "-3.13"), @("python"))) {
    try {
        $version = & $candidato[0] $candidato[1..($candidato.Length - 1)] --version 2>&1
        if ($LASTEXITCODE -eq 0 -and "$version" -match "Python 3\.(\d+)") { $py = $candidato; break }
    } catch { }
}
if (-not $py) { throw "No se encontro Python. Instala Python 3.13 desde https://www.python.org/downloads/ (marca 'Add python.exe to PATH')." }
$version = & $py[0] $py[1..($py.Length - 1)] --version
Bien $version
if ("$version" -notmatch "Python 3\.13") { Aviso "El proyecto se probo con Python 3.13; otra version puede funcionar pero no esta verificada." }

# --- 2. Entorno virtual y dependencias --------------------------------------
Paso "Entorno virtual"
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    & $py[0] $py[1..($py.Length - 1)] -m venv .venv
    Bien "creado .venv"
} else { Bien ".venv ya existe (no se recrea)" }
$venvPy = ".venv\Scripts\python.exe"

Paso "Dependencias (requirements.txt)"
& $venvPy -m pip install --upgrade pip --quiet
& $venvPy -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "pip no pudo instalar requirements.txt" }
Bien "dependencias instaladas"

# --- 3. .env ----------------------------------------------------------------
Paso "Archivo .env"
if (Test-Path ".env") {
    Bien ".env ya existe (no se modifica)"
} else {
    Copy-Item ".env.example" ".env"
    Bien "creado .env a partir de .env.example"
    $PendienteManual += "Editar .env: poner DATABASE_URL (la base real) y, si quieres, JWT_SECRET."
}

# --- 4. NVIDIA y Ollama ------------------------------------------------------
Paso "GPU NVIDIA"
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    & nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
} else {
    Aviso "nvidia-smi no esta disponible: instala el driver NVIDIA (Ollama usara la CPU hasta entonces)."
}

Paso "Ollama"
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Aviso "Ollama no esta instalado. Descargalo de https://ollama.com/download y vuelve a ejecutar este script."
    $PendienteManual += "Instalar Ollama y volver a ejecutar setup_windows.ps1 para descargar los modelos."
} else {
    Bien (& ollama --version 2>&1 | Select-Object -Last 1)
    $instalados = (& ollama list 2>$null) -join "`n"
    foreach ($modelo in $Modelos) {
        if ($instalados -match [regex]::Escape($modelo)) { Bien "modelo instalado: $modelo"; continue }
        Aviso "falta el modelo $modelo"
        $resp = Read-Host "  Descargar $modelo ahora? (s/N)"
        if ($resp -match "^[sSyY]") {
            & ollama pull $modelo
            if ($LASTEXITCODE -ne 0) { Aviso "fallo la descarga de $modelo" }
        } else {
            $PendienteManual += "ollama pull $modelo"
        }
    }
}

# --- 5. Verificacion ----------------------------------------------------------
Paso "Verificacion del entorno"
& $venvPy -m scripts.verificar_entorno
$verificacion = $LASTEXITCODE

Paso "Resumen"
if ($PendienteManual.Count -gt 0) {
    Write-Host "Pendiente:" -ForegroundColor Yellow
    $PendienteManual | ForEach-Object { Write-Host "  - $_" }
}
if ($verificacion -eq 0) {
    Write-Host "`nSiguiente: .\.venv\Scripts\python.exe -m scripts.warmup_ia   y luego   .\scripts\start_backend.ps1" -ForegroundColor Green
} else {
    Write-Host "`nLa verificacion tiene fallas: corrige lo indicado y ejecuta de nuevo este script (es repetible)." -ForegroundColor Yellow
}
