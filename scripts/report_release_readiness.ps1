param(
    [switch]$Json
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$AppsDir = Join-Path $Root "apps"
$ReleaseDir = Join-Path $Root "release"
$RuntimeDir = Join-Path $Root "runtime"
$AppManifestPath = Join-Path $ReleaseDir "app_manifest.json"
$ReleaseManifestPath = Join-Path $ReleaseDir "manifest.json"
$AppPacksDir = Join-Path $ReleaseDir "app_packs"
$StagingDir = Join-Path $ReleaseDir "staging"
$Failed = $false

function Write-Line {
    param([string]$Message)
    if (-not $Json) {
        Write-Host $Message
    }
}

function Add-ListItem {
    param(
        [System.Collections.IDictionary]$Report,
        [string]$Name,
        [object]$Value
    )
    $Report[$Name] = @($Report[$Name]) + @($Value)
}

function Entry-Enabled {
    param([object]$Entry)
    if ($null -eq $Entry.PSObject.Properties["enabled"]) {
        return $true
    }
    return [bool]$Entry.enabled
}

function To-RelativePath {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) {
        return ""
    }

    $FullRoot = [System.IO.Path]::GetFullPath($Root).TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)
    $FullPath = [System.IO.Path]::GetFullPath($Path)
    if ($FullPath.StartsWith($FullRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $FullPath.Substring($FullRoot.Length).TrimStart([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar).Replace("\", "/")
    }
    return $FullPath
}

function New-ItemRecord {
    param(
        [string]$Category,
        [string]$Id,
        [string]$State,
        [string]$Reason,
        [string]$RecommendedAction,
        [string]$Path = "",
        [object[]]$WouldRemove = @(),
        [object[]]$Excluded = @(),
        [object[]]$PreCheck = @()
    )

    [ordered]@{
        category = $Category
        id = $Id
        state = $State
        reason = $Reason
        path = $Path
        would_remove = @($WouldRemove)
        excluded = @($Excluded)
        pre_check = @($PreCheck)
        recommended_action = $RecommendedAction
    }
}

function Read-JsonFile {
    param([string]$Path)
    try {
        return Get-Content -Raw -Encoding UTF8 $Path | ConvertFrom-Json
    } catch {
        Add-ListItem $Report "blocked_items" (New-ItemRecord -Category "blocked_items" -Id (To-RelativePath $Path) -State "invalid_json" -Reason "JSON could not be parsed." -RecommendedAction "Fix the JSON before release readiness cleanup can be trusted." -Path (To-RelativePath $Path))
        $script:Failed = $true
        return $null
    }
}

function Get-AppSourceIds {
    if (-not (Test-Path -LiteralPath $AppsDir -PathType Container)) {
        return @()
    }
    return @(Get-ChildItem -LiteralPath $AppsDir -Directory -ErrorAction SilentlyContinue |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "app.yaml") -PathType Leaf } |
        ForEach-Object { $_.Name } |
        Sort-Object)
}

function Get-AppPackTargets {
    param(
        [string]$AppId,
        [object]$Entry
    )

    $Targets = @()
    if ($Entry -and $Entry.package) {
        $Targets += Join-Path $ReleaseDir ([string]$Entry.package)
    }
    if (Test-Path -LiteralPath $AppPacksDir -PathType Container) {
        $Targets += @(Get-ChildItem -LiteralPath $AppPacksDir -File -Filter "$AppId-*.zip" -ErrorAction SilentlyContinue |
            ForEach-Object { $_.FullName })
    }
    return @($Targets | Where-Object { $_ } | Sort-Object -Unique)
}

