param(
    [Parameter(Mandatory = $true)]
    [string]$AppId,
    [string]$ProjectRoot,
    [switch]$DryRun,
    [switch]$Apply,
    [switch]$AllowTemporaryAppApply,
    [switch]$Json
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

if ($DryRun -and $Apply) {
    throw "Specify only one mode: -DryRun or -Apply."
}

$ProjectRootWasSpecified = -not [string]::IsNullOrWhiteSpace($ProjectRoot)
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Root = if ($ProjectRootWasSpecified) {
    (Resolve-Path -LiteralPath $ProjectRoot).Path
} else {
    $RepoRoot
}
$EffectiveDryRun = -not $Apply
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

function Test-SamePath {
    param(
        [string]$Left,
        [string]$Right
    )
    try {
        $LeftFull = [System.IO.Path]::GetFullPath($Left).TrimEnd("\", "/")
        $RightFull = [System.IO.Path]::GetFullPath($Right).TrimEnd("\", "/")
    } catch {
        return $false
    }
    return $LeftFull.Equals($RightFull, [System.StringComparison]::OrdinalIgnoreCase)
}

function Test-PathUnderDirectory {
    param(
        [string]$Path,
        [string]$BaseDirectory
    )
    try {
        $Full = [System.IO.Path]::GetFullPath($Path).TrimEnd("\", "/")
        $Base = [System.IO.Path]::GetFullPath($BaseDirectory).TrimEnd("\", "/")
    } catch {
        return $false
    }
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

function New-ExecutionRecord {
    param(
        [object]$Target,
        [string]$Status,
        [string]$Note = ""
    )
    return [ordered]@{
        category = [string](Get-PlanValue -Object $Target -Names @("category") -DefaultValue "")
        action = [string](Get-PlanValue -Object $Target -Names @("action") -DefaultValue "")
        path = [string](Get-PlanValue -Object $Target -Names @("path") -DefaultValue "")
        normalized_path = [string](Get-PlanValue -Object $Target -Names @("normalized_path", "normalizedPath") -DefaultValue "")
        comparison_key = [string](Get-PlanValue -Object $Target -Names @("comparison_key", "comparisonKey") -DefaultValue "")
        status = $Status
        note = $Note
    }
}

function Test-PlanSafety {
    param([object]$Plan)

    $Errors = New-Object System.Collections.ArrayList
    $DeleteTargets = @(Get-PlanValue -Object $Plan -Names @("delete_targets", "deleteTargets") -DefaultValue @())
    $ExcludedTargets = @(Get-PlanValue -Object $Plan -Names @("excluded_targets", "excludedTargets") -DefaultValue @())
    $ForbiddenDeleteCategories = @("external_reference", "user_data", "shared_runtime", "managed_generated_candidate")
    $DeleteNormalizedPaths = @{}

    foreach ($Target in $DeleteTargets) {
        $DeleteAllowed = [bool](Get-PlanValue -Object $Target -Names @("delete_allowed", "deleteAllowed") -DefaultValue $false)
        $Path = [string](Get-PlanValue -Object $Target -Names @("path") -DefaultValue "")
        $Action = [string](Get-PlanValue -Object $Target -Names @("action") -DefaultValue "")
        $Normalized = [string](Get-PlanValue -Object $Target -Names @("normalized_path", "normalizedPath") -DefaultValue "")
        if (-not [string]::IsNullOrWhiteSpace($Normalized)) {
            $DeleteNormalizedPaths[$Normalized] = $true
        }
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
        $Normalized = [string](Get-PlanValue -Object $Target -Names @("normalized_path", "normalizedPath") -DefaultValue "")
        if ($DeleteAllowed) {
            [void]$Errors.Add("Excluded target must be delete_allowed=false: $Path")
        }
        if (-not [string]::IsNullOrWhiteSpace($Normalized) -and $DeleteNormalizedPaths.Contains($Normalized)) {
            [void]$Errors.Add("Excluded target overlaps a delete target: $Path")
        }
    }

    return @($Errors)
}

function Test-TemporaryApplyGate {
    $Errors = New-Object System.Collections.ArrayList
    if (-not $Apply) { return @($Errors) }

    if (-not $AllowTemporaryAppApply) {
        [void]$Errors.Add("Apply requires -AllowTemporaryAppApply in Phase 4.")
    }
    if (-not $ProjectRootWasSpecified) {
        [void]$Errors.Add("Apply requires an explicit -ProjectRoot fixture path.")
    }
    if (Test-SamePath -Left $Root -Right $RepoRoot) {
        [void]$Errors.Add("Apply is refused for the production repository root.")
    }
    $TempRoot = [System.IO.Path]::GetTempPath()
    if (-not (Test-PathUnderDirectory -Path $Root -BaseDirectory $TempRoot)) {
        [void]$Errors.Add("Apply is allowed only for a fixture root under the system temp directory.")
    }
    if ($AppId -notmatch "^(__delete_e2e_|delete_e2e_)[A-Za-z0-9_.-]+$") {
        [void]$Errors.Add("Apply is allowed only for temporary app ids beginning with __delete_e2e_ or delete_e2e_.")
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

function Invoke-DeleteTarget {
    param([object]$Target)

    $Path = [string](Get-PlanValue -Object $Target -Names @("path") -DefaultValue "")
    $Action = [string](Get-PlanValue -Object $Target -Names @("action") -DefaultValue "")
    if ($Action -eq "remove app_manifest entry") {
        return New-ExecutionRecord -Target $Target -Status "skipped" -Note "Manifest entry removal is handled as JSON mutation."
    }
    if (-not (Test-PathInsideRoot -Path $Path -RootPath $Root)) {
        return New-ExecutionRecord -Target $Target -Status "failed" -Note "Refused path outside fixture root."
    }
    if (-not (Test-Path -LiteralPath $Path)) {
        return New-ExecutionRecord -Target $Target -Status "already_clean" -Note "Target was already missing."
    }

    try {
        Remove-Item -LiteralPath $Path -Recurse -Force
        if (Test-Path -LiteralPath $Path) {
            return New-ExecutionRecord -Target $Target -Status "failed" -Note "Target still exists after deletion attempt."
        }
        return New-ExecutionRecord -Target $Target -Status "deleted" -Note "Deleted inside temporary fixture root."
    } catch {
        return New-ExecutionRecord -Target $Target -Status "failed" -Note $_.Exception.Message
    }
}

function Invoke-ManifestEntryRemoval {
    param([object[]]$ManifestTargets)

    $Records = New-Object System.Collections.ArrayList
    if (@($ManifestTargets).Count -eq 0) {
        return [ordered]@{
            records = @()
            manifest_entry_removed = $false
            manifest_json_valid = $false
            manifest_entry_present = $null
            failed = @("No manifest entry target was present in the plan.")
        }
    }

    $Target = @($ManifestTargets)[0]
    $ManifestPath = [string](Get-PlanValue -Object $Target -Names @("path") -DefaultValue "")
    if (-not (Test-PathInsideRoot -Path $ManifestPath -RootPath $Root)) {
        [void]$Records.Add((New-ExecutionRecord -Target $Target -Status "failed" -Note "Manifest path is outside fixture root."))
        return [ordered]@{
            records = @($Records | ForEach-Object { $_ })
            manifest_entry_removed = $false
            manifest_json_valid = $false
            manifest_entry_present = $null
            failed = @("Manifest path is outside fixture root.")
        }
    }
    if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
        [void]$Records.Add((New-ExecutionRecord -Target $Target -Status "failed" -Note "Manifest file is missing."))
        return [ordered]@{
            records = @($Records | ForEach-Object { $_ })
            manifest_entry_removed = $false
            manifest_json_valid = $false
            manifest_entry_present = $null
            failed = @("Manifest file is missing.")
        }
    }

    try {
        $Manifest = Get-Content -Raw -Encoding UTF8 $ManifestPath | ConvertFrom-Json
        $EntryExists = $Manifest.apps -and $Manifest.apps.PSObject.Properties[$AppId]
        if ($EntryExists) {
            $Manifest.apps.PSObject.Properties.Remove($AppId)
            $JsonText = $Manifest | ConvertTo-Json -Depth 20
            [System.IO.File]::WriteAllText($ManifestPath, $JsonText, [System.Text.UTF8Encoding]::new($false))
            [void]$Records.Add((New-ExecutionRecord -Target $Target -Status "deleted" -Note "Removed only the app entry from release/app_manifest.json."))
        } else {
            [void]$Records.Add((New-ExecutionRecord -Target $Target -Status "already_clean" -Note "Manifest entry was already absent."))
        }

        $AfterManifest = Get-Content -Raw -Encoding UTF8 $ManifestPath | ConvertFrom-Json
        $EntryPresentAfter = [bool]($AfterManifest.apps -and $AfterManifest.apps.PSObject.Properties[$AppId])
        return [ordered]@{
            records = @($Records | ForEach-Object { $_ })
            manifest_entry_removed = [bool]$EntryExists
            manifest_json_valid = $true
            manifest_entry_present = $EntryPresentAfter
            failed = if ($EntryPresentAfter) { @("Manifest entry is still present after removal.") } else { @() }
        }
    } catch {
        [void]$Records.Add((New-ExecutionRecord -Target $Target -Status "failed" -Note $_.Exception.Message))
        return [ordered]@{
            records = @($Records | ForEach-Object { $_ })
            manifest_entry_removed = $false
            manifest_json_valid = $false
            manifest_entry_present = $null
            failed = @($_.Exception.Message)
        }
    }
}

function Invoke-TemporaryApply {
    param(
        [object]$Plan,
        [object[]]$OrderedSteps
    )

    $Deleted = New-Object System.Collections.ArrayList
    $AlreadyClean = New-Object System.Collections.ArrayList
    $Skipped = New-Object System.Collections.ArrayList
    $Failed = New-Object System.Collections.ArrayList

    foreach ($Step in @($OrderedSteps | Where-Object { $_.order -ge 2 -and $_.order -le 6 } | Sort-Object -Property order)) {
        foreach ($Target in @($Step.targets)) {
            $Record = Invoke-DeleteTarget -Target $Target
            switch ($Record.status) {
                "deleted" { [void]$Deleted.Add($Record) }
                "already_clean" { [void]$AlreadyClean.Add($Record) }
                "skipped" { [void]$Skipped.Add($Record) }
                default { [void]$Failed.Add($Record) }
            }
        }
    }

    $ManifestTargets = @(@($OrderedSteps | Where-Object { $_.order -eq 7 })[0].targets)
    $ManifestResult = Invoke-ManifestEntryRemoval -ManifestTargets $ManifestTargets
    foreach ($Record in @($ManifestResult.records)) {
        switch ($Record.status) {
            "deleted" { [void]$Deleted.Add($Record) }
            "already_clean" { [void]$AlreadyClean.Add($Record) }
            "skipped" { [void]$Skipped.Add($Record) }
            default { [void]$Failed.Add($Record) }
        }
    }
    foreach ($Failure in @($ManifestResult.failed)) {
        if (-not [string]::IsNullOrWhiteSpace([string]$Failure)) {
            [void]$Failed.Add([ordered]@{ status = "failed"; note = [string]$Failure })
        }
    }

    $OriginalDeleteTargets = @(Get-PlanValue -Object $Plan -Names @("delete_targets", "deleteTargets") -DefaultValue @())
    $RemainingFileTargets = @()
    foreach ($Target in $OriginalDeleteTargets) {
        $Action = [string](Get-PlanValue -Object $Target -Names @("action") -DefaultValue "")
        if ($Action -eq "remove app_manifest entry") { continue }
        $Path = [string](Get-PlanValue -Object $Target -Names @("path") -DefaultValue "")
        if (Test-Path -LiteralPath $Path) {
            $RemainingFileTargets += $Path
        }
    }

    $FreshPlan = $null
    try {
        $FreshJson = (& $PlanScript -AppId $AppId -ProjectRoot $Root -DryRun -Json) | Out-String
        $FreshPlan = $FreshJson | ConvertFrom-Json
    } catch {
        [void]$Failed.Add([ordered]@{ status = "failed"; note = "Post-check plan regeneration failed: $($_.Exception.Message)" })
    }

    return [ordered]@{
        deleted = @($Deleted | ForEach-Object { $_ })
        already_clean = @($AlreadyClean | ForEach-Object { $_ })
        skipped = @($Skipped | ForEach-Object { $_ })
        failed = @($Failed | ForEach-Object { $_ })
        manifest_entry_removed = [bool]$ManifestResult.manifest_entry_removed
        post_check_summary = [ordered]@{
            manifest_json_valid = [bool]$ManifestResult.manifest_json_valid
            manifest_entry_present = $ManifestResult.manifest_entry_present
            remaining_file_delete_targets = @($RemainingFileTargets)
            fresh_plan_delete_target_count = if ($FreshPlan) { @($FreshPlan.delete_targets).Count } else { $null }
            fresh_plan_excluded_target_count = if ($FreshPlan) { @($FreshPlan.excluded_targets).Count } else { $null }
            fresh_plan_warnings = if ($FreshPlan) { @($FreshPlan.warnings) } else { @() }
        }
    }
}

$PlanJson = (& $PlanScript -AppId $AppId -ProjectRoot $Root -DryRun -Json) | Out-String
$Plan = $PlanJson | ConvertFrom-Json
$DeleteTargets = @(Get-PlanValue -Object $Plan -Names @("delete_targets", "deleteTargets") -DefaultValue @())
$ExcludedTargets = @(Get-PlanValue -Object $Plan -Names @("excluded_targets", "excludedTargets") -DefaultValue @())
$Warnings = @(Get-PlanValue -Object $Plan -Names @("warnings") -DefaultValue @())
$BlockingReasons = @(Get-PlanValue -Object $Plan -Names @("blocking_reasons", "blockingReasons") -DefaultValue @())
$SafetyErrors = @(Test-PlanSafety -Plan $Plan)
$ApplyGateErrors = @(Test-TemporaryApplyGate)
$AllSafetyErrors = @($SafetyErrors + $ApplyGateErrors)
$Steps = @(Get-OrderedDeleteSteps -Plan $Plan)
$ApplyResult = $null
if ($Apply -and $AllSafetyErrors.Count -eq 0) {
    $ApplyResult = Invoke-TemporaryApply -Plan $Plan -OrderedSteps $Steps
    if (@($ApplyResult.failed).Count -gt 0) {
        $AllSafetyErrors += @($ApplyResult.failed | ForEach-Object { [string](Get-PlanValue -Object $_ -Names @("note") -DefaultValue "Apply step failed.") })
    }
}

$Result = [ordered]@{
    app_id = $AppId
    mode = if ($Apply) { "apply" } else { "dry_run" }
    project_root = $Root
    apply_implemented = [bool]($Apply -and $AllowTemporaryAppApply)
    temporary_apply = [bool]($Apply -and $AllowTemporaryAppApply)
    defaulted_to_dry_run = (-not $DryRun -and -not $Apply)
    plan_summary = [ordered]@{
        manifest_entry_exists = Get-PlanValue -Object $Plan -Names @("manifest_entry_exists", "manifestEntryExists") -DefaultValue $false
        manifest_enabled = Get-PlanValue -Object $Plan -Names @("manifest_enabled", "manifestEnabled") -DefaultValue $null
        manifest_version = Get-PlanValue -Object $Plan -Names @("manifest_version", "manifestVersion") -DefaultValue $null
        manifest_package = Get-PlanValue -Object $Plan -Names @("manifest_package", "manifestPackage") -DefaultValue $null
        delete_target_count = $DeleteTargets.Count
        excluded_target_count = $ExcludedTargets.Count
        warning_count = $Warnings.Count
        blocking_reason_count = $BlockingReasons.Count
        safety_error_count = $AllSafetyErrors.Count
    }
    delete_ordering = $Steps
    delete_targets = $DeleteTargets
    excluded_targets = $ExcludedTargets
    excluded = $ExcludedTargets
    warnings = $Warnings
    blocking_reasons = $BlockingReasons
    safety_errors = $AllSafetyErrors
    deleted = if ($ApplyResult) { @($ApplyResult.deleted | Where-Object { $null -ne $_ }) } else { @() }
    already_clean = if ($ApplyResult) { @($ApplyResult.already_clean | Where-Object { $null -ne $_ }) } else { @() }
    skipped = if ($ApplyResult) { @($ApplyResult.skipped | Where-Object { $null -ne $_ }) } else { @() }
    failed = if ($ApplyResult) { @($ApplyResult.failed | Where-Object { $null -ne $_ }) } else { @() }
    manifest_entry_removed = if ($ApplyResult) { [bool]$ApplyResult.manifest_entry_removed } else { $false }
    post_check_summary = if ($ApplyResult) { $ApplyResult.post_check_summary } else { [ordered]@{} }
    note = if ($Apply) { "Temporary fixture Apply only. Production full delete is not implemented." } else { "DryRun only. No files were deleted." }
}

if ($Json) {
    $Result | ConvertTo-Json -Depth 30
} else {
    Write-Host "Full delete executor $($Result.mode) for $AppId"
    if (-not $DryRun -and -not $Apply) {
        Write-Host "  mode was not specified; defaulting to DryRun."
    }
    Write-Host "  project root: $Root"
    Write-Host "  manifest entry: $($Result.plan_summary.manifest_entry_exists)"
    Write-Host "  version: $($Result.plan_summary.manifest_version)"
    Write-Host "  delete targets: $($Result.plan_summary.delete_target_count)"
    Write-Host "  excluded targets: $($Result.plan_summary.excluded_target_count)"
    Write-Host "  production Apply is not implemented."
    if ($Apply) {
        Write-Host "  temporary Apply gate: $([bool]$AllowTemporaryAppApply)"
    }
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
    if ($AllSafetyErrors.Count -gt 0) {
        Write-Host ""
        Write-Host "Safety errors:"
        foreach ($SafetyError in $AllSafetyErrors) { Write-Host "  - $SafetyError" }
    }
    if ($ApplyResult) {
        Write-Host ""
        Write-Host "Apply result:"
        Write-Host "  deleted: $(@($ApplyResult.deleted).Count)"
        Write-Host "  already clean: $(@($ApplyResult.already_clean).Count)"
        Write-Host "  skipped: $(@($ApplyResult.skipped).Count)"
        Write-Host "  failed: $(@($ApplyResult.failed).Count)"
        Write-Host "  manifest entry removed: $($ApplyResult.manifest_entry_removed)"
    }
    Write-Host ""
    if ($Apply -and $AllSafetyErrors.Count -eq 0) {
        Write-Host "Apply was limited to the temporary fixture root."
    } else {
        Write-Host "No files were deleted."
    }
}

if ($AllSafetyErrors.Count -gt 0) {
    exit 1
}

if ($EffectiveDryRun) {
    exit 0
}

exit 0
