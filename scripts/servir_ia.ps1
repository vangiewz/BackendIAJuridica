# Sirve la IA de esta PC al equipo: comprueba Ollama, precarga los modelos y levanta el tunel.
#
#   .\scripts\servir_ia.ps1 -Tunel ia-juridica
#   .\scripts\servir_ia.ps1 -Tunel ia-juridica -Hostname ia.midominio.com
#   .\scripts\servir_ia.ps1 -Tunel ia-juridica -SinPrecarga
#
# No modifica configuracion ni el firewall: cloudflared abre una conexion hacia afuera y le
# habla a 127.0.0.1, asi que Ollama nunca queda escuchando en la red.
param(
    [string]$Tunel = $env:CLOUDFLARE_TUNNEL,
    [string]$Hostname = "",
    [switch]$SinPrecarga
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not $Tunel) {
    throw "Falta el nombre del tunel. Usa -Tunel <nombre> o define CLOUDFLARE_TUNNEL."
}
if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    throw "No se encontro cloudflared. Instalalo con el comando que da el panel de Cloudflare."
}

# Exponer Ollama en 0.0.0.0 lo deja accesible en la LAN sin pasar por el token del tunel.
if ($env:OLLAMA_HOST -and $env:OLLAMA_HOST -notmatch "^(127\.0\.0\.1|localhost|\[?::1\]?)(:\d+)?$") {
    Write-Warning "OLLAMA_HOST=$env:OLLAMA_HOST no es loopback: el tunel no es la unica puerta a tu GPU."
}

Write-Host "1/3  Ollama en 127.0.0.1:11434 ..." -NoNewline
try {
    $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 5
} catch {
    Write-Host ""
    throw "Ollama no responde. Abri la app de Ollama o ejecuta 'ollama serve' en otra terminal."
}
Write-Host " ok ($($tags.models.Count) modelos)"

if ($SinPrecarga) {
    Write-Host "2/3  Precarga saltada (-SinPrecarga)."
} else {
    $venvPy = ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPy)) {
        Write-Warning "2/3  No existe .venv, no se precargan los modelos. La primera consulta va a tardar mas."
    } else {
        Write-Host "2/3  Precargando los modelos en la GPU (puede tardar)..."
        & $venvPy -m scripts.warmup_ia
        if ($LASTEXITCODE -ne 0) { Write-Warning "El warm-up fallo. El tunel se levanta igual." }
    }
}

if ($Hostname) {
    Write-Host "3/3  Tunel '$Tunel' -> https://$Hostname   (Ctrl+C para dejar de servir)"
} else {
    Write-Host "3/3  Tunel '$Tunel'   (Ctrl+C para dejar de servir)"
}
Write-Host "     Mientras esto corra, el equipo puede apuntar OLLAMA_URL a este servidor."
cloudflared tunnel run $Tunel