function Get-StrictStagingTargets {
    param(
        [string]$AppId,
        [string]$Version
    )

    if (-not (Test-Path -LiteralPath $StagingDir -PathType Container)) {
        return @()
    }

    $Targets = @()
    foreach ($Item in @(Get-ChildItem -LiteralPath $StagingDir -Force -ErrorAction SilentlyContinue)) {
        $Segments = @($Item.FullName.Substring($StagingDir.Length).TrimStart("\", "/") -split "[\\/]+" | Where-Object { $_ })
        $Matches = $false
        foreach ($Segment in $Segments) {
            if ($Segment -eq $AppId) {
                $Matches = $true
                break
            }
            if (-not [string]::IsNullOrWhiteSpace($Version)) {
                $VersionPrefix = "$AppId-$Version"
                if ($Segment -eq $VersionPrefix -or $Segment.StartsWith("$VersionPrefix.", [System.StringComparison]::OrdinalIgnoreCase) -or $Segment.StartsWith("$VersionPrefix-", [System.StringComparison]::OrdinalIgnoreCase)) {
                    $Matches = $true
                    break
                }
            }
        }
        if ($Matches) {
            $Targets += $Item.FullName
        }
    }
    return @($Targets | Sort-Object -Unique)
}

function Get-BackupTargets {
    param([string]$AppId)

    $Targets = @()
    foreach ($Base in @("backups\app_studio", "backups\app_lifecycle")) {
        $BasePath = Join-Path $Root $Base
        if (Test-Path -LiteralPath $BasePath -PathType Container) {
            $Targets += @(Get-ChildItem -LiteralPath $BasePath -Recurse -Directory -Filter $AppId -ErrorAction SilentlyContinue |
                ForEach-Object { $_.FullName })
        }
    }
    return @($Targets | Sort-Object -Unique)
}

function Add-AppPackClassification {
    param(
        [string]$AppId,
        [object]$Entry,
        [bool]$HasSource,
        [bool]$IsStaleDeleteCandidate
    )

    $PackagePath = if ($Entry -and $Entry.package) { Join-Path $ReleaseDir ([string]$Entry.package) } else { "" }
    if (-not $HasSource -or $IsStaleDeleteCandidate) {
        return
    }

    if ([string]::IsNullOrWhiteSpace($PackagePath) -or -not (Test-Path -LiteralPath $PackagePath -PathType Leaf)) {
        Add-ListItem $Report "app_pack_rebuild_candidates" (New-ItemRecord -Category "app_pack_rebuild_candidates" -Id $AppId -State "package_missing" -Reason "App source exists, but the manifest package zip is not present in this checkout." -RecommendedAction "Regenerate the App Pack for this app before formal release checks." -Path (To-RelativePath $PackagePath))
        return
    }

    if ([string]::IsNullOrWhiteSpace([string]$Entry.sha256)) {
        Add-ListItem $Report "app_pack_rebuild_candidates" (New-ItemRecord -Category "app_pack_rebuild_candidates" -Id $AppId -State "sha256_empty" -Reason "App Pack exists but app_manifest sha256 is empty." -RecommendedAction "Regenerate or repackage the App Pack so sha256 is recorded." -Path (To-RelativePath $PackagePath))
        return
    }

    $ActualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $PackagePath).Hash.ToLowerInvariant()
    if ($ActualHash -ne [string]$Entry.sha256) {
        Add-ListItem $Report "blocked_items" (New-ItemRecord -Category "blocked_items" -Id $AppId -State "sha256_mismatch" -Reason "App Pack exists but sha256 does not match release/app_manifest.json." -RecommendedAction "Regenerate the App Pack or update the manifest through the packaging flow." -Path (To-RelativePath $PackagePath))
    }
}

$Report = [ordered]@{
    generated_at = (Get-Date).ToString("s")
    project_root = $Root
    summary = [ordered]@{}
    app_manifest = [ordered]@{
        path = To-RelativePath $AppManifestPath
        enabled_with_source = @()
        enabled_missing_source = @()
        disabled_with_source = @()
        disabled_stale = @()
        source_missing_from_manifest = @()
    }
    delete_candidates = @()
    hide_candidates = @()
    app_pack_rebuild_candidates = @()
    runtime_packaging_required = @()
    installer_build_required = @()
    docs_check_adjustment_candidates = @()
    intentional_warnings = @()
    blocked_items = @()
}

if (-not (Test-Path -LiteralPath $AppManifestPath -PathType Leaf)) {
    Add-ListItem $Report "blocked_items" (New-ItemRecord -Category "blocked_items" -Id "release/app_manifest.json" -State "missing" -Reason "App manifest is missing." -RecommendedAction "Restore or regenerate release/app_manifest.json before cleanup." -Path "release/app_manifest.json")
    $Failed = $true
}
if (-not (Test-Path -LiteralPath $ReleaseManifestPath -PathType Leaf)) {
    Add-ListItem $Report "blocked_items" (New-ItemRecord -Category "blocked_items" -Id "release/manifest.json" -State "missing" -Reason "Release manifest is missing." -RecommendedAction "Restore release/manifest.json before release readiness cleanup." -Path "release/manifest.json")
    $Failed = $true
}

$AppManifest = if (Test-Path -LiteralPath $AppManifestPath -PathType Leaf) { Read-JsonFile $AppManifestPath } else { $null }
$ReleaseManifest = if (Test-Path -LiteralPath $ReleaseManifestPath -PathType Leaf) { Read-JsonFile $ReleaseManifestPath } else { $null }

$ManifestProps = @()
if ($AppManifest -and $AppManifest.apps) {
    $ManifestProps = @($AppManifest.apps.PSObject.Properties | Sort-Object Name)
}
$ManifestIds = @($ManifestProps | ForEach-Object { $_.Name })
$SourceIds = Get-AppSourceIds

foreach ($Prop in $ManifestProps) {
    $AppId = $Prop.Name
    $Entry = $Prop.Value
    $Enabled = Entry-Enabled $Entry
    $AppYamlPath = Join-Path (Join-Path $AppsDir $AppId) "app.yaml"
    $HasSource = Test-Path -LiteralPath $AppYamlPath -PathType Leaf
    $Version = [string]$Entry.version

    if ($Enabled -and $HasSource) {
        $Report.app_manifest.enabled_with_source += $AppId
    } elseif ($Enabled -and -not $HasSource) {
        $Report.app_manifest.enabled_missing_source += $AppId
        Add-ListItem $Report "hide_candidates" (New-ItemRecord -Category "hide_candidates" -Id $AppId -State "enabled_missing_source" -Reason "The launcher can consider this app enabled, but its app source is missing." -RecommendedAction "Immediately restore source or hide it with enabled=false; only full-delete after ownership is confirmed." -Path (To-RelativePath $AppYamlPath))
        Add-ListItem $Report "blocked_items" (New-ItemRecord -Category "blocked_items" -Id $AppId -State "enabled_missing_source" -Reason "Enabled manifest entry has no app source." -RecommendedAction "This must be resolved before formal release." -Path (To-RelativePath $AppYamlPath))
    } elseif ((-not $Enabled) -and $HasSource) {
        $Report.app_manifest.disabled_with_source += $AppId
        Add-ListItem $Report "intentional_warnings" (New-ItemRecord -Category "intentional_warnings" -Id $AppId -State "disabled_with_source" -Reason "App source exists but manifest enabled=false. This is a valid hidden/reviewable state." -RecommendedAction "Keep hidden, show again, or full-delete only after business ownership is confirmed." -Path (To-RelativePath $AppYamlPath))
    } else {
        $Report.app_manifest.disabled_stale += $AppId
        $PackTargets = @(Get-AppPackTargets -AppId $AppId -Entry $Entry | ForEach-Object { To-RelativePath $_ })
        $StagingTargets = @(Get-StrictStagingTargets -AppId $AppId -Version $Version | ForEach-Object { To-RelativePath $_ })
        $RuntimeAppEnv = To-RelativePath (Join-Path (Join-Path $RuntimeDir "app_envs") $AppId)
        $BackupTargets = @(Get-BackupTargets -AppId $AppId | ForEach-Object { To-RelativePath $_ })
        $WouldRemove = @(
            "release/app_manifest.json entry:$AppId",
            $RuntimeAppEnv
        ) + $PackTargets + $StagingTargets + $BackupTargets
        $WouldRemove = @($WouldRemove | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) } | Sort-Object -Unique)
        Add-ListItem $Report "delete_candidates" (New-ItemRecord -Category "delete_candidates" -Id $AppId -State "disabled_stale" -Reason "Manifest has enabled=false and apps/<app_id>/app.yaml is missing. This is stale release index/history, not an active app source." -RecommendedAction "Have the owner confirm it is not needed, then remove through full delete; otherwise keep disabled as intentional history." -Path (To-RelativePath $AppYamlPath) -WouldRemove $WouldRemove -Excluded @("external source/output mirror", "user data/logs/browser profiles/app_state", "shared runtime") -PreCheck @("Confirm the app is not needed.", "Confirm there is no app source to restore.", "Confirm App Pack/staging/runtime app_env/backups are app-owned if present."))
    }

    Add-AppPackClassification -AppId $AppId -Entry $Entry -HasSource $HasSource -IsStaleDeleteCandidate ((-not $Enabled) -and (-not $HasSource))

    if ($HasSource) {
        $AppEnvPath = Join-Path (Join-Path $RuntimeDir "app_envs") $AppId
        if (-not (Test-Path -LiteralPath $AppEnvPath -PathType Container)) {
            Add-ListItem $Report "intentional_warnings" (New-ItemRecord -Category "intentional_warnings" -Id $AppId -State "app_env_missing" -Reason "verify_release warns that runtime/app_envs/<app_id> is missing. Current normal App Studio frozen-folder registration does not use app_env as the app source of truth." -RecommendedAction "Do not delete the app for this. Revisit only if an app-env execution mode is intentionally revived." -Path (To-RelativePath $AppEnvPath))
            Add-ListItem $Report "docs_check_adjustment_candidates" (New-ItemRecord -Category "docs_check_adjustment_candidates" -Id $AppId -State "strict_app_env_policy" -Reason "verify_release.ps1 -Strict currently escalates missing runtime/app_envs/<app_id> to NG, while normal App Studio frozen-folder apps do not use app_env." -RecommendedAction "Before formal strict release, decide whether strict verification should keep app_env as a fail, downgrade it for frozen-folder apps, or require explicit app-env metadata." -Path (To-RelativePath $AppEnvPath))
        }
    }
}

