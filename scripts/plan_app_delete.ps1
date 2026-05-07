param(
    [Parameter(Mandatory = $true)]
    [string]$AppId,
    [string]$ProjectRoot,
    [switch]$DryRun,
    [switch]$Json
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$Root = if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
} else {
    (Resolve-Path -LiteralPath $ProjectRoot).Path
}
$ReleaseDir = Join-Path $Root "release"
$AppsDir = Join-Path $Root "apps"
$AppManifestPath = Join-Path $ReleaseDir "app_manifest.json"

function Normalize-PlanPath {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return "" }
    try {
        $Full = [System.IO.Path]::GetFullPath($Path)
    } catch {
        $Full = $Path
    }
    return $Full.Replace("\", "/").TrimEnd("/").ToLowerInvariant()
}

function Add-Target {
    param(
        [System.Collections.ArrayList]$List,
        [string]$Category,
        [string]$Path,
        [bool]$DeleteAllowed,
        [string]$Action,
        [string]$Note
    )
    $Exists = Test-Path -LiteralPath $Path
    $NormalizedPath = Normalize-PlanPath $Path
    [void]$List.Add([ordered]@{
        category = $Category
        path = $Path
        normalized_path = $NormalizedPath
        exists = $Exists
        delete_allowed = $DeleteAllowed
        action = $Action
        comparison_key = "$Category|$Action|$NormalizedPath"
        note = $Note
    })
}

function Add-PathIfPresent {
    param(
        [System.Collections.ArrayList]$List,
        [string]$Category,
        [string]$Path,
        [bool]$DeleteAllowed,
        [string]$Action,
        [string]$Note
    )
    if ([string]::IsNullOrWhiteSpace($Path)) { return }
    Add-Target -List $List -Category $Category -Path $Path -DeleteAllowed $DeleteAllowed -Action $Action -Note $Note
}

function Get-PropertyValue {
    param(
        [object]$Object,
        [string]$Name,
        [object]$DefaultValue = $null
    )
    if ($null -eq $Object) { return $DefaultValue }
    $Property = $Object.PSObject.Properties[$Name]
    if ($null -eq $Property) { return $DefaultValue }
    if ($null -eq $Property.Value) { return $DefaultValue }
    return $Property.Value
}

function Find-BackupPaths {
    param(
        [string]$RootPath,
        [string]$TargetAppId
    )
    if (-not (Test-Path -LiteralPath $RootPath -PathType Container)) { return @() }
    return @(
        Get-ChildItem -LiteralPath $RootPath -Directory -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -eq $TargetAppId } |
            ForEach-Object { $_.FullName } |
            Sort-Object -Unique
    )
}

function Find-StagingPaths {
    param(
        [string]$TargetAppId,
        [string]$Version
    )
    $StagingRoot = Join-Path $ReleaseDir "staging"
    $Targets = New-Object System.Collections.ArrayList
    $Candidates = New-Object System.Collections.ArrayList
    if (Test-Path -LiteralPath $StagingRoot -PathType Container) {
        Find-StagingPathsInner -RootPath $StagingRoot -CurrentPath $StagingRoot -TargetAppId $TargetAppId -Version $Version -Targets $Targets -Candidates $Candidates
    }
    return [pscustomobject]@{
        targets = @($Targets | Sort-Object -Unique)
        candidates = @($Candidates | Sort-Object -Unique)
    }
}

function Find-StagingPathsInner {
    param(
        [string]$RootPath,
        [string]$CurrentPath,
        [string]$TargetAppId,
        [string]$Version,
        [System.Collections.ArrayList]$Targets,
        [System.Collections.ArrayList]$Candidates
    )
    foreach ($Item in @(Get-ChildItem -LiteralPath $CurrentPath -ErrorAction SilentlyContinue)) {
        $Match = Get-StagingPathMatch -RootPath $RootPath -Path $Item.FullName -TargetAppId $TargetAppId -Version $Version
        if ($Match -eq "target") {
            [void]$Targets.Add($Item.FullName)
            continue
        }
        if ($Match -eq "candidate") {
            [void]$Candidates.Add($Item.FullName)
            continue
        }
        if ($Item.PSIsContainer) {
            Find-StagingPathsInner -RootPath $RootPath -CurrentPath $Item.FullName -TargetAppId $TargetAppId -Version $Version -Targets $Targets -Candidates $Candidates
        }
    }
}

