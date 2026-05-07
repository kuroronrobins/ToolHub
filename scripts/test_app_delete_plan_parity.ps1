param(
    [switch]$KeepTemp
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$AppId = "deleteplan_probe"
$Version = "0.1.0"
$FixtureRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("toolhub_delete_plan_parity_" + [System.Guid]::NewGuid().ToString("N"))
$RustPlanPath = Join-Path $FixtureRoot "rust_delete_plan.json"

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

function New-DeletePlanFixture {
    param(
        [string]$Root,
        [string]$TargetAppId,
        [string]$TargetVersion
    )
    New-Item -ItemType Directory -Force -Path (Join-Path $Root "apps") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $Root "release") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $Root "runtime") | Out-Null

    $AppDir = Join-Path (Join-Path $Root "apps") $TargetAppId
    Write-TextFile -Path (Join-Path $AppDir "app.yaml") -Text @"
id: $TargetAppId
name: Delete Plan Probe
admin:
  version: $TargetVersion
runtime:
  required_runtime: python-embedded-toolhub-001
build:
  source_entry: C:\External\ToolHubProbe\main.py
  output_mirror: C:\External\ToolHubProbe\ToolHub_AppStudio_Output\$TargetAppId
"@
    Write-TextFile -Path (Join-Path $AppDir "README.md") -Text "probe"

    $AppPack = Join-Path (Join-Path (Join-Path $Root "release") "app_packs") "$TargetAppId-$TargetVersion.zip"
    Write-TextFile -Path $AppPack -Text "placeholder zip path for delete plan parity"
    Write-TextFile -Path (Join-Path (Join-Path (Join-Path (Join-Path $Root "release") "staging") $TargetAppId) "artifact.txt") -Text "strict"
    Write-TextFile -Path (Join-Path (Join-Path (Join-Path (Join-Path $Root "release") "staging") "$TargetAppId-$TargetVersion") "artifact.txt") -Text "strict version"
    Write-TextFile -Path (Join-Path (Join-Path (Join-Path (Join-Path $Root "release") "staging") "${TargetAppId}_other") "artifact.txt") -Text "ambiguous"
    Write-TextFile -Path (Join-Path (Join-Path (Join-Path (Join-Path $Root "runtime") "app_envs") $TargetAppId) "marker.txt") -Text "runtime"
    Write-TextFile -Path (Join-Path (Join-Path (Join-Path (Join-Path (Join-Path $Root "backups") "app_studio") "20990101_000000_delete_plan_test") $TargetAppId) "marker.txt") -Text "backup"
    Write-TextFile -Path (Join-Path (Join-Path (Join-Path (Join-Path (Join-Path $Root "backups") "app_lifecycle") "20990101_000000_delete_plan_test") $TargetAppId) "marker.txt") -Text "legacy backup"

    Write-TextFile -Path (Join-Path (Join-Path $Root "release") "app_manifest.json") -Text @"
{
  "schema_version": 1,
  "channel": "stable",
  "apps": {
    "$TargetAppId": {
      "version": "$TargetVersion",
      "package": "app_packs/$TargetAppId-$TargetVersion.zip",
      "sha256": "",
      "required_core": ">=0.1.0",
      "required_runner": ">=0.1.0",
      "required_runtime": "python-embedded-toolhub-001",
      "enabled": false
    }
  }
}
"@
}

function Get-PlanValue {
    param(
        [object]$Object,
        [string[]]$Names
    )
    if ($null -eq $Object) { return $null }
    foreach ($Name in $Names) {
        $Property = $Object.PSObject.Properties[$Name]
        if ($null -ne $Property) { return $Property.Value }
    }
    return $null
}

function Normalize-PathForCompare {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return "" }
    try {
        $Full = [System.IO.Path]::GetFullPath($Path)
    } catch {
        $Full = $Path
    }
    return $Full.Replace("\", "/").TrimEnd("/").ToLowerInvariant()
}

function Get-TargetRows {
    param(
        [object]$Plan,
        [string[]]$TargetNames
    )
    $Targets = @(Get-PlanValue -Object $Plan -Names $TargetNames)
    $Rows = foreach ($Target in $Targets) {
        $Category = [string](Get-PlanValue -Object $Target -Names @("category"))
        $Action = [string](Get-PlanValue -Object $Target -Names @("action"))
        $DeleteAllowed = [bool](Get-PlanValue -Object $Target -Names @("delete_allowed", "deleteAllowed"))
        $Normalized = [string](Get-PlanValue -Object $Target -Names @("normalized_path", "normalizedPath"))
        if ([string]::IsNullOrWhiteSpace($Normalized)) {
            $Normalized = Normalize-PathForCompare ([string](Get-PlanValue -Object $Target -Names @("path")))
        }
        "$Category|$Action|$DeleteAllowed|$Normalized"
    }
    return @($Rows | Sort-Object)
}

