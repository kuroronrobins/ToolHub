param(
    [switch]$KeepTemp
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Suffix = [System.Guid]::NewGuid().ToString("N").Substring(0, 10)
$AppId = "__delete_e2e_$Suffix"
$Version = "0.1.0"
$FixtureRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("toolhub_full_delete_e2e_" + [System.Guid]::NewGuid().ToString("N"))
$ExternalRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("toolhub_full_delete_e2e_external_" + [System.Guid]::NewGuid().ToString("N"))
$Executor = Join-Path $PSScriptRoot "execute_app_delete.ps1"

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

function Get-ItemCount {
    param([object]$Value)
    if ($null -eq $Value) { return 0 }
    if ($Value -is [pscustomobject] -and @($Value.PSObject.Properties).Count -eq 0) { return 0 }
    return @($Value).Count
}

function Write-TextFile {
    param(
        [string]$Path,
        [string]$Text
    )
    $Parent = Split-Path -Parent $Path
    if (-not [string]::IsNullOrWhiteSpace($Parent)) {
        New-Item -ItemType Directory -Force -Path $Parent | Out-Null
    }
    [System.IO.File]::WriteAllText($Path, $Text, [System.Text.UTF8Encoding]::new($false))
}

function Remove-TempRoot {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path)) { return }
    $Full = [System.IO.Path]::GetFullPath($Path)
    $Temp = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
    if (-not $Full.StartsWith($Temp, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clean path outside temp: $Full"
    }
    Remove-Item -LiteralPath $Full -Recurse -Force
}

function Invoke-Executor {
    param(
        [string[]]$Arguments,
        [switch]$ExpectFailure
    )
    $PreviousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $Output = & powershell -NoProfile -ExecutionPolicy Bypass -File $Executor @Arguments 2>&1
        $ExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $PreviousErrorActionPreference
    }
    if ($ExpectFailure) {
        Assert-True ($ExitCode -ne 0) "executor failed as expected: $($Arguments -join ' ')"
    } else {
        Assert-True ($ExitCode -eq 0) "executor succeeded: $($Arguments -join ' ')"
    }
    return [ordered]@{
        exit_code = $ExitCode
        text = ($Output | Out-String)
    }
}

function New-FullDeleteFixture {
    $AppDir = Join-Path (Join-Path $FixtureRoot "apps") $AppId
    $AppPack = Join-Path (Join-Path (Join-Path $FixtureRoot "release") "app_packs") "$AppId-$Version.zip"
    $StagingTarget = Join-Path (Join-Path (Join-Path $FixtureRoot "release") "staging") $AppId
    $StagingVersionTarget = Join-Path (Join-Path (Join-Path $FixtureRoot "release") "staging") "$AppId-$Version"
    $StagingCandidate = Join-Path (Join-Path (Join-Path $FixtureRoot "release") "staging") "${AppId}_candidate"
    $RuntimeAppEnv = Join-Path (Join-Path (Join-Path $FixtureRoot "runtime") "app_envs") $AppId
    $SharedPython = Join-Path (Join-Path $FixtureRoot "runtime") "python"
    $SharedWebRuntime = Join-Path (Join-Path $FixtureRoot "runtime") "web_automation_runtime"
    $Backup = Join-Path (Join-Path (Join-Path (Join-Path $FixtureRoot "backups") "app_studio") "20990101_000000_full_delete_e2e") $AppId
    $LifecycleBackup = Join-Path (Join-Path (Join-Path (Join-Path $FixtureRoot "backups") "app_lifecycle") "20990101_000000_full_delete_e2e") $AppId
    $ManifestPath = Join-Path (Join-Path $FixtureRoot "release") "app_manifest.json"
    $ExternalSource = Join-Path $ExternalRoot "source_main.py"
    $ExternalMirror = Join-Path $ExternalRoot "ToolHub_AppStudio_Output\$AppId"

    Write-TextFile -Path $ExternalSource -Text "external source must remain"
    Write-TextFile -Path (Join-Path $ExternalMirror "marker.txt") -Text "external output mirror must remain"
    Write-TextFile -Path (Join-Path $AppDir "app.yaml") -Text @"
id: $AppId
name: Full Delete E2E App
admin:
  version: $Version
runtime:
  required_runtime: python-embedded-toolhub-001
build:
  source_entry: $ExternalSource
  output_mirror: $ExternalMirror
"@
    Write-TextFile -Path (Join-Path $AppDir "README.md") -Text "full delete e2e fixture"
    Write-TextFile -Path $AppPack -Text "placeholder zip path for full delete e2e"
    Write-TextFile -Path (Join-Path $StagingTarget "artifact.txt") -Text "strict staging"
    Write-TextFile -Path (Join-Path $StagingVersionTarget "artifact.txt") -Text "version staging"
    Write-TextFile -Path (Join-Path $StagingCandidate "artifact.txt") -Text "candidate staging"
    Write-TextFile -Path (Join-Path $RuntimeAppEnv "marker.txt") -Text "runtime app env"
    Write-TextFile -Path (Join-Path $SharedPython "python.exe") -Text "shared python placeholder"
    Write-TextFile -Path (Join-Path $SharedWebRuntime "README.md") -Text "shared web runtime placeholder"
    Write-TextFile -Path (Join-Path $Backup "marker.txt") -Text "backup"
    Write-TextFile -Path (Join-Path $LifecycleBackup "marker.txt") -Text "legacy backup"
    Write-TextFile -Path $ManifestPath -Text @"
{
  "schema_version": 1,
  "channel": "stable",
  "apps": {
    "$AppId": {
      "version": "$Version",
      "package": "app_packs/$AppId-$Version.zip",
      "sha256": "",
      "required_core": ">=0.1.0",
      "required_runner": ">=0.1.0",
      "required_runtime": "python-embedded-toolhub-001",
      "enabled": false
    }
  }
}
"@

    return [ordered]@{
        app_dir = $AppDir
        app_pack = $AppPack
        staging_target = $StagingTarget
        staging_version_target = $StagingVersionTarget
        staging_candidate = $StagingCandidate
        runtime_app_env = $RuntimeAppEnv
        shared_python = $SharedPython
        shared_web_runtime = $SharedWebRuntime
        backup = $Backup
        lifecycle_backup = $LifecycleBackup
        manifest_path = $ManifestPath
        external_source = $ExternalSource
        external_mirror = $ExternalMirror
    }
}