foreach ($SourceId in $SourceIds) {
    if ($ManifestIds -notcontains $SourceId) {
        $AppYamlPath = Join-Path (Join-Path $AppsDir $SourceId) "app.yaml"
        $Report.app_manifest.source_missing_from_manifest += $SourceId
        Add-ListItem $Report "blocked_items" (New-ItemRecord -Category "blocked_items" -Id $SourceId -State "source_missing_from_manifest" -Reason "apps/<app_id>/app.yaml exists but release/app_manifest.json has no entry." -RecommendedAction "Regenerate/rebuild app_manifest or explicitly decide whether this source should be full-deleted." -Path (To-RelativePath $AppYamlPath))
    }
}

$PythonExe = Join-Path (Join-Path $RuntimeDir "python") "python.exe"
if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    Add-ListItem $Report "runtime_packaging_required" (New-ItemRecord -Category "runtime_packaging_required" -Id "python-runtime" -State "python_runtime_missing" -Reason "Shared Python runtime executable is not bundled." -RecommendedAction "Place an approved Python runtime archive locally and run prepare_runtime.ps1 -PythonArchive <zip> -PythonSha256 <sha256>; do not resolve this by deleting apps." -Path (To-RelativePath $PythonExe))
}

$WebRuntimeDir = Join-Path $RuntimeDir "web_automation_runtime"
$WebRuntimeFiles = @()
if (Test-Path -LiteralPath $WebRuntimeDir -PathType Container) {
    $WebRuntimeFiles = @(Get-ChildItem -LiteralPath $WebRuntimeDir -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notin @(".gitkeep", "README.md") })
}
if ($WebRuntimeFiles.Count -eq 0) {
    Add-ListItem $Report "runtime_packaging_required" (New-ItemRecord -Category "runtime_packaging_required" -Id "web-automation-runtime" -State "web_runtime_missing" -Reason "Shared web automation runtime files are not bundled." -RecommendedAction "Place an approved web automation runtime archive locally and run prepare_runtime.ps1 -WebRuntimeArchive <zip> -WebRuntimeSha256 <sha256>; do not resolve this by deleting apps." -Path (To-RelativePath $WebRuntimeDir))
}

