$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $repoRoot ".env"
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $envPath)) {
    throw "Missing .env. Run setup.ps1 first."
}
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Missing .venv. Run setup.ps1 first."
}

$settings = @{}
foreach ($line in Get-Content -LiteralPath $envPath) {
    $trimmed = $line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) {
        continue
    }
    $key, $value = $trimmed.Split("=", 2)
    $settings[$key.Trim()] = $value.Trim()
}

if (-not $settings.ContainsKey("API_KEY") -or -not $settings["API_KEY"]) {
    throw "API_KEY is missing from .env."
}

$apiPort = if ($settings.ContainsKey("APP_PORT")) { $settings["APP_PORT"] } else { "8000" }
if ($apiPort -notmatch "^\d{1,5}$" -or [int]$apiPort -lt 1 -or [int]$apiPort -gt 65535) {
    throw "APP_PORT in .env is invalid."
}

$env:PRICEWATCH_API_KEY = $settings["API_KEY"]
$env:PRICEWATCH_API_URL = "http://127.0.0.1:$apiPort"

& $pythonPath -m mcp_server.server
exit $LASTEXITCODE
