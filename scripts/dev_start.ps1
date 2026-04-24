param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")

Write-Host "Starting ToolHub in development mode."
Push-Location $Root
try {
    & $Python "main.py" "--dev"
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
