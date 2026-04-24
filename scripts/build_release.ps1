param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Error "npm was not found. Install Node.js first."
}
if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
    Write-Error "cargo was not found. Install Rust first."
}

Push-Location (Join-Path $Root "launcher")
try {
    if (-not $SkipInstall -and -not (Test-Path "node_modules")) {
        Write-Host "Installing frontend dependencies."
        & npm "install"
    }
    Write-Host "Running Tauri release build."
    & npm "run" "tauri" "build"
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
