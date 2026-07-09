[CmdletBinding()]
param(
    [string]$Destination = "backups",
    [switch]$KeepRunning
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$dataPath = Join-Path $root "data"
if (-not (Test-Path -LiteralPath $dataPath)) {
    throw "Pasta data nao encontrada. Suba o bot pelo menos uma vez antes de criar backup."
}

$items = Get-ChildItem -LiteralPath $dataPath -Force
if (-not $items) {
    throw "A pasta data esta vazia. Nao ha bancos para copiar."
}

if (-not (Test-Path -LiteralPath $Destination)) {
    New-Item -ItemType Directory -Path $Destination | Out-Null
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$archivePath = Join-Path $Destination "data-$timestamp.zip"

if ($KeepRunning) {
    Write-Warning "Backup com o bot ligado pode capturar SQLite em escrita. Prefira o modo padrao para backup consistente."
    Compress-Archive -LiteralPath $items.FullName -DestinationPath $archivePath -Force
} else {
    docker compose stop discord-bot
    try {
        Compress-Archive -LiteralPath $items.FullName -DestinationPath $archivePath -Force
    } finally {
        docker compose up -d discord-bot
    }
}

Write-Host "Backup criado em $archivePath"
