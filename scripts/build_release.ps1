param(
    [switch]$SkipInstall,
    [switch]$SkipBuild,
    [switch]$SkipAppPacks,
    [switch]$SkipInstallerPackage,
    [switch]$SkipVerify,
    [switch]$AllowMissingBundle
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")

if (-not $SkipBuild -and -not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Error "npm was not found. Install Node.js first."
}
if (-not $SkipBuild -and -not (Get-Command cargo -ErrorAction SilentlyContinue)) {
    Write-Error "cargo was not found. Install Rust first."
}

if (-not $SkipAppPacks) {
    Write-Host "Packaging built-in app packs."
    & (Join-Path $Root "scripts\package_app_pack.ps1")
    if (-not $?) { exit 1 }
}

if (-not $SkipBuild) {
    Push-Location (Join-Path $Root "launcher")
    try {
        if (-not $SkipInstall -and -not (Test-Path "node_modules")) {
            Write-Host "Installing frontend dependencies."
            & npm "install"
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }
        Write-Host "Running Tauri release build."
        & npm "run" "tauri" "build"
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    finally {
        Pop-Location
    }
}

if (-not $SkipInstallerPackage) {
    Write-Host "Collecting installer artifacts."
    if ($AllowMissingBundle) {
        & (Join-Path $Root "scripts\package_installer.ps1") -AllowMissingBundle
    } else {
        & (Join-Path $Root "scripts\package_installer.ps1")
    }
    if (-not $?) { exit 1 }
}

if (-not $SkipVerify) {
    Write-Host "Verifying release artifacts."
    & (Join-Path $Root "scripts\verify_release.ps1")
    if (-not $?) { exit 1 }
}

exit 0
