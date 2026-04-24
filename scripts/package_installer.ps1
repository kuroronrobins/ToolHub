param(
    [string]$Version,
    [switch]$AllowMissingBundle
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ReleaseDir = Join-Path $Root "release"
$ManifestPath = Join-Path $ReleaseDir "manifest.json"
$DistDir = Join-Path $ReleaseDir "dist_installer"
$BundleDir = Join-Path $Root "launcher\src-tauri\target\release\bundle"

function Assert-InRoot {
    param([string]$Path)
    $Full = [System.IO.Path]::GetFullPath($Path)
    if (-not $Full.StartsWith($Root, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing path outside workspace: $Full"
    }
    return $Full
}

if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
    throw "release/manifest.json was not found."
}

$Manifest = Get-Content -Raw -Encoding UTF8 $ManifestPath | ConvertFrom-Json
if ([string]::IsNullOrWhiteSpace($Version)) {
    $Version = [string]$Manifest.toolhub.version
}
if ([string]::IsNullOrWhiteSpace($Version)) {
    throw "ToolHub version is missing."
}

New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

$InstallerName = "ToolHub_Setup_$Version.exe"
$InstallerPath = Join-Path $DistDir $InstallerName
$Candidates = @()

if (Test-Path -LiteralPath $BundleDir -PathType Container) {
    $Candidates += Get-ChildItem -Path $BundleDir -Recurse -File -Include "*.exe","*.msi" -ErrorAction SilentlyContinue
}

$NsisOrExe = $Candidates | Where-Object { $_.Extension -ieq ".exe" } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$Msi = $Candidates | Where-Object { $_.Extension -ieq ".msi" } | Sort-Object LastWriteTime -Descending | Select-Object -First 1

if ($NsisOrExe) {
    Copy-Item -LiteralPath $NsisOrExe.FullName -Destination $InstallerPath -Force
    Write-Host "Collected installer: $($NsisOrExe.FullName)"
} elseif ($Msi) {
    $MsiTarget = Join-Path $DistDir "ToolHub_Setup_$Version.msi"
    Copy-Item -LiteralPath $Msi.FullName -Destination $MsiTarget -Force
    Write-Host "Collected MSI installer: $($Msi.FullName)"
} elseif ($AllowMissingBundle) {
    Write-Host "[WARN] Tauri bundle output was not found. Leaving installer sha256 empty."
} else {
    throw "No Tauri bundle installer was found under $BundleDir. Run npm run tauri build first, or pass -AllowMissingBundle for manifest-only staging."
}

if (Test-Path -LiteralPath $InstallerPath -PathType Leaf) {
    $Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $InstallerPath).Hash.ToLowerInvariant()
    $Size = (Get-Item -LiteralPath $InstallerPath).Length
    $Manifest.toolhub.installer.file = $InstallerName
    $Manifest.toolhub.installer.sha256 = $Hash
    $Manifest.toolhub.installer.size = $Size
    Write-Host "Installer sha256: $Hash"
} else {
    $Manifest.toolhub.installer.file = $InstallerName
}

$Manifest | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 $ManifestPath
Write-Host "Updated release/manifest.json"