if ($ReleaseManifest -and $ReleaseManifest.toolhub -and $ReleaseManifest.toolhub.installer -and $ReleaseManifest.toolhub.installer.file) {
    $InstallerPath = Join-Path (Join-Path $ReleaseDir "dist_installer") ([string]$ReleaseManifest.toolhub.installer.file)
    if (-not (Test-Path -LiteralPath $InstallerPath -PathType Leaf)) {
        Add-ListItem $Report "installer_build_required" (New-ItemRecord -Category "installer_build_required" -Id "toolhub-installer" -State "missing" -Reason "release/manifest.json points to an installer that is not present in release/dist_installer." -RecommendedAction "Resolve through installer/release build, not app deletion." -Path (To-RelativePath $InstallerPath))
    }
} else {
    Add-ListItem $Report "blocked_items" (New-ItemRecord -Category "blocked_items" -Id "toolhub-installer" -State "manifest_missing_installer_file" -Reason "release/manifest.json does not define toolhub.installer.file." -RecommendedAction "Fix release/manifest.json before formal release.")
}

$StageManifest = Join-Path $StagingDir "installer_payload\staging_manifest.json"
if (-not (Test-Path -LiteralPath $StageManifest -PathType Leaf)) {
    Add-ListItem $Report "installer_build_required" (New-ItemRecord -Category "installer_build_required" -Id "installer-staging-manifest" -State "missing" -Reason "Installer staging manifest is not present." -RecommendedAction "Resolve through installer/release build, not app deletion." -Path (To-RelativePath $StageManifest))
}