function Get-StagingPathMatch {
    param(
        [string]$RootPath,
        [string]$Path,
        [string]$TargetAppId,
        [string]$Version
    )
    $Base = [System.IO.Path]::GetFullPath($RootPath).TrimEnd("\", "/")
    $Full = [System.IO.Path]::GetFullPath($Path)
    if ($Full.StartsWith($Base + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
        $Relative = $Full.Substring($Base.Length + 1)
    } else {
        $Relative = Split-Path -Leaf $Full
    }
    $Segments = @($Relative -split "[\\/]+" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    $VersionPrefix = if ([string]::IsNullOrWhiteSpace($Version)) { $null } else { "$TargetAppId-$Version" }
    $ContainsOnly = $false
    foreach ($Segment in $Segments) {
        if ($Segment -eq $TargetAppId) {
            return "target"
        }
        if ($VersionPrefix -and ($Segment -eq $VersionPrefix -or $Segment.StartsWith("$VersionPrefix.", [System.StringComparison]::OrdinalIgnoreCase) -or $Segment.StartsWith("$VersionPrefix-", [System.StringComparison]::OrdinalIgnoreCase))) {
            return "target"
        }
        if ($Segment.IndexOf($TargetAppId, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
            $ContainsOnly = $true
        }
    }
    if ($ContainsOnly) { return "candidate" }
    return "none"
}

function Find-AppPackPaths {
    param(
        [string]$TargetAppId,
        [string]$ManifestPackage
    )
    $Paths = New-Object System.Collections.ArrayList
    if (-not [string]::IsNullOrWhiteSpace($ManifestPackage)) {
        [void]$Paths.Add((Join-Path $ReleaseDir $ManifestPackage))
    }
    $AppPacksDir = Join-Path $ReleaseDir "app_packs"
    if (Test-Path -LiteralPath $AppPacksDir -PathType Container) {
        Get-ChildItem -LiteralPath $AppPacksDir -File -Filter "$TargetAppId-*.zip" -ErrorAction SilentlyContinue |
            ForEach-Object {
                if (-not $Paths.Contains($_.FullName)) {
                    [void]$Paths.Add($_.FullName)
                }
            }
    }
    return @($Paths | Sort-Object -Unique)
}

function Find-ExternalReferences {
    param([string]$AppYamlPath)
    if (-not (Test-Path -LiteralPath $AppYamlPath -PathType Leaf)) { return @() }
    $Text = Get-Content -Raw -Encoding UTF8 $AppYamlPath
    $Matches = [regex]::Matches($Text, "([A-Za-z]:\\[^`r`n`"']+)")
    $Refs = New-Object System.Collections.ArrayList
    foreach ($Match in $Matches) {
        $Candidate = $Match.Groups[1].Value.Trim().TrimEnd(",", "]", "}", " ")
        if ([string]::IsNullOrWhiteSpace($Candidate)) { continue }
        $Full = [System.IO.Path]::GetFullPath($Candidate)
        if ($Full.StartsWith($Root, [System.StringComparison]::OrdinalIgnoreCase)) { continue }
        if (-not $Refs.Contains($Full)) {
            [void]$Refs.Add($Full)
        }
    }
    return @($Refs | Sort-Object -Unique)
}

if ($AppId -notmatch "^[A-Za-z0-9_.-]+$") {
    throw "Invalid app_id: $AppId"
}
if (-not (Test-Path -LiteralPath $AppManifestPath -PathType Leaf)) {
    throw "release/app_manifest.json was not found."
}

$Manifest = Get-Content -Raw -Encoding UTF8 $AppManifestPath | ConvertFrom-Json
$Entry = Get-PropertyValue -Object $Manifest.apps -Name $AppId -DefaultValue $null
$SourceDir = Join-Path $AppsDir $AppId
$AppYaml = Join-Path $SourceDir "app.yaml"
$ManifestPackage = if ($Entry) { [string](Get-PropertyValue -Object $Entry -Name "package" -DefaultValue "") } else { "" }
$ManifestVersion = if ($Entry) { [string](Get-PropertyValue -Object $Entry -Name "version" -DefaultValue "") } else { "" }
$RuntimeAppEnv = Join-Path (Join-Path (Join-Path $Root "runtime") "app_envs") $AppId
$DeleteTargets = New-Object System.Collections.ArrayList
$ExcludedTargets = New-Object System.Collections.ArrayList
$Warnings = New-Object System.Collections.ArrayList

Add-Target -List $DeleteTargets -Category "managed_required" -Path $SourceDir -DeleteAllowed $true -Action "delete apps/<app_id>/" -Note "Application source of truth."
Add-Target -List $DeleteTargets -Category "managed_required" -Path $AppManifestPath -DeleteAllowed $true -Action "remove app_manifest entry" -Note "Future full delete removes only this app entry from the generated index."

foreach ($Path in (Find-AppPackPaths -TargetAppId $AppId -ManifestPackage $ManifestPackage)) {
    Add-Target -List $DeleteTargets -Category "managed_generated" -Path $Path -DeleteAllowed $true -Action "delete App Pack zip" -Note "Generated App Pack for this app."
}
$StagingPlan = Find-StagingPaths -TargetAppId $AppId -Version $ManifestVersion
foreach ($Path in $StagingPlan.targets) {
    Add-Target -List $DeleteTargets -Category "managed_generated" -Path $Path -DeleteAllowed $true -Action "delete staging artifact" -Note "Generated release staging artifact for this app."
}
foreach ($Path in $StagingPlan.candidates) {
    Add-Target -List $ExcludedTargets -Category "managed_generated_candidate" -Path $Path -DeleteAllowed $false -Action "review staging candidate" -Note "Name contains app_id but does not match strict staging rules; future delete must not remove it automatically."
}
Add-Target -List $DeleteTargets -Category "managed_generated" -Path $RuntimeAppEnv -DeleteAllowed $true -Action "delete runtime app_env" -Note "App-specific runtime environment."

foreach ($Path in (Find-BackupPaths -RootPath (Join-Path (Join-Path $Root "backups") "app_studio") -TargetAppId $AppId)) {
    Add-Target -List $DeleteTargets -Category "managed_history" -Path $Path -DeleteAllowed $true -Action "delete App Studio backup" -Note "Repository-local app backup/history."
}
foreach ($Path in (Find-BackupPaths -RootPath (Join-Path (Join-Path $Root "backups") "app_lifecycle") -TargetAppId $AppId)) {
    Add-Target -List $DeleteTargets -Category "managed_history" -Path $Path -DeleteAllowed $true -Action "delete legacy lifecycle backup" -Note "Repository-local legacy lifecycle backup/history."
}

foreach ($Path in (Find-ExternalReferences -AppYamlPath $AppYaml)) {
    Add-Target -List $ExcludedTargets -Category "external_reference" -Path $Path -DeleteAllowed $false -Action "exclude external app.yaml reference" -Note "External source/output paths are not app-owned."
}

$LocalAppData = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { Join-Path $env:USERPROFILE "AppData\Local" }
foreach ($Path in @(
    (Join-Path (Join-Path $LocalAppData "ToolHub") "data"),
    (Join-Path (Join-Path (Join-Path $LocalAppData "ToolHub") "data") "logs"),
    (Join-Path (Join-Path (Join-Path $LocalAppData "ToolHub") "data") "browser_profiles"),
    (Join-Path (Join-Path (Join-Path $LocalAppData "ToolHub") "data") "app_state"),
    (Join-Path (Join-Path (Join-Path (Join-Path $LocalAppData "ToolHub") "data") "app_state") $AppId)
)) {
    Add-Target -List $ExcludedTargets -Category "user_data" -Path $Path -DeleteAllowed $false -Action "exclude user data" -Note "User data is outside repository-managed app deletion."
}

foreach ($Path in @(
    (Join-Path (Join-Path $Root "runtime") "python"),
    (Join-Path (Join-Path $Root "runtime") "web_automation_runtime")
)) {
    Add-Target -List $ExcludedTargets -Category "shared_runtime" -Path $Path -DeleteAllowed $false -Action "exclude shared runtime" -Note "Shared runtime is not app-owned."
}

if (-not (Test-Path -LiteralPath $AppYaml -PathType Leaf)) {
    [void]$Warnings.Add("apps/<app_id>/app.yaml is missing.")
}
if ($null -eq $Entry) {
    [void]$Warnings.Add("release/app_manifest.json has no entry for this app.")
}
if (@($StagingPlan.candidates).Count -gt 0) {
    [void]$Warnings.Add("Potential staging artifacts matched only by partial app_id and were excluded from delete targets.")
}

$DeleteTargets = @($DeleteTargets | Sort-Object -Property comparison_key)
$ExcludedTargets = @($ExcludedTargets | Sort-Object -Property comparison_key)

$Plan = [ordered]@{
    app_id = $AppId
    mode = "dry_run"
    manifest_entry_exists = ($null -ne $Entry)
    manifest_enabled = if ($Entry) { [bool](Get-PropertyValue -Object $Entry -Name "enabled" -DefaultValue $true) } else { $null }
    manifest_version = if ($Entry) { Get-PropertyValue -Object $Entry -Name "version" -DefaultValue $null } else { $null }
    manifest_package = $ManifestPackage
    source_dir = $SourceDir
    app_yaml = $AppYaml
    app_pack_paths = @(Find-AppPackPaths -TargetAppId $AppId -ManifestPackage $ManifestPackage)
    staging_paths = @($StagingPlan.targets)
    staging_candidate_paths = @($StagingPlan.candidates)
    delete_targets = @($DeleteTargets)
    excluded_targets = @($ExcludedTargets)
    warnings = @($Warnings)
}

if ($Json) {
    $Plan | ConvertTo-Json -Depth 20
} else {
    Write-Host "Deletion plan for $AppId"
    Write-Host "  mode: dry_run"
    Write-Host "  manifest entry: $($Plan.manifest_entry_exists)"
    Write-Host "  enabled: $($Plan.manifest_enabled)"
    Write-Host "  delete targets: $($DeleteTargets.Count)"
    foreach ($Target in $DeleteTargets) {
        Write-Host "    [$($Target.category)] $($Target.action): $($Target.path) (exists=$($Target.exists))"
    }
    Write-Host "  excluded targets: $($ExcludedTargets.Count)"
    foreach ($Target in $ExcludedTargets) {
        Write-Host "    [$($Target.category)] $($Target.action): $($Target.path) (exists=$($Target.exists))"
    }
    if ($Warnings.Count -gt 0) {
        Write-Host "  warnings:"
        foreach ($Warning in $Warnings) { Write-Host "    - $Warning" }
    }
    Write-Host "No files were deleted."
}
