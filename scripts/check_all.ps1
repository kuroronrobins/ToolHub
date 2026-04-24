param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Failed = $false

function Run-Step {
    param(
        [string]$Name,
        [scriptblock]$Script
    )
    Write-Host ""
    Write-Host "== $Name =="
    & $Script
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[NG] $Name failed with exit code $LASTEXITCODE"
        $script:Failed = $true
    } else {
        Write-Host "[OK] $Name"
    }
}

Push-Location $Root
try {
    Run-Step "Bootstrap environment check" {
        & $Python "main.py" "--check"
    }

    Run-Step "Python runner tests" {
        & $Python "-m" "unittest" "discover" "-s" "runner/tests"
    }

    if (Get-Command npm -ErrorAction SilentlyContinue) {
        if (Test-Path "launcher/node_modules") {
            Run-Step "TypeScript tests" {
                Push-Location "launcher"
                try { & npm "test" } finally { Pop-Location }
            }
            Run-Step "TypeScript build" {
                Push-Location "launcher"
                try { & npm "run" "build" } finally { Pop-Location }
            }
        } else {
            Write-Host ""
            Write-Host "[SKIP] TypeScript checks: launcher/node_modules is missing. Run npm install in launcher first."
        }
    } else {
        Write-Host ""
        Write-Host "[SKIP] TypeScript checks: npm was not found."
    }

    if (Get-Command cargo -ErrorAction SilentlyContinue) {
        Run-Step "Rust check" {
            Push-Location "launcher/src-tauri"
            try { & cargo "check" } finally { Pop-Location }
        }
    } else {
        Write-Host ""
        Write-Host "[SKIP] Rust check: cargo was not found."
    }
}
finally {
    Pop-Location
}

if ($Failed) {
    exit 1
}
exit 0
