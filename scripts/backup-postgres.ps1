[CmdletBinding()]
param(
    [string]$Destination = "backups"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path -LiteralPath $Destination)) {
    New-Item -ItemType Directory -Path $Destination | Out-Null
}

docker compose up -d postgres

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$containerPath = "/tmp/copenhague-$timestamp.dump"
$hostPath = Join-Path $Destination "postgres-$timestamp.dump"

docker compose exec -T postgres sh -lc `
    "pg_dump -U `"`$POSTGRES_USER`" -d `"`$POSTGRES_DB`" -Fc -f $containerPath"
if ($LASTEXITCODE -ne 0) {
    throw "Falha ao gerar o backup PostgreSQL."
}

docker compose cp "postgres:$containerPath" $hostPath
if ($LASTEXITCODE -ne 0) {
    throw "Falha ao copiar o backup PostgreSQL para o host."
}

Write-Host "Backup PostgreSQL criado em $hostPath"
