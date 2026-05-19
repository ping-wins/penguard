# Provisions the FortiGate Automation Stitch that pushes admin-login-failed
# events to the Penguard BFF ingestion endpoint. Idempotent: deletes
# stitch+action+trigger first if they already exist, then re-creates them.
#
# Usage:
#   pwsh ./scripts/setup_fortigate_webhook.ps1 `
#       -FortiGateHost https://192.168.0.100 `
#       -FortiGateApiKey <key> `
#       -BffUrl http://192.168.0.138:8000/api/soc/ingest/fortigate `
#       -IngestToken <token>

[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $FortiGateHost,
    [Parameter(Mandatory)] [string] $FortiGateApiKey,
    [Parameter(Mandatory)] [string] $BffUrl,
    [Parameter(Mandatory)] [string] $IngestToken,
    [string] $TriggerName = "PG-Brute-Force",
    [string] $ActionName = "PG-Ingest-Webhook",
    [string] $StitchName = "PG-Hydra-Detection",
    [int] $LogId = 32002
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$base = $FortiGateHost.TrimEnd('/')
$headers = @{Authorization = "Bearer $FortiGateApiKey"}

function Invoke-Fgt {
    param([string] $Method, [string] $Path, $Body)
    $uri = "$base$Path"
    $params = @{
        Method = $Method
        Uri = $uri
        Headers = $headers
        SkipCertificateCheck = $true
        UseBasicParsing = $true
        TimeoutSec = 15
    }
    if ($Body) {
        $params.Body = ($Body | ConvertTo-Json -Depth 10 -Compress)
        $params.ContentType = "application/json"
    }
    try {
        $r = Invoke-WebRequest @params
        return ($r.Content | ConvertFrom-Json)
    } catch {
        $msg = $_.Exception.Message
        if ($_.ErrorDetails -and $_.ErrorDetails.Message) {
            $msg += " :: " + $_.ErrorDetails.Message
        }
        throw "FortiGate API $Method $Path failed: $msg"
    }
}

function Remove-IfExists {
    param([string] $Path, [string] $Name)
    try {
        Invoke-Fgt -Method GET -Path "$Path/$Name" | Out-Null
        Write-Host "Removing existing $Name at $Path" -ForegroundColor Yellow
        Invoke-Fgt -Method DELETE -Path "$Path/$Name" | Out-Null
    } catch {
        Write-Host "  (no pre-existing $Name)" -ForegroundColor DarkGray
    }
}

Write-Host "==> Cleaning previous Penguard automation objects" -ForegroundColor Cyan
Remove-IfExists -Path "/api/v2/cmdb/system/automation-stitch"  -Name $StitchName
Remove-IfExists -Path "/api/v2/cmdb/system/automation-action"  -Name $ActionName
Remove-IfExists -Path "/api/v2/cmdb/system/automation-trigger" -Name $TriggerName

Write-Host "==> Creating trigger '$TriggerName' (event-type: ssh-logs)" -ForegroundColor Cyan
$triggerBody = @{
    name           = $TriggerName
    description    = "Penguard: fire on SSH/admin login activity (hydra brute-force)"
    "trigger-type" = "event-based"
    "event-type"   = "ssh-logs"
}
Invoke-Fgt -Method POST -Path "/api/v2/cmdb/system/automation-trigger" -Body $triggerBody | Out-Null

Write-Host "==> Creating webhook action '$ActionName' -> $BffUrl" -ForegroundColor Cyan
$payloadTemplate = @'
{"logid":"%%log.logid%%","type":"%%log.type%%","subtype":"%%log.subtype%%","action":"%%log.action%%","status":"%%log.status%%","level":"%%log.level%%","srcip":"%%log.srcip%%","dstip":"%%log.dstip%%","user":"%%log.user%%","msg":"%%log.msg%%","eventtime":"%%log.eventtime%%"}
'@
$actionBody = @{
    name           = $ActionName
    description    = "POST FortiGate event log to Penguard ingestion endpoint"
    "action-type"  = "webhook"
    protocol       = "http"
    method         = "post"
    uri            = $BffUrl
    "http-headers" = @(
        @{id = 1; key = "Authorization"; value = "Bearer $IngestToken"},
        @{id = 2; key = "Content-Type"; value = "application/json"}
    )
    "http-body"    = $payloadTemplate
}
Invoke-Fgt -Method POST -Path "/api/v2/cmdb/system/automation-action" -Body $actionBody | Out-Null

Write-Host "==> Creating stitch '$StitchName' binding trigger + action" -ForegroundColor Cyan
$stitchBody = @{
    name    = $StitchName
    status  = "enable"
    trigger = $TriggerName
    actions = @(@{id = 1; action = $ActionName; delay = 0; required = "enable"})
}
Invoke-Fgt -Method POST -Path "/api/v2/cmdb/system/automation-stitch" -Body $stitchBody | Out-Null

Write-Host "`nAutomation stitch '$StitchName' is enabled." -ForegroundColor Green
Write-Host "Next admin-login-failure on this FortiGate will POST to $BffUrl." -ForegroundColor Green
