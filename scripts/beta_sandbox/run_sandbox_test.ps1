param(
    [switch]$DryRun,
    [switch]$RequireSandbox,
    [string]$WsbPath = "",
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

if ([string]::IsNullOrWhiteSpace($WsbPath)) {
    $WsbPath = Join-Path $ScriptDir "ToolHub_Beta_Install_Test.wsb"
}
$WsbPath = (Resolve-Path $WsbPath).Path

$ResultsDir = Join-Path $ScriptDir "results"
$ManifestPath = Join-Path $RepoRoot "release\manifest.json"
$DistInstallerDir = Join-Path $RepoRoot "release\dist_installer"
$StagingManifestPath = Join-Path $RepoRoot "release\staging\installer_payload\staging_manifest.json"

function Get-WindowsSandboxAvailability {
    $Command = Get-Command "WindowsSandbox.exe" -ErrorAction SilentlyContinue
    if ($null -eq $Command) {
        $Command = Get-Command "WindowsSandbox" -ErrorAction SilentlyContinue
    }

    $FeatureStatus = "unknown"
    $FeatureMessage = ""
    try {
        $Feature = Get-WindowsOptionalFeature -Online -FeatureName "Containers-DisposableClientVM" -ErrorAction Stop
        $FeatureStatus = [string]$Feature.State
    } catch {
        $FeatureMessage = $_.Exception.Message
    }

    [ordered]@{
        command_available = ($null -ne $Command)
        command_path = if ($null -ne $Command) { $Command.Source } else { "" }
        feature_status = $FeatureStatus
        feature_message = $FeatureMessage
        can_launch = (($null -ne $Command) -and ($FeatureStatus -in @("Enabled", "unknown")))
    }
}

function Fail-WithMessage {
    param([string]$Message)
    Write-Error $Message
    exit 1
}

New-Item -ItemType Directory -Force -Path $ResultsDir | Out-Null

if (-not (Test-Path -LiteralPath $ManifestPath)) {
    Fail-WithMessage "release manifest not found: $ManifestPath"
}
if (-not (Test-Path -LiteralPath $StagingManifestPath)) {
    Fail-WithMessage "staging manifest not found: $StagingManifestPath"
}

$Manifest = Get-Content -Encoding UTF8 -Raw -LiteralPath $ManifestPath | ConvertFrom-Json
$InstallerFile = [string]$Manifest.toolhub.installer.file
$ExpectedSha256 = [string]$Manifest.toolhub.installer.sha256
$ExpectedSize = [int64]$Manifest.toolhub.installer.size
$InstallerPath = Join-Path $DistInstallerDir $InstallerFile

if (-not (Test-Path -LiteralPath $InstallerPath)) {
    Fail-WithMessage "installer artifact not found: $InstallerPath"
}

$InstallerItem = Get-Item -LiteralPath $InstallerPath
$ActualSize = [int64]$InstallerItem.Length
$ActualSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $InstallerPath).Hash.ToLowerInvariant()
$SizeMatches = ($ActualSize -eq $ExpectedSize)
$ShaMatches = ($ActualSha256 -eq $ExpectedSha256.ToLowerInvariant())
if (-not $SizeMatches -or -not $ShaMatches) {
    Fail-WithMessage "installer artifact does not match release manifest. expected sha256=$ExpectedSha256 size=$ExpectedSize actual sha256=$ActualSha256 size=$ActualSize"
}

$WsbXml = [xml](Get-Content -Encoding UTF8 -Raw -LiteralPath $WsbPath)
$MappedFolders = @($WsbXml.Configuration.MappedFolders.MappedFolder)
$RepoMap = $MappedFolders | Where-Object { $_.SandboxFolder -eq "C:\ToolHubRepo" } | Select-Object -First 1
$ResultsMap = $MappedFolders | Where-Object { $_.SandboxFolder -eq "C:\ToolHubBetaResults" } | Select-Object -First 1

if ($null -eq $RepoMap) {
    Fail-WithMessage "WSB does not map C:\ToolHubRepo"
}
if ($null -eq $ResultsMap) {
    Fail-WithMessage "WSB does not map C:\ToolHubBetaResults"
}

$MappedRepoRoot = [System.IO.Path]::GetFullPath([string]$RepoMap.HostFolder).TrimEnd("\")
$ActualRepoRoot = [System.IO.Path]::GetFullPath($RepoRoot).TrimEnd("\")
$MappedResultsDir = [System.IO.Path]::GetFullPath([string]$ResultsMap.HostFolder).TrimEnd("\")
$ActualResultsDir = [System.IO.Path]::GetFullPath($ResultsDir).TrimEnd("\")

if (-not $MappedRepoRoot.Equals($ActualRepoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    Fail-WithMessage "WSB repo HostFolder does not match this checkout. WSB=$MappedRepoRoot repo=$ActualRepoRoot"
}
if (-not $MappedResultsDir.Equals($ActualResultsDir, [System.StringComparison]::OrdinalIgnoreCase)) {
    Fail-WithMessage "WSB results HostFolder does not match this checkout. WSB=$MappedResultsDir results=$ActualResultsDir"
}
if ([string]$RepoMap.ReadOnly -ne "true") {
    Fail-WithMessage "WSB repo mount must be read-only"
}
if ([string]$ResultsMap.ReadOnly -ne "false") {
    Fail-WithMessage "WSB results mount must be writable"
}

$Availability = Get-WindowsSandboxAvailability

$Summary = [ordered]@{
    dry_run = [bool]$DryRun
    repo_root = $RepoRoot
    wsb_path = $WsbPath
    results_dir = $ResultsDir
    installer_path = $InstallerPath
    installer_size = $ActualSize
    installer_sha256 = $ActualSha256
    staging_manifest_path = $StagingManifestPath
    windows_sandbox = $Availability
}

$Summary | ConvertTo-Json -Depth 6

if ($RequireSandbox -and -not [bool]$Availability.can_launch) {
    Fail-WithMessage "Windows Sandbox is not available. Enable the Windows Sandbox optional feature or run this validation in a Hyper-V VM / clean Windows user profile."
}

if ($DryRun) {
    Write-Host "Dry run only. No Sandbox was launched."
    exit 0
}

if (-not [bool]$Availability.command_available) {
    Fail-WithMessage "WindowsSandbox.exe was not found. Enable Windows Sandbox or use a clean VM/user profile."
}

Write-Host "Launching Windows Sandbox with $WsbPath"
Start-Process -FilePath $Availability.command_path -ArgumentList @($WsbPath)
