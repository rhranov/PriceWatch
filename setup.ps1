$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Definition

foreach ($command in @("docker", "py", "node", "npm")) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "Required command '$command' is not installed. See README.md for prerequisites."
    }
}
$nodeMajor = [int]((& node --version).TrimStart("v").Split(".")[0])
if ($nodeMajor -lt 20) {
    throw "Node.js 20 or newer is required. Found $(& node --version)."
}
& docker compose version | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Docker Compose is not available. Install or update Docker Desktop." }

Set-Location -LiteralPath $ProjectDir
if (-not (Test-Path -LiteralPath "$ProjectDir\.venv")) {
    & py -3.12 -m venv "$ProjectDir\.venv"
}
& "$ProjectDir\.venv\Scripts\python.exe" -m pip install --require-hashes --requirement "$ProjectDir\requirements.lock"
& "$ProjectDir\.venv\Scripts\python.exe" -m playwright install chromium
if ($LASTEXITCODE -ne 0) { throw "Playwright Chromium installation failed." }

Push-Location "$ProjectDir\frontend"
try {
    & npm.cmd ci
} finally {
    Pop-Location
}

if (-not (Test-Path -LiteralPath "$ProjectDir\.env")) {
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $apiBytes = New-Object byte[] 32
        $dbBytes = New-Object byte[] 24
        $rng.GetBytes($apiBytes)
        $rng.GetBytes($dbBytes)
    } finally {
        $rng.Dispose()
    }
    $apiKey = [Convert]::ToBase64String($apiBytes).Replace("=","").Replace("+","-").Replace("/","_")
    $dbPassword = [Convert]::ToBase64String($dbBytes).Replace("=","").Replace("+","-").Replace("/","_")
    $environment = (Get-Content -Raw -LiteralPath "$ProjectDir\.env.example").
        Replace("__API_KEY__", $apiKey).
        Replace("__DB_PASSWORD__", $dbPassword)
    [IO.File]::WriteAllText("$ProjectDir\.env", $environment, [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText(
        "$ProjectDir\frontend\.env.local",
        "PRICEWATCH_API_KEY=$apiKey`n",
        [Text.UTF8Encoding]::new($false)
    )
    Write-Host "Created .env and frontend/.env.local with random local credentials."
}

Write-Host "Setup complete. Start Docker Desktop, then run the start command from README.md."
