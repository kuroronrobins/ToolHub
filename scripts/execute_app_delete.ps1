param(
    [Parameter(Mandatory = $true)]
    [string]$AppId,
    [string]$ProjectRoot,
    [switch]$DryRun,
    [switch]$Apply,
    [switch]$Json
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

if ($DryRun -and $Apply) {
    throw "Specify only one mode: -DryRun or -Apply."
}

if ($Apply) {
    throw "Apply is not implemented in Phase 3. Run -DryRun to inspect the executor order without deleting files."
}

$EffectiveDryRun = $true
$Root = if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
} else {
    (Resolve-Path -LiteralPath $ProjectRoot).Path
}
$PlanScript = Join-Path $PSScriptRoot "plan_app_delete.ps1"

if (-not (Test-Path -LiteralPath $PlanScript -PathType Leaf)) {
    throw "Missing plan script: $PlanScript"
}

function Get-PlanValue {
    param(
        [object]$Object,
        [string[]]$Names,
        [object]$DefaultValue = $null
    )
    if ($null -eq $Object) { return $DefaultValue }
    foreach ($Name in $Names) {
        $Property = $Object.PSObject.Properties[$Name]
        if ($null -ne $Property) { return $Property.Value }
    }
    return $DefaultValue
}

function Test-TargetCategory {
    param(
        [object]$Target,
        [string[]]$Categories
    )
    $Category = [string](Get-PlanValue -Object $Target -Names @("category") -DefaultValue "")
    return $Categories -contains $Category
}

