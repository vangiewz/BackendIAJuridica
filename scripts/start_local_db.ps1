<#
.SYNOPSIS
Levanta una base de datos PostgreSQL 100% local con soporte para Inteligencia Artificial (pgvector).
Esta base de datos es exclusiva para tu máquina y sirve para presentar el proyecto sin internet (Modo Búnker).

.DESCRIPTION
Este script descarga y corre un contenedor de Docker con la imagen 'ankane/pgvector'.
Expone el puerto 5432 a tu localhost.
#>

$ContainerName = "legal_db_bunker"
$ImageName = "ankane/pgvector:latest"
$DbPassword = "postgres"

Write-Host "Iniciando Base de Datos Local (Modo Bunker)..." -ForegroundColor Cyan

# Check if container exists
$existing = docker ps -a -q -f name=$ContainerName

if ($existing) {
    Write-Host "El contenedor '$ContainerName' ya existe. Intentando iniciarlo..." -ForegroundColor Yellow
    docker start $ContainerName
} else {
    Write-Host "Creando y levantando un nuevo contenedor '$ContainerName'..." -ForegroundColor Green
    docker run -d --name $ContainerName -e POSTGRES_PASSWORD=$DbPassword -p 5433:5432 $ImageName
}

Write-Host "Verificando si la base de datos necesita sincronizarse..." -ForegroundColor Cyan

# Extraer URL de Neon del .env
$envFile = Get-Content -Path ".\.env" -ErrorAction SilentlyContinue
if (-not $envFile) { $envFile = Get-Content -Path "..\.env" -ErrorAction SilentlyContinue }

$NeonUrl = $null
if ($envFile) {
    $neonLine = $envFile | Select-String -Pattern "^#?\s*DATABASE_URL=`"([^`"]*neon\.tech[^`"]*)`""
    if ($neonLine) { $NeonUrl = $neonLine.Matches.Groups[1].Value }
}

$UserCountStr = docker exec -i $ContainerName psql -U postgres -d postgres -t -c "SELECT count(*) FROM usuarios;" 2>$null
$UserCount = 0
if ($UserCountStr -match "\d+") { $UserCount = [int]($UserCountStr.Trim()) }

if ($UserCount -gt 0) {
    Write-Host "La base de datos ya tiene datos (usuarios encontrados). Omitiendo clonacion." -ForegroundColor Green
} else {
    if ($NeonUrl) {
        Write-Host "La base local esta vacia. Clonando desde Neon de forma automatica..." -ForegroundColor Yellow
        Write-Host "Bypass de version: descargando postgres:latest temporalmente..." -ForegroundColor Cyan
        
        # Truco para saltarse la restriccion de version 18.6 de Neon usando un contenedor temporal
        $CloneCmd = "docker run --rm -i postgres:latest pg_dump -d `"$NeonUrl`" --clean --if-exists --no-owner --no-privileges | docker exec -i $ContainerName psql -U postgres -d postgres"
        Invoke-Expression $CloneCmd
        
        Write-Host "¡Clonación completada con éxito desde Neon!" -ForegroundColor Green
    } else {
        Write-Host "La base de datos local esta vacia, pero no se encontro la URL de Neon en el archivo .env para clonar." -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "¡Listo! Tu base de datos local está corriendo en localhost:5433" -ForegroundColor Green
