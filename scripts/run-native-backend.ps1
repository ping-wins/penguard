# Native backend runner — needed for CLI AI provider mode.
#
# Why this exists: the standard `docker compose up` runs the backend
# inside a Linux container that can't see the host's `claude.exe` /
# `codex.exe` or its auth state. To use Settings -> Assistente IA -> CLI,
# the backend must run on the host. This script:
#   1. Loads secrets from .env (POSTGRES_*, PENGUARD_*).
#   2. Points DATABASE_URL + sister-service URLs at localhost ports
#      exposed by `docker compose up -d db keycloak siem-kowalski
#      soar-skipper xdr-rico redis`.
#   3. Applies Alembic migrations.
#   4. Starts uvicorn with --reload on port 8000.

param(
  [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path "$PSScriptRoot\..").Path
$apiDir = Join-Path $repoRoot "apps\api"
$envFile = Join-Path $repoRoot ".env"

if (-not (Test-Path $envFile)) {
  Write-Error ".env not found at $envFile. Run scripts/bootstrap-secrets.ps1 first."
}

# Load .env into the current shell, but force host-friendly URLs.
Get-Content $envFile | ForEach-Object {
  $line = $_.Trim()
  if (-not $line -or $line.StartsWith("#")) { return }
  $eq = $line.IndexOf("=")
  if ($eq -lt 1) { return }
  $name = $line.Substring(0, $eq).Trim()
  $value = $line.Substring($eq + 1).Trim()
  # Expand ${VAR} references against what we already loaded.
  $expanded = [regex]::Replace($value, '\$\{([A-Z0-9_]+)\}', {
    param($m)
    $key = $m.Groups[1].Value
    $existing = (Get-Item "Env:$key" -ErrorAction SilentlyContinue).Value
    if ($null -ne $existing) { $existing } else { $m.Value }
  })
  Set-Item -Path "Env:$name" -Value $expanded
}

# Override URLs so the native backend talks to the docker-exposed ports.
# Postgres is published on PENGUARD_POSTGRES_PORT (defaults to 5432
# but most local envs remap it via .env to dodge a host Postgres conflict).
$pgUser = $env:POSTGRES_USER
$pgPass = $env:POSTGRES_PASSWORD
$pgDb   = $env:POSTGRES_DB
$pgPort = if ($env:PENGUARD_POSTGRES_PORT) { $env:PENGUARD_POSTGRES_PORT } else { "5432" }
$kcPort = if ($env:PENGUARD_KEYCLOAK_PORT) { $env:PENGUARD_KEYCLOAK_PORT } else { "8080" }
$siemPort = if ($env:PENGUARD_SIEM_KOWALSKI_PORT) { $env:PENGUARD_SIEM_KOWALSKI_PORT } else { "8011" }
$soarPort = if ($env:PENGUARD_SOAR_SKIPPER_PORT) { $env:PENGUARD_SOAR_SKIPPER_PORT } else { "8012" }
$xdrPort  = if ($env:PENGUARD_XDR_RICO_PORT)     { $env:PENGUARD_XDR_RICO_PORT }     else { "8013" }

$dbUrl = "postgresql+psycopg://${pgUser}:${pgPass}@localhost:${pgPort}/${pgDb}"
$env:PENGUARD_DATABASE_URL = $dbUrl
$env:PENGUARD_KEYCLOAK_BASE_URL = "http://localhost:$kcPort"
$env:PENGUARD_KEYCLOAK_BROWSER_BASE_URL = "http://localhost:$kcPort"
$env:PENGUARD_SIEM_KOWALSKI_URL = "http://localhost:$siemPort"
$env:PENGUARD_SOAR_SKIPPER_URL = "http://localhost:$soarPort"
$env:PENGUARD_XDR_RICO_URL = "http://localhost:$xdrPort"
$env:SIEM_KOWALSKI_DATABASE_URL = $dbUrl
$env:SOAR_SKIPPER_DATABASE_URL = $dbUrl
$env:XDR_RICO_DATABASE_URL = $dbUrl

# uv is installed at ~/.local/bin on Windows via the official installer.
$uvPath = "$env:USERPROFILE\.local\bin"
if (Test-Path "$uvPath\uv.exe") {
  $env:Path = "$uvPath;$env:Path"
}

Push-Location $apiDir
try {
  Write-Host "==> uv sync" -ForegroundColor Cyan
  & uv sync | Out-Null

  Write-Host "==> alembic upgrade head" -ForegroundColor Cyan
  & uv run alembic upgrade head

  Write-Host "==> uvicorn on http://localhost:$Port (Ctrl+C to stop)" -ForegroundColor Cyan
  & uv run uvicorn app.main:app --reload --host 0.0.0.0 --port $Port
}
finally {
  Pop-Location
}
