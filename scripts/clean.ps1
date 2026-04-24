param(
    [switch]$IncludeLogs,
    [switch]$IncludeBuild
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")

Write-Host "Cleaning generated files."

Get-ChildItem -Path $Root -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $Root -Recurse -Directory -Filter ".pytest_cache" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

if ($IncludeBuild) {
    $BuildDirs = @(
        "launcher/dist",
        "launcher/src-tauri/target",
        "dist",
        "build"
    )
    foreach ($Dir in $BuildDirs) {
        $Path = Join-Path $Root $Dir
        if (Test-Path $Path) {
            Remove-Item -Path $Path -Recurse -Force
            Write-Host "Deleted: $Path"
        }
    }
}

if ($IncludeLogs) {
    $LogDir = Join-Path $Root "data/logs"
    if (Test-Path $LogDir) {
        Get-ChildItem -Path $LogDir -Recurse -File -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
        Write-Host "Log files deleted."
    }
}

Write-Host "Done."
