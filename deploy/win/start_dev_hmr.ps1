param([switch]$NoBrowser)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$apiDir = Join-Path $root 'flask_shop'
$python = Join-Path $apiDir '.venv/Scripts/python.exe'
$logDir = Join-Path $root 'logs/launcher'
$stateFile = Join-Path $logDir 'processes.json'

function Test-Url([string]$url) {
    try {
        $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Test-ManagedProcess($entry) {
    if (-not $entry) { return $false }
    try {
        $process = Get-Process -Id $entry.id -ErrorAction Stop
        return $process.StartTime.ToUniversalTime().Ticks -eq [long]$entry.started
    } catch {
        return $false
    }
}

function Test-Port([int]$port) {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $port)
    try { $listener.Start(); return $false } catch { return $true } finally { $listener.Stop() }
}

function Save-State {
    $state | ConvertTo-Json | Set-Content -LiteralPath $stateFile -Encoding UTF8
}

function Start-ServiceProcess($name, $directory, $file, $arguments, $port, $url, $timeout) {
    $entry = $state[$name]
    if (Test-ManagedProcess $entry) {
        Write-Host "[INFO] Waiting for existing $name service..."
        if ($name -eq 'api') { Write-Host '[WARN] Existing API is reused; code and database configuration changes require a restart.' }
    } else {
        if (Test-Port $port) {
            throw "Port $port is already in use by another process. Stop it and try again."
        }
        Write-Host "[INFO] Starting $name..."
        $process = Start-Process -FilePath $file -ArgumentList $arguments -WorkingDirectory $directory `
            -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir "$name.log") `
            -RedirectStandardError (Join-Path $logDir "$name.error.log")
        $state[$name] = @{ id = $process.Id; started = $process.StartTime.ToUniversalTime().Ticks.ToString() }
        Save-State
    }
    $deadline = (Get-Date).AddSeconds($timeout)
    do {
        if (Test-Url $url) { return }
        if (-not (Test-ManagedProcess $state[$name])) {
            throw "$name stopped during startup. Check $logDir\$name.error.log and $name.log."
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    throw "$name did not become ready. Check $logDir\$name.error.log and $name.log."
}

try {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    if (-not (Test-Path $python)) { throw 'Python environment missing: flask_shop\.venv. Install the backend dependencies first.' }
    if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw 'Node.js/npm not found in PATH.' }
    foreach ($path in @('mall/node_modules/.bin/vite.cmd', 'vue_shop/node_modules/.bin/vue-cli-service.cmd')) {
        if (-not (Test-Path (Join-Path $root $path))) { throw "Frontend dependencies missing: $path. Run npm ci in that frontend directory." }
    }

    $state = @{}
    if (Test-Path $stateFile) {
        try {
            $previous = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
            foreach ($property in $previous.PSObject.Properties) { $state[$property.Name] = $property.Value }
        } catch { Write-Host '[WARN] Could not read previous launcher state.' }
    }

    Write-Host '[INFO] Checking the configured database...'
    Push-Location $apiDir
    try {
        $ErrorActionPreference = 'Continue'
        & $python 'scripts/verify/dev_preflight.py'
        $ErrorActionPreference = 'Stop'
        if ($LASTEXITCODE -ne 0) { throw 'Backend preflight failed. Check the message above; no fallback database was created.' }
    } finally { Pop-Location }

    $env:FLASK_PORT = '5002'
    $env:CORS_ORIGINS = 'http://127.0.0.1:5202,http://localhost:5202,http://127.0.0.1:8082,http://localhost:8082'
    $env:VITE_API_PROXY_TARGET = 'http://127.0.0.1:5002'
    $env:VUE_APP_API_PROXY_TARGET = 'http://127.0.0.1:5002'
    Start-ServiceProcess 'api' $apiDir $python 'run_dev_api.py' 5002 'http://127.0.0.1:5002/health/' 90
    Start-ServiceProcess 'mall' (Join-Path $root 'mall') $env:ComSpec '/d /s /c "npm run dev -- --host 127.0.0.1 --port 5202 --strictPort"' 5202 'http://127.0.0.1:5202/' 120
    Start-ServiceProcess 'admin' (Join-Path $root 'vue_shop') $env:ComSpec '/d /s /c "npm run serve -- --host 127.0.0.1 --port 8082"' 8082 'http://127.0.0.1:8082/admin/' 180

    $mallPing = Invoke-RestMethod -Uri 'http://127.0.0.1:5202/api/c/ping/' -TimeoutSec 5
    $adminPing = Invoke-RestMethod -Uri 'http://127.0.0.1:8082/health/' -TimeoutSec 5
    if ($mallPing.msg -ne 'c-api ok' -or $adminPing.app -ne 'ecommerce-shop') {
        throw 'Frontend API proxy returned an unexpected response. Check the launcher logs.'
    }
    Write-Host '[OK] Mall: http://127.0.0.1:5202/'
    Write-Host '[OK] Admin: http://127.0.0.1:8082/admin/'
    Write-Host "[INFO] Services run in the background. Logs: $logDir"
    if (-not $NoBrowser) {
        Start-Process 'http://127.0.0.1:5202/'
        Start-Process 'http://127.0.0.1:8082/admin/'
    }
} catch {
    Write-Host "[ERROR] $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