$Link = Get-Command "link.exe" -ErrorAction SilentlyContinue
$Cl = Get-Command "cl.exe" -ErrorAction SilentlyContinue
if (-not $Link) {
    Add-ListItem $Report "blocked_items" (New-ItemRecord -Category "blocked_items" -Id "msvc-linker" -State "not_detected" -Reason "Visual Studio C++ linker link.exe was not found in this shell." -RecommendedAction "Use Developer PowerShell or install Visual Studio Build Tools with C++ workload before local Tauri release builds.")
}
if (-not $Cl) {
    Add-ListItem $Report "blocked_items" (New-ItemRecord -Category "blocked_items" -Id "msvc-compiler" -State "not_detected" -Reason "Visual Studio C++ compiler cl.exe was not found in this shell." -RecommendedAction "Use Developer PowerShell or install Visual Studio Build Tools with C++ workload before local Tauri release builds.")
}

$Report.summary = [ordered]@{
    manifest_entries = @($ManifestIds).Count
    app_sources = @($SourceIds).Count
    enabled_with_source = @($Report.app_manifest.enabled_with_source).Count
    enabled_missing_source = @($Report.app_manifest.enabled_missing_source).Count
    disabled_with_source = @($Report.app_manifest.disabled_with_source).Count
    disabled_stale = @($Report.app_manifest.disabled_stale).Count
    source_missing_from_manifest = @($Report.app_manifest.source_missing_from_manifest).Count
    delete_candidates = @($Report.delete_candidates).Count
    hide_candidates = @($Report.hide_candidates).Count
    app_pack_rebuild_candidates = @($Report.app_pack_rebuild_candidates).Count
    runtime_packaging_required = @($Report.runtime_packaging_required).Count
    installer_build_required = @($Report.installer_build_required).Count
    docs_check_adjustment_candidates = @($Report.docs_check_adjustment_candidates).Count
    intentional_warnings = @($Report.intentional_warnings).Count
    blocked_items = @($Report.blocked_items).Count
}

if ($Json) {
    $Report | ConvertTo-Json -Depth 16
    if ($Failed) { exit 1 }
    exit 0
}

Write-Line "== Release readiness cleanup report =="
Write-Line "manifest entries: $($Report.summary.manifest_entries)"
Write-Line "app sources: $($Report.summary.app_sources)"
Write-Line "enabled with source: $($Report.summary.enabled_with_source)"
Write-Line "disabled with source: $($Report.summary.disabled_with_source)"
Write-Line "disabled stale: $($Report.summary.disabled_stale)"
Write-Line "source missing from manifest: $($Report.summary.source_missing_from_manifest)"
Write-Line ""
Write-Line "delete_candidates: $($Report.summary.delete_candidates)"
foreach ($Item in @($Report.delete_candidates)) {
    Write-Line "  - $($Item.id): $($Item.reason)"
}
Write-Line "hide_candidates: $($Report.summary.hide_candidates)"
foreach ($Item in @($Report.hide_candidates)) {
    Write-Line "  - $($Item.id): $($Item.reason)"
}
Write-Line "app_pack_rebuild_candidates: $($Report.summary.app_pack_rebuild_candidates)"
foreach ($Item in @($Report.app_pack_rebuild_candidates)) {
    Write-Line "  - $($Item.id): $($Item.path)"
}
Write-Line "runtime_packaging_required: $($Report.summary.runtime_packaging_required)"
foreach ($Item in @($Report.runtime_packaging_required)) {
    Write-Line "  - $($Item.id): $($Item.reason)"
}
Write-Line "installer_build_required: $($Report.summary.installer_build_required)"
foreach ($Item in @($Report.installer_build_required)) {
    Write-Line "  - $($Item.id): $($Item.reason)"
}
Write-Line "docs_check_adjustment_candidates: $($Report.summary.docs_check_adjustment_candidates)"
foreach ($Item in @($Report.docs_check_adjustment_candidates)) {
    Write-Line "  - $($Item.id): $($Item.reason)"
}
Write-Line "intentional_warnings: $($Report.summary.intentional_warnings)"
Write-Line "blocked_items: $($Report.summary.blocked_items)"
foreach ($Item in @($Report.blocked_items)) {
    Write-Line "  - $($Item.id): $($Item.reason)"
}
Write-Line ""
Write-Line "No files were changed. Use -Json for machine-readable details."

if ($Failed) {
    exit 1
}
exit 0
