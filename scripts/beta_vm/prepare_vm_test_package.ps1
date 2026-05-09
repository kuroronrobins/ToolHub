param(
    [switch]$DryRun,
    [string]$PackageRoot = "",
    [string]$RepoRoot = ""
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path
} else {
    $RepoRoot = (Resolve-Path $RepoRoot).Path
}
if ([string]::IsNullOrWhiteSpace($PackageRoot)) {
    $PackageRoot = Join-Path $ScriptDir "package\ToolHub_Beta_VM_Test"
}

$ResultsDir = Join-Path $ScriptDir "results"
$PackageRootFull = [System.IO.Path]::GetFullPath($PackageRoot)
$AllowedPackageBase = [System.IO.Path]::GetFullPath((Join-Path $ScriptDir "package")).TrimEnd("\")
if (-not $PackageRootFull.StartsWith($AllowedPackageBase, [System.StringComparison]::OrdinalIgnoreCase)) {
    Write-Error "PackageRoot must stay under scripts\beta_vm\package: $PackageRootFull"
    exit 1
}

function Write-Utf8NoBom {
    param([string]$Path, [string]$Content)
    $Encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $Encoding)
}

function To-RelativePath {
    param([string]$Path)
    $FullRoot = [System.IO.Path]::GetFullPath($RepoRoot).TrimEnd("\")
    $FullPath = [System.IO.Path]::GetFullPath($Path)
    if ($FullPath.StartsWith($FullRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $FullPath.Substring($FullRoot.Length).TrimStart("\").Replace("\", "/")
    }
    return $FullPath
}

function Fail-WithMessage {
    param([string]$Message)
    Write-Error $Message
    exit 1
}

New-Item -ItemType Directory -Force -Path $ResultsDir | Out-Null

$ReleaseManifestPath = Join-Path $RepoRoot "release\manifest.json"
$StagingManifestPath = Join-Path $RepoRoot "release\staging\installer_payload\staging_manifest.json"
$VmScriptPath = Join-Path $ScriptDir "vm_install_test.ps1"
$VmReadmeSourcePath = Join-Path $ScriptDir "VM_TEST_PACKAGE_README.md"

if (-not (Test-Path -LiteralPath $ReleaseManifestPath -PathType Leaf)) {
    Fail-WithMessage "release manifest not found: $ReleaseManifestPath"
}
if (-not (Test-Path -LiteralPath $StagingManifestPath -PathType Leaf)) {
    Fail-WithMessage "staging manifest not found: $StagingManifestPath"
}
if (-not (Test-Path -LiteralPath $VmScriptPath -PathType Leaf)) {
    Fail-WithMessage "VM install script not found: $VmScriptPath"
}
if (-not (Test-Path -LiteralPath $VmReadmeSourcePath -PathType Leaf)) {
    Fail-WithMessage "VM package README not found: $VmReadmeSourcePath"
}

$ReleaseManifest = Get-Content -Encoding UTF8 -Raw -LiteralPath $ReleaseManifestPath | ConvertFrom-Json
$InstallerFile = [string]$ReleaseManifest.toolhub.installer.file
$ExpectedSha256 = [string]$ReleaseManifest.toolhub.installer.sha256
$ExpectedSize = [int64]$ReleaseManifest.toolhub.installer.size
$InstallerPath = Join-Path (Join-Path $RepoRoot "release\dist_installer") $InstallerFile

if ([string]::IsNullOrWhiteSpace($InstallerFile) -or [string]::IsNullOrWhiteSpace($ExpectedSha256) -or $ExpectedSize -le 0) {
    Fail-WithMessage "release manifest installer metadata is incomplete"
}
if (-not (Test-Path -LiteralPath $InstallerPath -PathType Leaf)) {
    Fail-WithMessage "installer artifact not found: $InstallerPath"
}

$InstallerItem = Get-Item -LiteralPath $InstallerPath
$ActualSize = [int64]$InstallerItem.Length
$ActualSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $InstallerPath).Hash.ToLowerInvariant()
$ExpectedSha256Lower = $ExpectedSha256.ToLowerInvariant()
if ($ActualSize -ne $ExpectedSize) {
    Fail-WithMessage "installer size mismatch. expected=$ExpectedSize actual=$ActualSize"
}
if ($ActualSha256 -ne $ExpectedSha256Lower) {
    Fail-WithMessage "installer sha256 mismatch. expected=$ExpectedSha256Lower actual=$ActualSha256"
}

$PackageFiles = @(
    [ordered]@{
        source = $ReleaseManifestPath
        destination = Join-Path $PackageRootFull "release\manifest.json"
        role = "release_manifest"
    },
    [ordered]@{
        source = $InstallerPath
        destination = Join-Path (Join-Path $PackageRootFull "release\dist_installer") $InstallerFile
        role = "installer"
    },
    [ordered]@{
        source = $StagingManifestPath
        destination = Join-Path $PackageRootFull "release\staging\installer_payload\staging_manifest.json"
        role = "staging_manifest"
    },
    [ordered]@{
        source = $VmScriptPath
        destination = Join-Path $PackageRootFull "vm_install_test.ps1"
        role = "vm_install_script"
    },
    [ordered]@{
        source = $VmReadmeSourcePath
        destination = Join-Path $PackageRootFull "VM_TEST_PACKAGE_README.md"
        role = "package_readme"
    }
)

if (-not $DryRun) {
    foreach ($File in $PackageFiles) {
        $Parent = Split-Path -Parent $File.destination
        New-Item -ItemType Directory -Force -Path $Parent | Out-Null
        Copy-Item -LiteralPath $File.source -Destination $File.destination -Force
    }
    New-Item -ItemType Directory -Force -Path (Join-Path $PackageRootFull "results") | Out-Null
}

$PackageInstallerPath = Join-Path (Join-Path $PackageRootFull "release\dist_installer") $InstallerFile
$PackageManifestPath = Join-Path $PackageRootFull "release\manifest.json"
$PackageStagingManifestPath = Join-Path $PackageRootFull "release\staging\installer_payload\staging_manifest.json"
$PackageReadmePath = Join-Path $PackageRootFull "VM_TEST_PACKAGE_README.md"
$ChecksumsPath = Join-Path $PackageRootFull "checksums.json"
$ChecksumsTextPath = Join-Path $PackageRootFull "checksums.sha256.txt"
$SummaryJsonPath = Join-Path $PackageRootFull "package_summary.json"
$SummaryMarkdownPath = Join-Path $PackageRootFull "package_summary.md"

$PackageInstallerSha256 = ""
$PackageInstallerSize = 0
$PackageManifestSha256 = ""
$PackageStagingSha256 = ""
$PackageScriptSha256 = ""
if (-not $DryRun) {
    $PackageInstallerSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $PackageInstallerPath).Hash.ToLowerInvariant()
    $PackageInstallerSize = [int64](Get-Item -LiteralPath $PackageInstallerPath).Length
    $PackageManifestSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $PackageManifestPath).Hash.ToLowerInvariant()
    $PackageStagingSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $PackageStagingManifestPath).Hash.ToLowerInvariant()
    $PackageScriptSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $PackageRootFull "vm_install_test.ps1")).Hash.ToLowerInvariant()

    if ($PackageInstallerSha256 -ne $ExpectedSha256Lower -or $PackageInstallerSize -ne $ExpectedSize) {
        Fail-WithMessage "packaged installer does not match release manifest"
    }
}

