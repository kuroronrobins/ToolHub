param(
    [switch]$SkipInstall,
    [switch]$SkipBuild,
    [switch]$SkipAppPacks,
    [switch]$SkipRuntime,
    [switch]$SkipInstallerPackage,
    [switch]$SkipVerify,
    [switch]$AllowMissingBundle,
    [switch]$Strict,
    [switch]$RequireRuntime,
    [switch]$SignInstaller,
    [switch]$RequireInstallerSignature,
    [string]$CodeSignCertificateThumbprint,
    [string]$CodeSignCertificateSubject,
    [string]$CodeSignTimestampUrl,
    [string]$SignToolPath,
    [string[]]$SignToolExtraArgs = @()
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$LauncherDir = Join-Path $Root "launcher"

function Test-CommandAvailable {
    param(
        [string]$Name,
        [bool]$Required
    )
    if (Get-Command $Name -ErrorAction SilentlyContinue) {
        Write-Host "[OK] $Name is available"
        return $true
    }
    $Message = "$Name was not found."
    if ($Required) {
        Write-Host "[NG] $Message"
        throw $Message
    }
    Write-Host "[WARN] $Message"
    return $false
}

Write-Host "ToolHub release build started."
Write-Host "Root: $Root"

Write-Host ""
Write-Host "== 1. Environment preflight =="
$BuildRequired = -not $SkipBuild
Test-CommandAvailable -Name "node" -Required:$BuildRequired | Out-Null
Test-CommandAvailable -Name "npm" -Required:$BuildRequired | Out-Null
Test-CommandAvailable -Name "cargo" -Required:$BuildRequired | Out-Null
Test-CommandAvailable -Name "rustc" -Required:$BuildRequired | Out-Null

if (-not (Test-Path -LiteralPath (Join-Path $LauncherDir "package-lock.json") -PathType Leaf)) {
    if ($Strict) { throw "launcher/package-lock.json is required for reproducible release builds." }
    Write-Host "[WARN] launcher/package-lock.json is missing."
}
if (-not (Test-Path -LiteralPath (Join-Path $LauncherDir "src-tauri\Cargo.lock") -PathType Leaf)) {
    if ($Strict) { throw "launcher/src-tauri/Cargo.lock is required for reproducible release builds." }
    Write-Host "[WARN] launcher/src-tauri/Cargo.lock is missing."
}

if (-not $SkipAppPacks) {
    Write-Host ""
    Write-Host "== 2. Package App Packs =="
    & (Join-Path $Root "scripts\package_app_pack.ps1")
    if (-not $?) { exit 1 }
} else {
    Write-Host "[SKIP] App Pack packaging"
}

if (-not $SkipRuntime) {
    Write-Host ""
    Write-Host "== 3. Prepare Runtime =="
    $RuntimeArgs = @{}
    if (-not $RequireRuntime) { $RuntimeArgs.AllowMissingRuntime = $true }
    & (Join-Path $Root "scripts\prepare_runtime.ps1") @RuntimeArgs
    if (-not $?) { exit 1 }
} else {
    Write-Host "[SKIP] Runtime preparation"
}

if (-not $SkipBuild) {
    Write-Host ""
    Write-Host "== 4. Frontend install/build =="
    Push-Location $LauncherDir
    try {
        if (-not $SkipInstall) {
            if (Test-Path -LiteralPath "package-lock.json" -PathType Leaf) {
                Write-Host "Installing frontend dependencies with npm ci."
                & npm "ci"
            } else {
                Write-Host "Installing frontend dependencies with npm install."
                & npm "install"
            }
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        } else {
            Write-Host "[SKIP] npm dependency install"
        }

        Write-Host "Running Tauri release build."
        & npm "run" "tauri" "build"
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    finally {
        Pop-Location
    }
} else {
    Write-Host "[SKIP] Tauri build"
}

if (-not $SkipInstallerPackage) {
    Write-Host ""
    Write-Host "== 5. Package Installer Artifacts =="
    $InstallerArgs = @{}
    if ($AllowMissingBundle) { $InstallerArgs.AllowMissingBundle = $true }
    if ($SignInstaller) { $InstallerArgs.SignInstaller = $true }
    if (-not [string]::IsNullOrWhiteSpace($CodeSignCertificateThumbprint)) {
        $InstallerArgs.CodeSignCertificateThumbprint = $CodeSignCertificateThumbprint
    }
    if (-not [string]::IsNullOrWhiteSpace($CodeSignCertificateSubject)) {
        $InstallerArgs.CodeSignCertificateSubject = $CodeSignCertificateSubject
    }
    if (-not [string]::IsNullOrWhiteSpace($CodeSignTimestampUrl)) {
        $InstallerArgs.CodeSignTimestampUrl = $CodeSignTimestampUrl
    }
    if (-not [string]::IsNullOrWhiteSpace($SignToolPath)) {
        $InstallerArgs.SignToolPath = $SignToolPath
    }
    if (@($SignToolExtraArgs).Count -gt 0) {
        $InstallerArgs.SignToolExtraArgs = $SignToolExtraArgs
    }
    & (Join-Path $Root "scripts\package_installer.ps1") @InstallerArgs
    if (-not $?) { exit 1 }
} else {
    Write-Host "[SKIP] Installer packaging"
}

if (-not $SkipVerify) {
    Write-Host ""
    Write-Host "== 6. Verify Release =="
    $VerifyArgs = @{}
    if (-not $AllowMissingBundle) { $VerifyArgs.RequireInstaller = $true }
    if (-not $SkipAppPacks) { $VerifyArgs.RequireAppPacks = $true }
    if ($RequireRuntime) { $VerifyArgs.RequireRuntime = $true }
    if ($RequireInstallerSignature -or $SignInstaller) { $VerifyArgs.RequireInstallerSignature = $true }
    if ($Strict) { $VerifyArgs.Strict = $true }
    & (Join-Path $Root "scripts\verify_release.ps1") @VerifyArgs
    if (-not $?) { exit 1 }
} else {
    Write-Host "[SKIP] Release verification"
}

Write-Host ""
Write-Host "ToolHub release build flow completed."
exit 0
