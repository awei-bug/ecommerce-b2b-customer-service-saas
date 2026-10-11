# Windows health check for local API / optional public URL
param(
  [string]$ApiUrl = "http://127.0.0.1:5000",
  [string]$PublicUrl = ""
)
$ErrorActionPreference = "Continue"
function Probe($url) {
  try {
    $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5
    Write-Host "[OK] $url -> $($r.StatusCode)"
    return $true
  } catch {
    Write-Host "[FAIL] $url -> $($_.Exception.Message)"
    return $false
  }
}
$ok = Probe "$ApiUrl/health/"
if ($PublicUrl) {
  $ok = (Probe "$PublicUrl/health/") -and $ok
  $ok = (Probe "$PublicUrl/") -and $ok
  $ok = (Probe "$PublicUrl/admin/") -and $ok
}
if (-not $ok) { exit 1 }
Write-Host "healthcheck passed"
