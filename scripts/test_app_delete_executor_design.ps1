param(
    [switch]$KeepTemp
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$AppId = "__executor_probe__"
$Version = "0.1.0"
$FixtureRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("toolhub_delete_executor_design_" + [System.Guid]::NewGuid().ToString("N"))
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

function New-ExecutorFixture {
    param([string]$Root)

    $AppDir = Join-Path (Join-Path $Root "apps") $AppId
    $AppPack = Join-Path (Join-Path (Join-Path $Root "release") "app_packs") "$AppId-$Version.zip"
    $StagingTarget = Join-Path (Join-Path (Join-Path $Root "release") "staging") $AppId
    $StagingVersionTarget = Join-Path (Join-Path (Join-Path $Root "release") "staging") "$AppId-$Version"
    $StagingCandidate = Join-Path (Join-Path (Join-Path $Root "release") "staging") "${AppId}_candidate"
    $RuntimeAppEnv = Join-Path (Join-Path (Join-Path $Root "runtime") "app_envs") $AppId
    $Backup = Join-Path (Join-Path (Join-Path (Join-Path $Root "backups") "app_studio") "20990101_000000_executor_test") $AppId
    $LifecycleBackup = Join-Path (Join-Path (Join-Path (Join-Path $Root "backups") "app_lifecycle") "20990101_000000_executor_test") $AppId
    $ManifestPath = Join-Path (Join-Path $Root "release") "app_manifest.json"

    Write-TextFile -Path (Join-Path $AppDir "app.yaml") -Text @"
id: $AppId
name: Delete Executor Probe
admin:
  version: $Version
runtime:
  required_runtime: python-embedded-toolhub-001
build:
  source_entry: C:\External\ToolHubExecutorProbe\main.py
  output_mirror: C:\External\ToolHubExecutorProbe\ToolHub_AppStudio_Output\$AppId
"@
    Write-TextFile -Path (Join-Path $AppDir "README.md") -Text "executor probe"
    Write-TextFile -Path $AppPack -Text "placeholder zip path for executor design test"
    Write-TextFile -Path (Join-Path $StagingTarget "artifact.txt") -Text "strict"
    Write-TextFile -Path (Join-Path $StagingVersionTarget "artifact.txt") -Text "strict version"
    Write-TextFile -Path (Join-Path $StagingCandidate "artifact.txt") -Text "candidate"
    Write-TextFile -Path (Join-Path $RuntimeAppEnv "marker.txt") -Text "runtime"
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
        backup = $Backup
        lifecycle_backup = $LifecycleBackup
        manifest_path = $ManifestPath
    }
}

if (-not (Test-Path -LiteralPath $Executor -PathType Leaf)) {
    throw "Missing executor script: $Executor"
}

$Paths = $null
try {
    $Paths = New-ExecutorFixture -Root $FixtureRoot

    $DryRunOutput = & powershell -NoProfile -ExecutionPolicy Bypass -File $Executor -AppId $AppId -ProjectRoot $FixtureRoot -DryRun 2>&1
    $DryRunExit = $LASTEXITCODE
    $DryRunText = ($DryRunOutput | Out-String)
    Assert-True ($DryRunExit -eq 0) "DryRun exits successfully"
    Assert-True ($DryRunText.Contains("Full delete executor")) "DryRun prints executor heading"
    Assert-True ($DryRunText.Contains("production Apply is not implemented")) "DryRun states production Apply is not implemented"
    Assert-True ($DryRunText.Contains("Delete ordering")) "DryRun prints delete ordering"
    Assert-True ($DryRunText.Contains("Excluded targets")) "DryRun prints excluded targets"

    foreach ($Path in $Paths.GetEnumerator()) {
        Assert-True (Test-Path -LiteralPath $Path.Value) "DryRun did not delete $($Path.Key)"
    }

    $JsonOutput = & powershell -NoProfile -ExecutionPolicy Bypass -File $Executor -AppId $AppId -ProjectRoot $FixtureRoot -DryRun -Json 2>&1
    $JsonExit = $LASTEXITCODE
    Assert-True ($JsonExit -eq 0) "DryRun JSON exits successfully"
    $JsonPlan = (($JsonOutput | Out-String) | ConvertFrom-Json)
    Assert-True ($JsonPlan.apply_implemented -eq $false) "JSON marks Apply as unimplemented"
    Assert-True (@($JsonPlan.delete_ordering).Count -ge 8) "JSON includes executor ordering"

    $PreviousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $ApplyOutput = & powershell -NoProfile -ExecutionPolicy Bypass -File $Executor -AppId $AppId -ProjectRoot $FixtureRoot -Apply 2>&1
        $ApplyExit = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $PreviousErrorActionPreference
    }
    $ApplyText = ($ApplyOutput | Out-String)
    Assert-True ($ApplyExit -ne 0) "Apply without temporary gate is rejected"
    Assert-True ($ApplyText.Contains("Apply requires -AllowTemporaryAppApply")) "Apply rejection requires temporary gate"

    $ErrorActionPreference = "Continue"
    try {
        $UnsafeApplyOutput = & powershell -NoProfile -ExecutionPolicy Bypass -File $Executor -AppId $AppId -ProjectRoot $FixtureRoot -Apply -AllowTemporaryAppApply 2>&1
        $UnsafeApplyExit = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $PreviousErrorActionPreference
    }
    $UnsafeApplyText = ($UnsafeApplyOutput | Out-String)
    Assert-True ($UnsafeApplyExit -ne 0) "Temporary Apply rejects unsafe app_id prefix"
    Assert-True ($UnsafeApplyText.Contains("temporary app ids")) "Unsafe app_id rejection explains prefix gate"

    foreach ($Path in $Paths.GetEnumerator()) {
        Assert-True (Test-Path -LiteralPath $Path.Value) "Apply rejection did not delete $($Path.Key)"
    }
} finally {
    if (-not $KeepTemp -and (Test-Path -LiteralPath $FixtureRoot)) {
        $Full = [System.IO.Path]::GetFullPath($FixtureRoot)
        $Temp = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
        if (-not $Full.StartsWith($Temp, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to clean fixture outside temp: $Full"
        }
        Remove-Item -LiteralPath $Full -Recurse -Force
    } elseif ($KeepTemp) {
        Write-Host "Temporary fixture preserved: $FixtureRoot"
    }
}

Write-Host "Full delete executor design test completed. No full-delete files were removed."
exit 0
