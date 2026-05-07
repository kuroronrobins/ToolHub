param(
    [string[]]$AppId,
    [switch]$NoManifestUpdate
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ReleaseDir = Join-Path $Root "release"
$AppManifestPath = Join-Path $ReleaseDir "app_manifest.json"
$AppPacksDir = Join-Path $ReleaseDir "app_packs"
$StageRoot = Join-Path $ReleaseDir "staging\app_pack_build"

function Assert-InRoot {
    param([string]$Path)
    $Full = [System.IO.Path]::GetFullPath($Path)
    if (-not $Full.StartsWith($Root, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing path outside workspace: $Full"
    }
    return $Full
}

function Reset-Directory {
    param([string]$Path)
    $Full = Assert-InRoot $Path
    if (Test-Path -LiteralPath $Full) {
        Remove-Item -LiteralPath $Full -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $Full | Out-Null
}

function Require-File {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Required file is missing: $Path"
    }
}

function Entry-Enabled {
    param([object]$Entry)
    if ($null -eq $Entry.PSObject.Properties["enabled"]) {
        return $true
    }
    return [bool]$Entry.enabled
}

if (-not (Test-Path -LiteralPath $AppManifestPath -PathType Leaf)) {
    throw "release/app_manifest.json was not found."
}

$AppManifest = Get-Content -Raw -Encoding UTF8 $AppManifestPath | ConvertFrom-Json
$KnownAppIds = @($AppManifest.apps.PSObject.Properties.Name)
$ExplicitTargets = $AppId -and $AppId.Count -gt 0
$TargetAppIds = if ($ExplicitTargets) { $AppId } else { $KnownAppIds }

New-Item -ItemType Directory -Force -Path $AppPacksDir | Out-Null
Reset-Directory $StageRoot

foreach ($Id in $TargetAppIds) {
    if ($KnownAppIds -notcontains $Id) {
        throw "App is not listed in release/app_manifest.json: $Id"
    }

    $AppDir = Join-Path (Join-Path $Root "apps") $Id
    $AppYaml = Join-Path $AppDir "app.yaml"
    $Entry = $AppManifest.apps.$Id
    $Enabled = Entry-Enabled $Entry
    if (-not (Test-Path -LiteralPath $AppYaml -PathType Leaf)) {
        if (-not $ExplicitTargets -and -not $Enabled) {
            Write-Host "[SKIP] $Id is enabled=false and apps/<app_id>/app.yaml is missing; treating it as a stale manifest entry."
            continue
        }
        throw "App source is missing for $Id (enabled=$Enabled): $AppYaml"
    }

    Require-File (Join-Path $AppDir "README.md")
    Require-File (Join-Path $AppDir "requirements.txt")
    Require-File (Join-Path $AppDir "icon.svg")

    $Version = [string]$Entry.version
    if ([string]::IsNullOrWhiteSpace($Version)) {
        throw "Version is missing in app_manifest.json for $Id"
    }

    $PackageRelative = "app_packs/$Id-$Version.zip"
    $PackagePath = Join-Path $ReleaseDir $PackageRelative
    $StageAppDir = Join-Path $StageRoot $Id

    Copy-Item -LiteralPath $AppDir -Destination $StageAppDir -Recurse -Force

    Get-ChildItem -Path $StageAppDir -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path $StageAppDir -Recurse -File -Include "*.pyc","*.pyo" -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction SilentlyContinue

    $PackMetadata = [ordered]@{
        schema_version = 1
        app_id = $Id
        version = $Version
        required_core = $Entry.required_core
        required_runner = $Entry.required_runner
        required_runtime = $Entry.required_runtime
        package_sha256 = ""
    }
    $PackMetadataPath = Join-Path $StageAppDir "pack_manifest.json"
    $PackMetadata | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 $PackMetadataPath

    if (Test-Path -LiteralPath $PackagePath) {
        Remove-Item -LiteralPath (Assert-InRoot $PackagePath) -Force
    }
    Compress-Archive -Path $StageAppDir -DestinationPath $PackagePath -Force

    $Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $PackagePath).Hash.ToLowerInvariant()
    $Size = (Get-Item -LiteralPath $PackagePath).Length

    $Entry.package = $PackageRelative
    $Entry.sha256 = $Hash

    Write-Host "Packaged $Id $Version -> $PackageRelative"
    Write-Host "  sha256: $Hash"
    Write-Host "  size: $Size"
}

if (-not $NoManifestUpdate) {
    $AppManifest | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 $AppManifestPath
    Write-Host "Updated release/app_manifest.json"
}

