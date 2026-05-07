param(
    [switch]$RunValidation,
    [switch]$RunCheckAll
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$AppId = "delete_rehearsal_app"
$Version = "0.1.0"
$AppsDir = Join-Path $Root "apps"
$ReleaseDir = Join-Path $Root "release"
$ManifestPath = Join-Path $ReleaseDir "app_manifest.json"
$AppDir = Join-Path $AppsDir $AppId
$AppPackPath = Join-Path (Join-Path $ReleaseDir "app_packs") "$AppId-$Version.zip"
$StrictStagingDir = Join-Path (Join-Path $ReleaseDir "staging") $AppId
$StrictVersionStaging = Join-Path (Join-Path $ReleaseDir "staging") "$AppId-$Version"
$AmbiguousStagingDir = Join-Path (Join-Path $ReleaseDir "staging") "${AppId}_other"
$RuntimeAppEnv = Join-Path (Join-Path (Join-Path $Root "runtime") "app_envs") $AppId
$BackupStampDir = Join-Path (Join-Path (Join-Path $Root "backups") "app_studio") "20990101_000000_delete_rehearsal"
$BackupDir = Join-Path $BackupStampDir $AppId
$LifecycleBackupStampDir = Join-Path (Join-Path (Join-Path $Root "backups") "app_lifecycle") "20990101_000000_delete_rehearsal"
$LifecycleBackupDir = Join-Path $LifecycleBackupStampDir $AppId

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )
    if (-not $Condition) {
        throw $Message
    }
    Write-Host "[OK] $Message"
}

function Write-TextFile {
    param(
        [string]$Path,
        [string]$Text
    )
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path) | Out-Null
    [System.IO.File]::WriteAllText($Path, $Text, [System.Text.UTF8Encoding]::new($false))
}

function Remove-TestPath {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return }
    $Full = [System.IO.Path]::GetFullPath($Path)
    if (-not $Full.StartsWith($Root, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clean path outside repository: $Full"
    }
    if (Test-Path -LiteralPath $Full) {
        Remove-Item -LiteralPath $Full -Recurse -Force
    }
}

function Invoke-ValidationCommand {
    param(
        [string]$Label,
        [scriptblock]$Command
    )
    Write-Host ""
    Write-Host "== $Label =="
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE"
    }
}

foreach ($Path in @($AppDir, $AppPackPath, $StrictStagingDir, $StrictVersionStaging, $AmbiguousStagingDir, $RuntimeAppEnv, $BackupStampDir, $LifecycleBackupStampDir)) {
    if (Test-Path -LiteralPath $Path) {
        throw "Rehearsal path already exists; refusing to overwrite: $Path"
    }
}

$OriginalManifestBytes = [System.IO.File]::ReadAllBytes($ManifestPath)
$OriginalManifest = [System.Text.Encoding]::UTF8.GetString($OriginalManifestBytes)

