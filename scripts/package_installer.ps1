param(
    [string]$Version,
    [switch]$AllowMissingBundle
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

. (Join-Path $PSScriptRoot "utf8_no_bom.ps1")

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ReleaseDir = Join-Path $Root "release"
$ManifestPath = Join-Path $ReleaseDir "manifest.json"
$DistDir = Join-Path $ReleaseDir "dist_installer"
$StagingDir = Join-Path $ReleaseDir "staging\installer_payload"
$BundleDir = Join-Path $Root "launcher\src-tauri\target\release\bundle"

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

function Copy-ToStage {
    param(
        [string]$Source,
        [string]$RelativeDestination
    )
    $SourceFull = Assert-InRoot $Source
    if (-not (Test-Path -LiteralPath $SourceFull)) {
        throw "Staging source is missing: $SourceFull"
    }
    $Destination = Join-Path $StagingDir $RelativeDestination
    $DestinationParent = Split-Path -Parent $Destination
    New-Item -ItemType Directory -Force -Path $DestinationParent | Out-Null
    if (Test-Path -LiteralPath $SourceFull -PathType Container) {
        $ExcludedDirectories = @(
            ".git",
            "node_modules",
            "debug",
            "__pycache__",
            ".pytest_cache",
            "browser_profiles",
            "update_cache",
            "logs"
        )
        $ExcludedFiles = @(
            "*.pyc",
            "*.pyo",
            "*.tmp",
            "*.log"
        )
        New-Item -ItemType Directory -Force -Path $Destination | Out-Null
        & robocopy $SourceFull $Destination /E /XD $ExcludedDirectories /XF $ExcludedFiles /NFL /NDL /NJH /NJS /NP | Out-Null
        $RobocopyExitCode = $LASTEXITCODE
        if ($RobocopyExitCode -ge 8) {
            throw "robocopy failed while staging $SourceFull to $Destination. exit_code=$RobocopyExitCode"
        }
        $global:LASTEXITCODE = 0
    } else {
        Copy-Item -LiteralPath $SourceFull -Destination $Destination -Force
    }
}

function Remove-ExcludedFromStage {
    $ExcludedDirectories = @(
        ".git",
        "node_modules",
        "debug",
        "__pycache__",
        ".pytest_cache",
        "browser_profiles",
        "update_cache",
        "logs"
    )
    foreach ($Name in $ExcludedDirectories) {
        Get-ChildItem -LiteralPath $StagingDir -Recurse -Directory -Force -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -ieq $Name -or $_.FullName -match "\\target\\debug($|\\)" } |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    }
    Get-ChildItem -LiteralPath $StagingDir -Recurse -File -Force -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -like "*.pyc" -or
            $_.Name -like "*.pyo" -or
            $_.Name -like "*.tmp" -or
            $_.Name -like "*.log"
        } |
        Remove-Item -Force -ErrorAction SilentlyContinue
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
Reset-Directory $StagingDir

$StageItems = @(
    @{ Source = "runner"; Destination = "runner" },
    @{ Source = "apps"; Destination = "apps" },
    @{ Source = "runtime"; Destination = "runtime" },
    @{ Source = "config.default"; Destination = "config.default" },
    @{ Source = "updater"; Destination = "updater" },
    @{ Source = "installer"; Destination = "installer" },
    @{ Source = "tools\app_studio\main.py"; Destination = "tools\app_studio\main.py" },
    @{ Source = "tools\app_studio\app_studio"; Destination = "tools\app_studio\app_studio" },
    @{ Source = "tools\app_studio\assets"; Destination = "tools\app_studio\assets" },
    @{ Source = "README.md"; Destination = "README.md" },
    @{ Source = "release\manifest.json"; Destination = "release\manifest.json" },
    @{ Source = "release\app_manifest.json"; Destination = "release\app_manifest.json" }
)

foreach ($Item in $StageItems) {
    Copy-ToStage -Source (Join-Path $Root $Item.Source) -RelativeDestination $Item.Destination
    Write-Host "[OK] Staged $($Item.Source)"
}
Remove-ExcludedFromStage

$StagedFiles = Get-ChildItem -LiteralPath $StagingDir -Recurse -File -Force | ForEach-Object {
    $_.FullName.Substring($StagingDir.Length + 1).Replace("\", "/")
}
$StageManifest = [ordered]@{
    schema_version = 1
    toolhub_version = $Version
    created_by = "scripts/package_installer.ps1"
    files = @($StagedFiles)
}
Write-JsonUtf8NoBomFile -Path (Join-Path $StagingDir "staging_manifest.json") -InputObject $StageManifest -Depth 20

$Candidates = @()
if (Test-Path -LiteralPath $BundleDir -PathType Container) {
    $Candidates += Get-ChildItem -Path $BundleDir -Recurse -File -Include "*.exe","*.msi" -ErrorAction SilentlyContinue
}

$Exe = $Candidates | Where-Object { $_.Extension -ieq ".exe" } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$Msi = $Candidates | Where-Object { $_.Extension -ieq ".msi" } | Sort-Object LastWriteTime -Descending | Select-Object -First 1

$InstallerFileName = "ToolHub_Setup_$Version.exe"
$InstallerType = "nsis"
$InstallerPath = Join-Path $DistDir $InstallerFileName

if ($Exe) {
    Copy-Item -LiteralPath $Exe.FullName -Destination $InstallerPath -Force
    Write-Host "Collected NSIS/exe installer: $($Exe.FullName)"
} elseif ($Msi) {
    $InstallerFileName = "ToolHub_Setup_$Version.msi"
    $InstallerType = "msi"
    $InstallerPath = Join-Path $DistDir $InstallerFileName
    Copy-Item -LiteralPath $Msi.FullName -Destination $InstallerPath -Force
    Write-Host "Collected MSI installer: $($Msi.FullName)"
} elseif ($AllowMissingBundle) {
    Write-Host "[WARN] Tauri bundle output was not found. Staging was created and installer sha256 remains empty."
} else {
    throw "No Tauri bundle installer was found under $BundleDir. Run npm run tauri build first, or pass -AllowMissingBundle for staging-only packaging."
}

$Manifest.toolhub.installer.file = $InstallerFileName
$Manifest.toolhub.installer.type = $InstallerType

if (Test-Path -LiteralPath $InstallerPath -PathType Leaf) {
    $Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $InstallerPath).Hash.ToLowerInvariant()
    $Size = (Get-Item -LiteralPath $InstallerPath).Length
    $Manifest.toolhub.installer.sha256 = $Hash
    $Manifest.toolhub.installer.size = $Size
    Write-Host "Installer sha256: $Hash"
    Write-Host "Installer size: $Size"
} else {
    $Manifest.toolhub.installer.sha256 = ""
    $Manifest.toolhub.installer.size = $null
}

Write-JsonUtf8NoBomFile -Path $ManifestPath -InputObject $Manifest -Depth 20
$StagedManifestPath = Join-Path $StagingDir "release\manifest.json"
if (Test-Path -LiteralPath $StagedManifestPath -PathType Leaf) {
    Write-JsonUtf8NoBomFile -Path $StagedManifestPath -InputObject $Manifest -Depth 20
}
Write-Host "Updated release/manifest.json"
Write-Host "Installer staging completed: $StagingDir"
