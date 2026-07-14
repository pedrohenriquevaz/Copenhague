[CmdletBinding()]
param(
    [switch]$PullGit,
    [switch]$NoBuild
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path -LiteralPath ".env")) {
    throw "Arquivo .env nao encontrado. Crie uma copia de .env.example e preencha DISCORD_TOKEN."
}

if ($PullGit) {
    git pull --ff-only
}

if ($NoBuild) {
    docker compose up -d --remove-orphans
} else {
    docker compose build --pull
    docker compose up -d --remove-orphans
}

docker compose ps
Write-Host "Logs: docker compose logs -f --tail=100 discord-bot"
