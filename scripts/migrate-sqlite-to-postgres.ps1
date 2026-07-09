param(
    [switch]$Replace,
    [switch]$NoBackup,
    [switch]$SkipSchemaRefresh,
    [string]$PostgresDsn = "",
    [string]$Schema = ""
)

$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
Set-Location $projectRoot

if (-not $PostgresDsn) {
    $PostgresDsn = $env:POSTGRES_MIGRATION_DSN
}
if (-not $PostgresDsn) {
    $PostgresDsn = "postgresql://copenhague:copenhague@127.0.0.1:5432/copenhague"
}
if (-not $Schema) {
    $Schema = $env:POSTGRES_SCHEMA
}
if (-not $Schema) {
    $Schema = "copenhague"
}

Write-Host "Subindo Postgres local..."
docker compose up -d postgres

$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    $python = "python"
}

$arguments = @(
    "scripts/db_manage.py",
    "--postgres-dsn",
    $PostgresDsn,
    "--schema",
    $Schema,
    "migrate-sqlite"
)

if ($Replace) {
    $arguments += "--replace"
}
if ($NoBackup) {
    $arguments += "--no-backup"
}
if ($SkipSchemaRefresh) {
    $arguments += "--skip-schema-refresh"
}

Write-Host "Migrando SQLite para Postgres no schema '$Schema'..."
& $python @arguments
