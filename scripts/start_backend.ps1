<#
.SYNOPSIS
    Start the backend (the gateway: console API + live SSE stream + /metrics) on Windows.

.DESCRIPTION
    Same as `make gateway`, but needs no make and works from any folder:
      - uses the project's .venv Python (no need to activate it first);
      - trains the learned verifier once if runs/models/ has no model yet;
      - runs uvicorn against the offline environment (zero Kubernetes).
    Ctrl-C stops the server.

.EXAMPLE
    .\scripts\start_backend.ps1
.EXAMPLE
    .\scripts\start_backend.ps1 -Port 9000 -Reload
#>
param(
    [int]$Port = 8080,
    [string]$Config = "config/offline_eval.yaml",
    [switch]$Reload  # restart automatically when a file under src/ changes
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Repo ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Error "No .venv found at $Python. Create it first: python -m venv .venv; .\.venv\Scripts\pip install -e "".[dev]"""
}
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    Write-Error "Port $Port is already in use (is the backend already running?). Use -Port to pick another."
}

Push-Location $Repo
try {
    if (-not (Test-Path "runs\models\learned_verifier.joblib")) {
        Write-Host "No learned-verifier model yet -- training it once (make train)..."
        & $Python scripts\train_learned.py
        if ($LASTEXITCODE -ne 0) { throw "training failed" }
    }

    # Optional secrets file (gitignored), one KEY=value per line, e.g. ANTHROPIC_API_KEY=sk-ant-...
    if (Test-Path ".env") {
        foreach ($line in Get-Content ".env") {
            if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$' -and $line -notmatch '^\s*#') {
                Set-Item -Path "env:$($Matches[1])" -Value ($Matches[2].Trim('"', "'"))
            }
        }
        Write-Host "Loaded settings from .env"
    }
    if (-not $env:GROQ_API_KEY) {
        Write-Warning ("No GROQ_API_KEY set: the LLM-judge and Combined verifiers will BLOCK every " +
            "action (they fail closed). Envelope / Learned / Ungated work without a key. " +
            "Put GROQ_API_KEY=... in .env (free key: https://console.groq.com/keys).")
    }

    $env:SENTINEL_CONFIG = $Config
    $env:PYTHONPATH = Join-Path $Repo "src"
    $uvicornArgs = @("-m", "uvicorn", "sentinel.gateway.app:app", "--port", "$Port")
    if ($Reload) { $uvicornArgs += @("--reload", "--reload-dir", "src") }

    Write-Host ""
    Write-Host "  backend   http://localhost:$Port"
    Write-Host "  health    http://localhost:$Port/health"
    Write-Host "  API docs  http://localhost:$Port/docs"
    Write-Host "  config    $Config"
    Write-Host "  Ctrl-C to stop"
    Write-Host ""
    & $Python @uvicornArgs
}
finally {
    Pop-Location
}
