# Arranca FastAPI escuchando en toda la red local (para usarlo desde otra PC o el celular).
#
#   .\scripts\start_backend.ps1            # puerto 8000
#   .\scripts\start_backend.ps1 -Port 8001
#
# No modifica configuracion ni el firewall.
param([int]$Port = 8000)

Set-Location (Split-Path -Parent $PSScriptRoot)
$venvPy = ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) { throw "No existe .venv. Ejecuta primero .\scripts\setup_windows.ps1" }

Write-Host "Backend en http://0.0.0.0:$Port  (health: http://localhost:$Port/api/v1/health)"
Write-Host "Desde otro equipo usa la IP de esta PC:" -NoNewline
(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notmatch "^(127|169\.254)\." } |
    ForEach-Object { " $($_.IPAddress)" }) -join "," | Write-Host
& $venvPy -m uvicorn app.main:app --host 0.0.0.0 --port $Port