$GeneratedAt = (Get-Date).ToString("o")
$PackageSummary = [ordered]@{
    schema_version = 1
    generated_at = $GeneratedAt
    dry_run = [bool]$DryRun
    repo_root = $RepoRoot
    package_root = $PackageRootFull
    installer = [ordered]@{
        file = $InstallerFile
        type = [string]$ReleaseManifest.toolhub.installer.type
        expected_sha256 = $ExpectedSha256Lower
        expected_size = $ExpectedSize
        source_path = To-RelativePath $InstallerPath
        packaged_path = if ($DryRun) { "" } else { $PackageInstallerPath }
        packaged_sha256 = $PackageInstallerSha256
        packaged_size = $PackageInstallerSize
    }
    release_manifest = [ordered]@{
        source_path = To-RelativePath $ReleaseManifestPath
        packaged_path = if ($DryRun) { "" } else { $PackageManifestPath }
        packaged_sha256 = $PackageManifestSha256
    }
    staging_manifest = [ordered]@{
        source_path = To-RelativePath $StagingManifestPath
        packaged_path = if ($DryRun) { "" } else { $PackageStagingManifestPath }
        packaged_sha256 = $PackageStagingSha256
    }
    package_files = @($PackageFiles | ForEach-Object {
        [ordered]@{
            role = $_.role
            source = To-RelativePath $_.source
            destination = if ($DryRun) { $_.destination } else { $_.destination }
        }
    })
    vm_command = "powershell -NoProfile -ExecutionPolicy Bypass -File .\vm_install_test.ps1 -SharedRoot . -ResultsDir .\results -PauseForManualGuiChecks"
    results_path = if ($DryRun) { Join-Path $PackageRootFull "results" } else { Join-Path $PackageRootFull "results" }
    notes = @(
        "Copy the whole ToolHub_Beta_VM_Test folder to a clean Windows VM.",
        "Do not install Python, Node.js, npm, Rust, cargo, Tauri CLI, or pip packages before testing.",
        "VM execution is still a manual step; this package creation does not prove installation."
    )
}

