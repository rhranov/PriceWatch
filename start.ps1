$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Python = "$ProjectDir\.venv\Scripts\python.exe"
$PidFile = "$ProjectDir\.pids"
$LogDir = "$ProjectDir\logs"

function Get-DotEnvValue([string]$Name, [string]$Default) {
    $processValue = [Environment]::GetEnvironmentVariable($Name)
    if (-not [string]::IsNullOrWhiteSpace($processValue)) {
        return $processValue.Trim()
    }
    $line = Get-Content -LiteralPath "$ProjectDir\.env" |
        Where-Object { $_ -match "^\s*$([regex]::Escape($Name))=(.*)$" } |
        Select-Object -Last 1
    if (-not $line) { return $Default }
    return ($line -replace "^\s*$([regex]::Escape($Name))=", "").Trim()
}

function Assert-FreePort([int]$Port, [string]$Service) {
    if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
        throw "Port $Port for $Service is already in use. Stop the other service or change the port in .env."
    }
}

function Test-Http([string]$Url) {
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
        return $response.StatusCode -lt 400
    } catch {
        return $false
    }
}

function Wait-Http([string]$Url, [int]$Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Http $Url) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

if (-not (Test-Path -LiteralPath "$ProjectDir\.env")) {
    throw "Missing .env. Run .\setup.ps1 first."
}
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Missing virtual environment. Run .\setup.ps1 first."
}
if (-not (docker info 2>$null)) {
    throw "Docker Desktop is not running."
}

$AppPort = [int](Get-DotEnvValue "APP_PORT" "8000")
$FrontendPort = [int](Get-DotEnvValue "FRONTEND_PORT" "3000")
Assert-FreePort $AppPort "FastAPI"
Assert-FreePort $FrontendPort "Next.js"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
& docker compose --file "$ProjectDir\docker-compose.yml" up --detach --wait
if ($LASTEXITCODE -ne 0) { throw "PostgreSQL did not become healthy." }
& $Python -m backend.db.create_tables
if ($LASTEXITCODE -ne 0) { throw "Database table creation failed." }
& $Python -m backend.db.seed
if ($LASTEXITCODE -ne 0) { throw "Database seed failed." }

$processIds = @()
$BackendUrl = "http://127.0.0.1:$AppPort"
$FrontendUrl = "http://127.0.0.1:$FrontendPort"
if (-not (Test-Http "$BackendUrl/api/health")) {
    $backend = Start-Process -FilePath $Python `
        -ArgumentList @("-m", "backend.main") `
        -WorkingDirectory $ProjectDir `
        -WindowStyle Hidden `
        -RedirectStandardOutput "$LogDir\backend.stdout.log" `
        -RedirectStandardError "$LogDir\backend.stderr.log" `
        -PassThru
    $processIds += $backend.Id
    if (-not (Wait-Http "$BackendUrl/api/health" 45)) {
        throw "Backend did not become healthy. Check logs/backend.stderr.log."
    }
}

if (-not (Test-Http $FrontendUrl)) {
    $env:PRICEWATCH_BACKEND_URL = $BackendUrl
    $env:NEXT_PUBLIC_PRICEWATCH_WS_URL = "ws://127.0.0.1:$AppPort/ws"
    $frontend = Start-Process -FilePath "npm.cmd" `
        -ArgumentList @("run", "dev", "--", "--port", "$FrontendPort") `
        -WorkingDirectory "$ProjectDir\frontend" `
        -WindowStyle Hidden `
        -RedirectStandardOutput "$LogDir\frontend.stdout.log" `
        -RedirectStandardError "$LogDir\frontend.stderr.log" `
        -PassThru
    $processIds += $frontend.Id
    if (-not (Wait-Http $FrontendUrl 90)) {
        throw "Dashboard did not become healthy. Check logs/frontend.stderr.log."
    }
}

if ($processIds.Count -gt 0) {
    [IO.File]::WriteAllLines($PidFile, [string[]]$processIds)
}
Write-Host "Dashboard: $FrontendUrl"
Write-Host "API docs: $BackendUrl/api/docs"
