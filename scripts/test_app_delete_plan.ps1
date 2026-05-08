param()

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

. (Join-Path $PSScriptRoot "utf8_no_bom.ps1")

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$AppId = "deleteplan_probe"
$Version = "0.1.0"
$AppsDir = Join-Path $Root "apps"
$ReleaseDir = Join-Path $Root "release"
$ManifestPath = Join-Path $ReleaseDir "app_manifest.json"
$AppDir = Join-Path $AppsDir $AppId
$StrictStagingDir = Join-Path (Join-Path $ReleaseDir "staging") $AppId
$StrictVersionStaging = Join-Path (Join-Path $ReleaseDir "staging") "$AppId-$Version"
$AmbiguousStagingDir = Join-Path (Join-Path $ReleaseDir "staging") "${AppId}_other"
$AppPackPath = Join-Path (Join-Path $ReleaseDir "app_packs") "$AppId-$Version.zip"
$RuntimeAppEnv = Join-Path (Join-Path (Join-Path $Root "runtime") "app_envs") $AppId
$BackupStampDir = Join-Path (Join-Path (Join-Path $Root "backups") "app_studio") "20990101_000000_delete_plan_test"
$BackupDir = Join-Path $BackupStampDir $AppId

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

foreach ($Path in @($AppDir, $StrictStagingDir, $StrictVersionStaging, $AmbiguousStagingDir, $AppPackPath, $RuntimeAppEnv, $BackupStampDir)) {
    if (Test-Path -LiteralPath $Path) {
        throw "Test path already exists; refusing to overwrite: $Path"
    }
}

$OriginalManifestBytes = [System.IO.File]::ReadAllBytes($ManifestPath)
$OriginalManifest = [System.Text.Encoding]::UTF8.GetString($OriginalManifestBytes)

try {
    New-Item -ItemType Directory -Force -Path $AppDir | Out-Null
    @"
id: $AppId
name: Delete Plan Probe
admin:
  version: $Version
runtime:
  required_runtime: python-embedded-toolhub-001
build:
  source_entry: C:\External\ToolHubProbe\main.py
  output_mirror: C:\External\ToolHubProbe\ToolHub_AppStudio_Output\$AppId
"@ | Set-Content -Encoding UTF8 (Join-Path $AppDir "app.yaml")
    "probe" | Set-Content -Encoding UTF8 (Join-Path $AppDir "README.md")
    "" | Set-Content -Encoding UTF8 (Join-Path $AppDir "requirements.txt")

    New-Item -ItemType Directory -Force -Path $StrictStagingDir | Out-Null
    "strict" | Set-Content -Encoding UTF8 (Join-Path $StrictStagingDir "artifact.txt")
    New-Item -ItemType Directory -Force -Path $StrictVersionStaging | Out-Null
    "strict version" | Set-Content -Encoding UTF8 (Join-Path $StrictVersionStaging "artifact.txt")
    New-Item -ItemType Directory -Force -Path $AmbiguousStagingDir | Out-Null
    "ambiguous" | Set-Content -Encoding UTF8 (Join-Path $AmbiguousStagingDir "artifact.txt")
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $AppPackPath) | Out-Null
    "placeholder zip path for delete plan test" | Set-Content -Encoding UTF8 $AppPackPath
    New-Item -ItemType Directory -Force -Path $RuntimeAppEnv | Out-Null
    "runtime marker" | Set-Content -Encoding UTF8 (Join-Path $RuntimeAppEnv "marker.txt")
    New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
    "backup marker" | Set-Content -Encoding UTF8 (Join-Path $BackupDir "marker.txt")

    $Manifest = $OriginalManifest | ConvertFrom-Json
    if ($Manifest.apps.PSObject.Properties[$AppId]) {
        throw "Manifest already contains test app id: $AppId"
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
    Write-JsonUtf8NoBomFile -Path $ManifestPath -InputObject $Manifest -Depth 20

    $PlanJson = (& (Join-Path $PSScriptRoot "plan_app_delete.ps1") -AppId $AppId -DryRun -Json) | Out-String
    $Plan = $PlanJson | ConvertFrom-Json
    $DeleteTargets = @($Plan.delete_targets)
    $ExcludedTargets = @($Plan.excluded_targets)
    $DeletePaths = @($DeleteTargets | ForEach-Object { [string]$_.path })
    $ExcludedPaths = @($ExcludedTargets | ForEach-Object { [string]$_.path })

    Assert-True ($DeletePaths -contains $AppDir) "source dir is a delete target"
    $ManifestEntryTargets = @($DeleteTargets | Where-Object { $_.action -eq "remove app_manifest entry" -and ([string]$_.path).EndsWith("release\app_manifest.json", [System.StringComparison]::OrdinalIgnoreCase) })
    Assert-True ($ManifestEntryTargets.Count -eq 1) "manifest is represented as entry removal"
    Assert-True ($DeletePaths -contains $AppPackPath) "App Pack path is a delete target"
    Assert-True ($DeletePaths -contains $StrictStagingDir) "exact staging segment is a delete target"
    Assert-True ($DeletePaths -contains $StrictVersionStaging) "app_id-version staging segment is a delete target"
    Assert-True ($DeletePaths -notcontains $AmbiguousStagingDir) "partial staging match is not a delete target"
    Assert-True ($ExcludedPaths -contains $AmbiguousStagingDir) "partial staging match is an excluded candidate"
    Assert-True ($DeletePaths -contains $RuntimeAppEnv) "runtime app_env is a delete target"
    Assert-True ($DeletePaths -contains $BackupDir) "App Studio backup path is a delete target"
    Assert-True (@($ExcludedTargets | Where-Object { $_.category -eq "external_reference" -and $_.delete_allowed -eq $false }).Count -ge 2) "external references are excluded"
    Assert-True (@($ExcludedTargets | Where-Object { $_.category -eq "user_data" -and $_.delete_allowed -eq $false }).Count -ge 1) "user data is excluded"
    Assert-True (@($ExcludedTargets | Where-Object { $_.category -eq "shared_runtime" -and $_.delete_allowed -eq $false }).Count -ge 2) "shared runtime is excluded"
    Assert-True (@($Plan.staging_candidate_paths).Count -eq 1) "staging candidates are reported separately"
    Assert-True (@($DeleteTargets | Where-Object { [string]::IsNullOrWhiteSpace([string]$_.normalized_path) -or [string]::IsNullOrWhiteSpace([string]$_.comparison_key) }).Count -eq 0) "delete targets have comparison fields"
    Assert-True (@($ExcludedTargets | Where-Object { [string]::IsNullOrWhiteSpace([string]$_.normalized_path) -or [string]::IsNullOrWhiteSpace([string]$_.comparison_key) }).Count -eq 0) "excluded targets have comparison fields"
}
finally {
    [System.IO.File]::WriteAllBytes($ManifestPath, $OriginalManifestBytes)
    foreach ($Path in @($AppDir, $StrictStagingDir, $StrictVersionStaging, $AmbiguousStagingDir, $AppPackPath, $RuntimeAppEnv, $BackupStampDir)) {
        Remove-TestPath $Path
    }
}

Write-Host "Delete plan dry-run tests completed."