function Assert-SameRows {
    param(
        [string]$Label,
        [string[]]$Left,
        [string[]]$Right
    )
    $LeftText = @($Left) -join "`n"
    $RightText = @($Right) -join "`n"
    if ($LeftText -ne $RightText) {
        Write-Host "PowerShell ${Label}:"
        $Left | ForEach-Object { Write-Host "  $_" }
        Write-Host "Rust ${Label}:"
        $Right | ForEach-Object { Write-Host "  $_" }
        throw "Delete plan parity mismatch: $Label"
    }
    Write-Host "[OK] $Label match"
}

function Assert-Equal {
    param(
        [object]$Actual,
        [object]$Expected,
        [string]$Message
    )
    if ($Actual -ne $Expected) {
        throw "$Message expected=$Expected actual=$Actual"
    }
    Write-Host "[OK] $Message"
}

try {
    New-DeletePlanFixture -Root $FixtureRoot -TargetAppId $AppId -TargetVersion $Version

    $PowerShellJson = (& (Join-Path $PSScriptRoot "plan_app_delete.ps1") -AppId $AppId -ProjectRoot $FixtureRoot -DryRun -Json) | Out-String
    $PowerShellPlan = $PowerShellJson | ConvertFrom-Json

    $PreviousRoot = $env:TOOLHUB_DELETE_PLAN_PARITY_ROOT
    $PreviousAppId = $env:TOOLHUB_DELETE_PLAN_PARITY_APP_ID
    $PreviousOut = $env:TOOLHUB_DELETE_PLAN_PARITY_OUT
    try {
        $env:TOOLHUB_DELETE_PLAN_PARITY_ROOT = $FixtureRoot
        $env:TOOLHUB_DELETE_PLAN_PARITY_APP_ID = $AppId
        $env:TOOLHUB_DELETE_PLAN_PARITY_OUT = $RustPlanPath
        Push-Location (Join-Path (Join-Path $RepoRoot "launcher") "src-tauri")
        & cargo test delete_plan_parity_export_from_env -- --nocapture
        if ($LASTEXITCODE -ne 0) {
            throw "Rust delete plan parity export test failed."
        }
    } finally {
        Pop-Location
        if ($null -eq $PreviousRoot) { Remove-Item Env:\TOOLHUB_DELETE_PLAN_PARITY_ROOT -ErrorAction SilentlyContinue } else { $env:TOOLHUB_DELETE_PLAN_PARITY_ROOT = $PreviousRoot }
        if ($null -eq $PreviousAppId) { Remove-Item Env:\TOOLHUB_DELETE_PLAN_PARITY_APP_ID -ErrorAction SilentlyContinue } else { $env:TOOLHUB_DELETE_PLAN_PARITY_APP_ID = $PreviousAppId }
        if ($null -eq $PreviousOut) { Remove-Item Env:\TOOLHUB_DELETE_PLAN_PARITY_OUT -ErrorAction SilentlyContinue } else { $env:TOOLHUB_DELETE_PLAN_PARITY_OUT = $PreviousOut }
    }

    if (-not (Test-Path -LiteralPath $RustPlanPath -PathType Leaf)) {
        throw "Rust delete plan export was not created: $RustPlanPath"
    }
    $RustPlan = Get-Content -Raw -Encoding UTF8 $RustPlanPath | ConvertFrom-Json

    Assert-Equal (Get-PlanValue -Object $PowerShellPlan -Names @("manifest_entry_exists", "manifestEntryExists")) $true "PowerShell manifest entry is present"
    Assert-Equal (Get-PlanValue -Object $RustPlan -Names @("manifest_entry_exists", "manifestEntryExists")) $true "Rust manifest entry is present"
    Assert-Equal @((Get-PlanValue -Object $PowerShellPlan -Names @("staging_candidate_paths", "stagingCandidatePaths"))).Count 1 "PowerShell staging candidate count"
    Assert-Equal @((Get-PlanValue -Object $RustPlan -Names @("staging_candidate_paths", "stagingCandidatePaths"))).Count 1 "Rust staging candidate count"

    Assert-SameRows -Label "delete targets" `
        -Left (Get-TargetRows -Plan $PowerShellPlan -TargetNames @("delete_targets", "deleteTargets")) `
        -Right (Get-TargetRows -Plan $RustPlan -TargetNames @("delete_targets", "deleteTargets"))
    Assert-SameRows -Label "excluded targets" `
        -Left (Get-TargetRows -Plan $PowerShellPlan -TargetNames @("excluded_targets", "excludedTargets")) `
        -Right (Get-TargetRows -Plan $RustPlan -TargetNames @("excluded_targets", "excludedTargets"))

    Write-Host "Delete plan parity test completed."
} finally {
    if (-not $KeepTemp -and (Test-Path -LiteralPath $FixtureRoot)) {
        Remove-Item -LiteralPath $FixtureRoot -Recurse -Force
    } elseif ($KeepTemp) {
        Write-Host "Temporary fixture preserved: $FixtureRoot"
    }
}