function Test-PathInsideRoot {
    param(
        [string]$Path,
        [string]$RootPath
    )
    if ([string]::IsNullOrWhiteSpace($Path)) { return $false }
    try {
        $Full = [System.IO.Path]::GetFullPath($Path).TrimEnd("\", "/")
        $Base = [System.IO.Path]::GetFullPath($RootPath).TrimEnd("\", "/")
    } catch {
        return $false
    }
    if ($Full -eq $Base) { return $false }
    return $Full.StartsWith($Base + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)
}

function New-ExecutorStep {
    param(
        [int]$Order,
        [string]$Name,
        [object[]]$Targets,
        [string]$Action
    )
    return [ordered]@{
        order = $Order
        name = $Name
        action = $Action
        target_count = @($Targets).Count
        targets = @($Targets)
    }
}

function Test-PlanSafety {
    param([object]$Plan)

    $Errors = New-Object System.Collections.ArrayList
    $DeleteTargets = @(Get-PlanValue -Object $Plan -Names @("delete_targets", "deleteTargets") -DefaultValue @())
    $ExcludedTargets = @(Get-PlanValue -Object $Plan -Names @("excluded_targets", "excludedTargets") -DefaultValue @())
    $ForbiddenDeleteCategories = @("external_reference", "user_data", "shared_runtime", "managed_generated_candidate")

    foreach ($Target in $DeleteTargets) {
        $DeleteAllowed = [bool](Get-PlanValue -Object $Target -Names @("delete_allowed", "deleteAllowed") -DefaultValue $false)
        $Path = [string](Get-PlanValue -Object $Target -Names @("path") -DefaultValue "")
        $Action = [string](Get-PlanValue -Object $Target -Names @("action") -DefaultValue "")
        if (-not $DeleteAllowed) {
            [void]$Errors.Add("Delete target is not marked delete_allowed=true: $Path")
        }
        if (Test-TargetCategory -Target $Target -Categories $ForbiddenDeleteCategories) {
            [void]$Errors.Add("Forbidden category appears in delete targets: $Path")
        }
        if (-not (Test-PathInsideRoot -Path $Path -RootPath $Root)) {
            [void]$Errors.Add("Delete target is not safely inside the project root: $Path")
        }
        if ($Path -like "*release*app_manifest.json" -and $Action -ne "remove app_manifest entry") {
            [void]$Errors.Add("Manifest file target must be entry removal only: $Path")
        }
    }

    foreach ($Target in $ExcludedTargets) {
        $DeleteAllowed = [bool](Get-PlanValue -Object $Target -Names @("delete_allowed", "deleteAllowed") -DefaultValue $true)
        $Path = [string](Get-PlanValue -Object $Target -Names @("path") -DefaultValue "")
        if ($DeleteAllowed) {
            [void]$Errors.Add("Excluded target must be delete_allowed=false: $Path")
        }
    }

    return @($Errors)
}

function Get-OrderedDeleteSteps {
    param([object]$Plan)

    $DeleteTargets = @(Get-PlanValue -Object $Plan -Names @("delete_targets", "deleteTargets") -DefaultValue @())
    $AppPackTargets = @($DeleteTargets | Where-Object { [string](Get-PlanValue -Object $_ -Names @("action")) -eq "delete App Pack zip" })
    $StagingTargets = @($DeleteTargets | Where-Object { [string](Get-PlanValue -Object $_ -Names @("action")) -eq "delete staging artifact" })
    $RuntimeTargets = @($DeleteTargets | Where-Object { [string](Get-PlanValue -Object $_ -Names @("action")) -eq "delete runtime app_env" })
    $HistoryTargets = @($DeleteTargets | Where-Object { Test-TargetCategory -Target $_ -Categories @("managed_history") })
    $SourceTargets = @($DeleteTargets | Where-Object { [string](Get-PlanValue -Object $_ -Names @("action")) -eq "delete apps/<app_id>/" })
    $ManifestTargets = @($DeleteTargets | Where-Object { [string](Get-PlanValue -Object $_ -Names @("action")) -eq "remove app_manifest entry" })

    return @(
        (New-ExecutorStep -Order 1 -Name "Regenerate and validate plan" -Targets @() -Action "read-only preflight")
        (New-ExecutorStep -Order 2 -Name "Delete App Pack zips" -Targets $AppPackTargets -Action "future delete")
        (New-ExecutorStep -Order 3 -Name "Delete strict staging targets" -Targets $StagingTargets -Action "future delete")
        (New-ExecutorStep -Order 4 -Name "Delete runtime app_env" -Targets $RuntimeTargets -Action "future delete")
        (New-ExecutorStep -Order 5 -Name "Delete app backup/history" -Targets $HistoryTargets -Action "future delete")
        (New-ExecutorStep -Order 6 -Name "Delete app source" -Targets $SourceTargets -Action "future delete")
        (New-ExecutorStep -Order 7 -Name "Remove app manifest entry" -Targets $ManifestTargets -Action "future manifest entry removal")
        (New-ExecutorStep -Order 8 -Name "Post-delete verification" -Targets @() -Action "diagnose, rebuild dry-run, verify_release, check_all")
    )
}

$PlanJson = (& $PlanScript -AppId $AppId -ProjectRoot $Root -DryRun -Json) | Out-String
$Plan = $PlanJson | ConvertFrom-Json
$DeleteTargets = @(Get-PlanValue -Object $Plan -Names @("delete_targets", "deleteTargets") -DefaultValue @())
$ExcludedTargets = @(Get-PlanValue -Object $Plan -Names @("excluded_targets", "excludedTargets") -DefaultValue @())
$Warnings = @(Get-PlanValue -Object $Plan -Names @("warnings") -DefaultValue @())
$BlockingReasons = @(Get-PlanValue -Object $Plan -Names @("blocking_reasons", "blockingReasons") -DefaultValue @())
$SafetyErrors = @(Test-PlanSafety -Plan $Plan)
$Steps = @(Get-OrderedDeleteSteps -Plan $Plan)

$Result = [ordered]@{
    app_id = $AppId
    mode = "dry_run"
    project_root = $Root
    apply_implemented = $false
    defaulted_to_dry_run = (-not $DryRun)
    plan_summary = [ordered]@{
        manifest_entry_exists = Get-PlanValue -Object $Plan -Names @("manifest_entry_exists", "manifestEntryExists") -DefaultValue $false
        manifest_enabled = Get-PlanValue -Object $Plan -Names @("manifest_enabled", "manifestEnabled") -DefaultValue $null
        manifest_version = Get-PlanValue -Object $Plan -Names @("manifest_version", "manifestVersion") -DefaultValue $null
        manifest_package = Get-PlanValue -Object $Plan -Names @("manifest_package", "manifestPackage") -DefaultValue $null
        delete_target_count = $DeleteTargets.Count
        excluded_target_count = $ExcludedTargets.Count
        warning_count = $Warnings.Count
        blocking_reason_count = $BlockingReasons.Count
        safety_error_count = $SafetyErrors.Count
    }
    delete_ordering = $Steps
    delete_targets = $DeleteTargets
    excluded_targets = $ExcludedTargets
    warnings = $Warnings
    blocking_reasons = $BlockingReasons
    safety_errors = $SafetyErrors
    note = "DryRun only. Apply is not implemented and no files were deleted."
}

if ($Json) {
    $Result | ConvertTo-Json -Depth 30
} else {
    Write-Host "Full delete executor dry-run for $AppId"
    if (-not $DryRun) {
        Write-Host "  mode was not specified; defaulting to DryRun."
    }
    Write-Host "  project root: $Root"
    Write-Host "  manifest entry: $($Result.plan_summary.manifest_entry_exists)"
    Write-Host "  version: $($Result.plan_summary.manifest_version)"
    Write-Host "  delete targets: $($Result.plan_summary.delete_target_count)"
    Write-Host "  excluded targets: $($Result.plan_summary.excluded_target_count)"
    Write-Host "  Apply is not implemented."
    Write-Host ""
    Write-Host "Delete ordering:"
    foreach ($Step in $Steps) {
        Write-Host "  $($Step.order). $($Step.name) [$($Step.action)] targets=$($Step.target_count)"
        foreach ($Target in @($Step.targets)) {
            Write-Host "     - [$($Target.category)] $($Target.action): $($Target.path) (exists=$($Target.exists))"
        }
    }
    Write-Host ""
    Write-Host "Excluded targets:"
    foreach ($Target in $ExcludedTargets) {
        Write-Host "  - [$($Target.category)] $($Target.action): $($Target.path) (exists=$($Target.exists))"
    }
    if ($Warnings.Count -gt 0) {
        Write-Host ""
        Write-Host "Warnings:"
        foreach ($Warning in $Warnings) { Write-Host "  - $Warning" }
    }
    if ($SafetyErrors.Count -gt 0) {
        Write-Host ""
        Write-Host "Safety errors:"
        foreach ($SafetyError in $SafetyErrors) { Write-Host "  - $SafetyError" }
    }
    Write-Host ""
    Write-Host "No files were deleted."
}

if ($SafetyErrors.Count -gt 0) {
    exit 1
}

if ($EffectiveDryRun) {
    exit 0
}
