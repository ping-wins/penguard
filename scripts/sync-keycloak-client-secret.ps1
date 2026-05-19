<#
.SYNOPSIS
    Align the Keycloak `penguard-bff` client secret with the value in
    .env after the first `docker compose up`.

.DESCRIPTION
    PowerShell mirror of scripts/sync-keycloak-client-secret.sh. The realm
    import ships with the literal `dev-client-secret`; the bootstrap-secrets
    script generated a random value into `.env`. Without this sync the BFF
    and Keycloak disagree and OAuth/Kerberos callbacks fail with
    `invalid_client` (manifests as a 502 on /api/auth/register).

.EXAMPLE
    PS> ./scripts/sync-keycloak-client-secret.ps1
#>

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$EnvFile = Join-Path $RepoRoot '.env'

if (-not (Test-Path $EnvFile)) {
    throw "$EnvFile not found. Run scripts/bootstrap-secrets.ps1 first."
}

# Minimal .env parser: KEY=VALUE lines, '#' comments, no quoting tricks.
$env_vars = @{}
foreach ($line in Get-Content $EnvFile) {
    if ($line -match '^\s*#') { continue }
    if ($line -match '^\s*$') { continue }
    if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$') {
        $env_vars[$Matches[1]] = $Matches[2]
    }
}

$required = @(
    'PENGUARD_KEYCLOAK_BASE_URL',
    'PENGUARD_KEYCLOAK_REALM',
    'PENGUARD_KEYCLOAK_CLIENT_ID',
    'PENGUARD_KEYCLOAK_CLIENT_SECRET',
    'KC_BOOTSTRAP_ADMIN_USERNAME',
    'KC_BOOTSTRAP_ADMIN_PASSWORD'
)
foreach ($name in $required) {
    if (-not $env_vars.ContainsKey($name) -or [string]::IsNullOrWhiteSpace($env_vars[$name])) {
        throw "$name is not set in $EnvFile"
    }
}

$KC_BASE = $env_vars['PENGUARD_KEYCLOAK_BASE_URL'].TrimEnd('/')
$REALM   = $env_vars['PENGUARD_KEYCLOAK_REALM']
$CLIENT  = $env_vars['PENGUARD_KEYCLOAK_CLIENT_ID']
$SECRET  = $env_vars['PENGUARD_KEYCLOAK_CLIENT_SECRET']
$ADMIN_U = $env_vars['KC_BOOTSTRAP_ADMIN_USERNAME']
$ADMIN_P = $env_vars['KC_BOOTSTRAP_ADMIN_PASSWORD']

Write-Host "Authenticating against $KC_BASE as $ADMIN_U..."

try {
    $tokenResponse = Invoke-RestMethod `
        -Method Post `
        -Uri "$KC_BASE/realms/master/protocol/openid-connect/token" `
        -Body @{
            username   = $ADMIN_U
            password   = $ADMIN_P
            grant_type = 'password'
            client_id  = 'admin-cli'
        } `
        -ContentType 'application/x-www-form-urlencoded'
} catch {
    throw "admin token request failed: $_"
}

$token = $tokenResponse.access_token
if ([string]::IsNullOrWhiteSpace($token)) {
    throw "admin token response did not include access_token"
}

Write-Host "Looking up client $CLIENT in realm $REALM..."

try {
    $clients = Invoke-RestMethod `
        -Method Get `
        -Uri "$KC_BASE/admin/realms/$REALM/clients?clientId=$CLIENT" `
        -Headers @{ Authorization = "Bearer $token" }
} catch {
    throw "client lookup failed: $_"
}

if (-not $clients -or $clients.Count -eq 0) {
    throw "client $CLIENT not found in realm $REALM"
}

$clientUuid = $clients[0].id
Write-Host "Pushing the new secret for client $CLIENT (uuid $clientUuid)..."

try {
    Invoke-RestMethod `
        -Method Put `
        -Uri "$KC_BASE/admin/realms/$REALM/clients/$clientUuid" `
        -Headers @{ Authorization = "Bearer $token" } `
        -ContentType 'application/json' `
        -Body (@{ secret = $SECRET } | ConvertTo-Json -Compress) | Out-Null
} catch {
    throw "PUT /clients/$clientUuid failed: $_"
}

Write-Host "Done. The Keycloak client secret now matches PENGUARD_KEYCLOAK_CLIENT_SECRET in .env."

# Disable Kerberos storage provider when running without a real AD/KDC.
# The placeholder keytab signals a local-dev or lab setup where no Windows
# Server is running. Leaving Kerberos enabled causes "Cannot locate KDC"
# errors that block user creation and login.
$keytabPath = if ($env_vars.ContainsKey('PENGUARD_KEYTAB_PATH')) { $env_vars['PENGUARD_KEYTAB_PATH'] } else { '' }
if ($keytabPath -match 'empty-keytab|placeholder') {
    Write-Host "Empty keytab detected — disabling Kerberos storage provider in realm $REALM..."
    try {
        $components = Invoke-RestMethod `
            -Method Get `
            -Uri "$KC_BASE/admin/realms/$REALM/components?name=kerberos-penguard" `
            -Headers @{ Authorization = "Bearer $token" }
    } catch {
        Write-Warning "Kerberos component lookup failed (non-fatal): $_"
        $components = @()
    }
    if ($components -and $components.Count -gt 0) {
        $comp = $components[0]
        if ($comp.config.enabled -contains 'true') {
            $comp.config.enabled = @('false')
            try {
                Invoke-RestMethod `
                    -Method Put `
                    -Uri "$KC_BASE/admin/realms/$REALM/components/$($comp.id)" `
                    -Headers @{ Authorization = "Bearer $token" } `
                    -ContentType 'application/json' `
                    -Body ($comp | ConvertTo-Json -Depth 10 -Compress) | Out-Null
                Write-Host "Kerberos provider disabled. Enable it manually when a real AD/KDC is available."
            } catch {
                Write-Warning "Could not disable Kerberos provider (non-fatal): $_"
            }
        } else {
            Write-Host "Kerberos provider already disabled."
        }
    }
}