if (-not $DryRun) {
    $Checksums = [ordered]@{
        schema_version = 1
        generated_at = $GeneratedAt
        files = @(
            [ordered]@{ path = "release/manifest.json"; sha256 = $PackageManifestSha256 },
            [ordered]@{ path = "release/dist_installer/$InstallerFile"; sha256 = $PackageInstallerSha256; size = $PackageInstallerSize },
            [ordered]@{ path = "release/staging/installer_payload/staging_manifest.json"; sha256 = $PackageStagingSha256 },
            [ordered]@{ path = "vm_install_test.ps1"; sha256 = $PackageScriptSha256 }
        )
    }
    Write-Utf8NoBom -Path $ChecksumsPath -Content ($Checksums | ConvertTo-Json -Depth 6)
    $ChecksumLines = @(
        "$PackageInstallerSha256  release/dist_installer/$InstallerFile",
        "$PackageManifestSha256  release/manifest.json",
        "$PackageStagingSha256  release/staging/installer_payload/staging_manifest.json",
        "$PackageScriptSha256  vm_install_test.ps1"
    )
    Write-Utf8NoBom -Path $ChecksumsTextPath -Content ($ChecksumLines -join [Environment]::NewLine)
    Write-Utf8NoBom -Path $SummaryJsonPath -Content ($PackageSummary | ConvertTo-Json -Depth 8)

    $Markdown = @(
        "# ToolHub Beta VM Test Package Summary",
        "",
        ("- generated_at: {0}" -f $GeneratedAt),
        ("- package_root: {0}" -f $PackageRootFull),
        ("- installer: {0}" -f $InstallerFile),
        ("- installer_sha256: {0}" -f $PackageInstallerSha256),
        ("- installer_size: {0}" -f $PackageInstallerSize),
        "- vm_command: powershell -NoProfile -ExecutionPolicy Bypass -File .\vm_install_test.ps1 -SharedRoot . -ResultsDir .\results -PauseForManualGuiChecks",
        "",
        "VM execution has not been performed by this package step."
    )
    Write-Utf8NoBom -Path $SummaryMarkdownPath -Content ($Markdown -join [Environment]::NewLine)
}

$PackageSummary | ConvertTo-Json -Depth 8