if (-not (Test-Path -LiteralPath $Executor -PathType Leaf)) {
    throw "Missing executor script: $Executor"
}

$Paths = $null
try {
    $Paths = New-FullDeleteFixture

    $Rejected = Invoke-Executor -Arguments @("-AppId", $AppId, "-ProjectRoot", $FixtureRoot, "-Apply") -ExpectFailure
    Assert-True ($Rejected.text.Contains("Apply requires -AllowTemporaryAppApply")) "Apply without temporary gate is refused"
    foreach ($Key in @("app_dir", "app_pack", "staging_target", "staging_version_target", "runtime_app_env", "backup", "lifecycle_backup")) {
        Assert-True (Test-Path -LiteralPath $Paths[$Key]) "unsafe Apply rejection kept $Key"
    }

    $ProductionRejected = Invoke-Executor -Arguments @("-AppId", "__delete_e2e_production_refusal", "-ProjectRoot", $RepoRoot, "-Apply", "-AllowTemporaryAppApply") -ExpectFailure
    Assert-True ($ProductionRejected.text.Contains("production repository root")) "production root Apply is refused"

    $ApplyOutput = Invoke-Executor -Arguments @("-AppId", $AppId, "-ProjectRoot", $FixtureRoot, "-Apply", "-AllowTemporaryAppApply", "-Json")
    $ApplyResult = $ApplyOutput.text | ConvertFrom-Json
    Assert-True ($ApplyResult.mode -eq "apply") "Apply result reports apply mode"
    Assert-True ($ApplyResult.temporary_apply -eq $true) "Apply result is marked temporary-only"
    Assert-True ((Get-ItemCount $ApplyResult.failed) -eq 0) "Apply result has no failed records"
    Assert-True ($ApplyResult.manifest_entry_removed -eq $true) "manifest entry was removed by Apply"
    Assert-True ((Get-ItemCount $ApplyResult.post_check_summary.remaining_file_delete_targets) -eq 0) "post-check has no remaining file delete targets"

    foreach ($Key in @("app_dir", "app_pack", "staging_target", "staging_version_target", "runtime_app_env", "backup", "lifecycle_backup")) {
        Assert-True (-not (Test-Path -LiteralPath $Paths[$Key])) "Apply removed $Key"
    }
    foreach ($Key in @("staging_candidate", "shared_python", "shared_web_runtime", "external_source", "external_mirror")) {
        Assert-True (Test-Path -LiteralPath $Paths[$Key]) "Apply preserved $Key"
    }

    Assert-True (Test-Path -LiteralPath $Paths.manifest_path -PathType Leaf) "manifest file remains"
    $ManifestAfter = Get-Content -Raw -Encoding UTF8 $Paths.manifest_path | ConvertFrom-Json
    Assert-True (-not ($ManifestAfter.apps.PSObject.Properties[$AppId])) "manifest entry is absent"

    $ExcludedCategories = @($ApplyResult.excluded | ForEach-Object { [string]$_.category })
    Assert-True ($ExcludedCategories -contains "external_reference") "external references were excluded"
    Assert-True ($ExcludedCategories -contains "user_data") "user data paths were excluded"
    Assert-True ($ExcludedCategories -contains "shared_runtime") "shared runtime paths were excluded"
    Assert-True ($ExcludedCategories -contains "managed_generated_candidate") "staging candidate was excluded"

    $SecondApplyOutput = Invoke-Executor -Arguments @("-AppId", $AppId, "-ProjectRoot", $FixtureRoot, "-Apply", "-AllowTemporaryAppApply", "-Json")
    $SecondApplyResult = $SecondApplyOutput.text | ConvertFrom-Json
    Assert-True ((Get-ItemCount $SecondApplyResult.failed) -eq 0) "second Apply is idempotent"
    Assert-True ($SecondApplyResult.manifest_entry_removed -eq $false) "second Apply treats missing manifest entry as already clean"
} finally {
    if (-not $KeepTemp) {
        Remove-TempRoot $FixtureRoot
        Remove-TempRoot $ExternalRoot
    } else {
        Write-Host "Temporary fixture preserved: $FixtureRoot"
        Write-Host "Temporary external root preserved: $ExternalRoot"
    }
}

Write-Host "Temporary full-delete E2E completed. Production repository was not modified."
exit 0
