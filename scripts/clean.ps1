param(
    [switch]$IncludeLogs,
    [switch]$IncludeBuild,
    [switch]$IncludeRelease,
    [switch]$IncludeUpdateCache,
    [switch]$IncludeTemp,
    [switch]$IncludeRuntimeGenerated
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

if ($IncludeRelease) {
    $ReleasePaths = @(
        "release/staging",
        "release/dist_installer",
        "release/app_packs"
    )
    foreach ($Dir in $ReleasePaths) {
        $Path = Join-Path $Root $Dir
        if (Test-Path $Path) {
            Remove-Item -Path $Path -Recurse -Force -ErrorAction SilentlyContinue
        }
        New-Item -ItemType Directory -Force -Path $Path | Out-Null
        New-Item -ItemType File -Force -Path (Join-Path $Path ".gitkeep") | Out-Null
        Write-Host "Reset: $Path"
    }
}

if ($IncludeLogs) {
    $LogDir = Join-Path $Root "data/logs"
    if (Test-Path $LogDir) {
        Get-ChildItem -Path $LogDir -Recurse -File -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
        Write-Host "Log files deleted."
    }
}

if ($IncludeUpdateCache) {
    $CacheDir = Join-Path $Root "data/update_cache"
    if (Test-Path $CacheDir) {
        Remove-Item -Path $CacheDir -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "Update cache deleted."
    }
}

if ($IncludeTemp) {
    $TempPaths = @(
        "temp",
        "tmp",
        "release/temp"
    )
    foreach ($Dir in $TempPaths) {
        $Path = Join-Path $Root $Dir
        if (Test-Path $Path) {
            Remove-Item -Path $Path -Recurse -Force -ErrorAction SilentlyContinue
            Write-Host "Temp deleted: $Path"
        }
    }
}

if ($IncludeRuntimeGenerated) {
    $RuntimeGenerated = @(
        "runtime/python",
        "runtime/app_envs",
        "runtime/web_automation_runtime"
    )
    foreach ($Dir in $RuntimeGenerated) {
        $Path = Join-Path $Root $Dir
        if (Test-Path $Path) {
            Remove-Item -Path $Path -Recurse -Force -ErrorAction SilentlyContinue
        }
        New-Item -ItemType Directory -Force -Path $Path | Out-Null
        New-Item -ItemType File -Force -Path (Join-Path $Path ".gitkeep") | Out-Null
        Write-Host "Reset runtime generated directory: $Path"
    }
}

Write-Host "Done."
