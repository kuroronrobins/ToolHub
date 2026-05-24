param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")

Write-Host "Starting ToolHub from the development source."
Push-Location $Root
try {
    & $Python "main.py"
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