try {
    Write-TextFile -Path (Join-Path $AppDir "app.yaml") -Text @"
id: $AppId
name: Delete Rehearsal App
admin:
  version: $Version
runtime:
  required_runtime: python-embedded-toolhub-001
build:
  source_entry: C:\External\ToolHubDeleteRehearsal\main.py
  output_mirror: C:\External\ToolHubDeleteRehearsal\ToolHub_AppStudio_Output\$AppId
"@
    Write-TextFile -Path (Join-Path $AppDir "README.md") -Text "delete rehearsal only"
    Write-TextFile -Path (Join-Path $AppDir "requirements.txt") -Text ""
    Write-TextFile -Path $AppPackPath -Text "placeholder zip path for delete rehearsal"
    Write-TextFile -Path (Join-Path $StrictStagingDir "artifact.txt") -Text "strict"
    Write-TextFile -Path (Join-Path $StrictVersionStaging "artifact.txt") -Text "strict version"
    Write-TextFile -Path (Join-Path $AmbiguousStagingDir "artifact.txt") -Text "ambiguous"
    Write-TextFile -Path (Join-Path $RuntimeAppEnv "marker.txt") -Text "runtime"
    Write-TextFile -Path (Join-Path $BackupDir "marker.txt") -Text "backup"
    Write-TextFile -Path (Join-Path $LifecycleBackupDir "marker.txt") -Text "legacy backup"

    $Manifest = $OriginalManifest | ConvertFrom-Json
    if ($Manifest.apps.PSObject.Properties[$AppId]) {
        throw "Manifest already contains rehearsal app id: $AppId"
    }
    $Manifest.apps | Add-Member -NotePropertyName $AppId -NotePropertyValue ([pscustomobject]@{
        version = $Version
        package = "app_packs/$AppId-$Version.zip"
        sha256 = ""
        required_core = ">=0.1.0"
        required_runner = ">=0.1.0"
        required_runtime = "python-embedded-toolhub-001"
        enabled = $false
    })
    [System.IO.File]::WriteAllText($ManifestPath, ($Manifest | ConvertTo-Json -Depth 20), [System.Text.UTF8Encoding]::new($false))

    $PlanJson = (& (Join-Path $PSScriptRoot "plan_app_delete.ps1") -AppId $AppId -DryRun -Json) | Out-String
    $Plan = $PlanJson | ConvertFrom-Json
    $DeleteTargets = @($Plan.delete_targets)
    $ExcludedTargets = @($Plan.excluded_targets)
    $DeletePaths = @($DeleteTargets | ForEach-Object { [string]$_.path })
    $ExcludedPaths = @($ExcludedTargets | ForEach-Object { [string]$_.path })

    Assert-True ($DeletePaths -contains $AppDir) "source dir would be deleted by future full-delete"
    Assert-True (@($DeleteTargets | Where-Object { $_.action -eq "remove app_manifest entry" -and $_.path -eq $ManifestPath }).Count -eq 1) "manifest target is entry removal, not manifest file deletion"
    Assert-True ($DeletePaths -contains $AppPackPath) "App Pack zip would be deleted by future full-delete"
    Assert-True ($DeletePaths -contains $StrictStagingDir) "strict staging dir would be deleted by future full-delete"
    Assert-True ($DeletePaths -contains $StrictVersionStaging) "versioned staging dir would be deleted by future full-delete"
    Assert-True ($DeletePaths -contains $RuntimeAppEnv) "runtime app_env would be deleted by future full-delete"
    Assert-True ($DeletePaths -contains $BackupDir) "App Studio backup would be deleted by future full-delete"
    Assert-True ($DeletePaths -contains $LifecycleBackupDir) "legacy lifecycle backup would be deleted by future full-delete"
    Assert-True ($DeletePaths -notcontains $AmbiguousStagingDir) "ambiguous staging candidate is not a delete target"
    Assert-True ($ExcludedPaths -contains $AmbiguousStagingDir) "ambiguous staging candidate is excluded"
    Assert-True (@($ExcludedTargets | Where-Object { $_.category -eq "external_reference" -and $_.delete_allowed -eq $false }).Count -ge 2) "external references are excluded"
    Assert-True (@($ExcludedTargets | Where-Object { $_.category -eq "user_data" -and $_.delete_allowed -eq $false }).Count -ge 1) "user data is excluded"
    Assert-True (@($ExcludedTargets | Where-Object { $_.category -eq "shared_runtime" -and $_.delete_allowed -eq $false }).Count -ge 2) "shared runtime is excluded"
    Assert-True (@($Plan.staging_candidate_paths).Count -eq 1) "staging candidate is reported separately"
    Assert-True (@($DeleteTargets | Where-Object { [string]::IsNullOrWhiteSpace([string]$_.normalized_path) -or [string]::IsNullOrWhiteSpace([string]$_.comparison_key) }).Count -eq 0) "delete targets have comparison fields"
    Assert-True (@($ExcludedTargets | Where-Object { [string]::IsNullOrWhiteSpace([string]$_.normalized_path) -or [string]::IsNullOrWhiteSpace([string]$_.comparison_key) }).Count -eq 0) "excluded targets have comparison fields"
}
finally {
    [System.IO.File]::WriteAllBytes($ManifestPath, $OriginalManifestBytes)
    foreach ($Path in @($AppDir, $AppPackPath, $StrictStagingDir, $StrictVersionStaging, $AmbiguousStagingDir, $RuntimeAppEnv, $BackupStampDir, $LifecycleBackupStampDir)) {
        Remove-TestPath $Path
    }
}

Write-Host "Delete rehearsal completed. No files were deleted by a full-delete command."

if ($RunValidation -or $RunCheckAll) {
    Invoke-ValidationCommand "rebuild_app_manifest.ps1 -DryRun" { & (Join-Path $PSScriptRoot "rebuild_app_manifest.ps1") -DryRun }
    Invoke-ValidationCommand "diagnose_app_manifest.ps1" { & (Join-Path $PSScriptRoot "diagnose_app_manifest.ps1") }
    Invoke-ValidationCommand "verify_release.ps1" { & (Join-Path $PSScriptRoot "verify_release.ps1") }
}

if ($RunCheckAll) {
    Invoke-ValidationCommand "check_all.ps1" { & (Join-Path $PSScriptRoot "check_all.ps1") }
}
