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
$DefaultLauncherConfigPath = Join-Path $Root "config.default\launcher.yaml"
$TauriConfigPath = Join-Path $Root "launcher\src-tauri\tauri.conf.json"
$CommandsPath = Join-Path $Root "launcher\src-tauri\src\commands.rs"
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

function New-BetaReadyRecord {
    param(
        [string]$Category,
        [string]$Id,
        [string]$State,
        [string]$Reason,
        [string]$RecommendedAction,
        [string]$Path = "",
        [string]$Verification = "read_only",
        [string]$Phase = ""
    )

    [ordered]@{
        category = $Category
        id = $Id
        state = $State
        reason = $Reason
        path = $Path
        verification = $Verification
        phase = $Phase
        recommended_action = $RecommendedAction
    }
}

function Add-BetaReadyItem {
    param(
        [ValidateSet("blockers", "warnings", "manual_checks", "future_formal_only")]
        [string]$Severity,
        [object]$Record
    )
    $Report.beta_ready[$Severity] = @($Report.beta_ready[$Severity]) + @($Record)
}

function Get-UpdateSourceFromConfig {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $null
    }

    $InUpdates = $false
    foreach ($Line in @(Get-Content -Encoding UTF8 $Path)) {
        if ($Line -match "^\s*updates\s*:\s*$") {
            $InUpdates = $true
            continue
        }
        if ($InUpdates -and $Line -match "^\S") {
            $InUpdates = $false
        }
        if ($InUpdates -and $Line -match "^\s{2,}(source_url|manifest_url|url)\s*:\s*(.+?)\s*$") {
            $Value = ([string]$Matches[2]).Trim().Trim('"').Trim("'")
            if (-not [string]::IsNullOrWhiteSpace($Value)) {
                return $Value
            }
        }
    }
    return $null
}

function Add-BetaReadyClassifications {
    $Phase1 = "Phase 1"
    $Phase2 = "Phase 2"
    $Phase3 = "Phase 3"
    $Phase4 = "Phase 4"
    $Phase5 = "Phase 5"

    foreach ($RelativePath in @(
        "runner",
        "apps",
        "runtime",
        "config.default",
        "release\manifest.json",
        "release\app_manifest.json",
        "tools\app_studio\main.py",
        "tools\app_studio\app_studio",
        "tools\app_studio\assets",
        "updater",
        "README.md"
    )) {
        $Path = Join-Path $Root $RelativePath
        if (-not (Test-Path -LiteralPath $Path)) {
            Add-BetaReadyItem "blockers" (New-BetaReadyRecord -Category "beta_ready_blocker" -Id "distribution_source_missing:$RelativePath" -State "missing" -Reason "A required installer payload source is missing from the repository." -RecommendedAction "Restore the path before building a Beta installer." -Path (To-RelativePath $Path) -Phase $Phase1)
        }
    }

    if (Test-Path -LiteralPath $TauriConfigPath -PathType Leaf) {
        $TauriConfigText = Get-Content -Raw -Encoding UTF8 $TauriConfigPath
        foreach ($Resource in @("../../runner", "../../apps", "../../runtime", "../../config.default", "../../release/manifest.json", "../../release/app_manifest.json", "../../tools/app_studio/main.py", "../../tools/app_studio/app_studio", "../../tools/app_studio/assets", "../../updater", "../../README.md")) {
            if ($TauriConfigText -notmatch [regex]::Escape($Resource)) {
                Add-BetaReadyItem "blockers" (New-BetaReadyRecord -Category "beta_ready_blocker" -Id "tauri_resource_missing:$Resource" -State "missing" -Reason "Tauri bundle.resources does not list a required Beta payload resource." -RecommendedAction "Add the resource before building a Beta installer." -Path (To-RelativePath $TauriConfigPath) -Phase $Phase1)
            }
        }
    } else {
        Add-BetaReadyItem "blockers" (New-BetaReadyRecord -Category "beta_ready_blocker" -Id "tauri_config_missing" -State "missing" -Reason "Tauri config is missing, so installer payload resources cannot be checked." -RecommendedAction "Restore launcher/src-tauri/tauri.conf.json." -Path (To-RelativePath $TauriConfigPath) -Phase $Phase1)
    }

    if ($ReleaseManifest -and $ReleaseManifest.toolhub -and $ReleaseManifest.toolhub.installer -and $ReleaseManifest.toolhub.installer.file) {
        $InstallerPathForBeta = Join-Path (Join-Path $ReleaseDir "dist_installer") ([string]$ReleaseManifest.toolhub.installer.file)
        if (Test-Path -LiteralPath $InstallerPathForBeta -PathType Leaf) {
            $ActualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $InstallerPathForBeta).Hash.ToLowerInvariant()
            $ExpectedHash = [string]$ReleaseManifest.toolhub.installer.sha256
            if ([string]::IsNullOrWhiteSpace($ExpectedHash)) {
                Add-BetaReadyItem "blockers" (New-BetaReadyRecord -Category "beta_ready_blocker" -Id "installer_sha256_missing" -State "sha256_missing" -Reason "Installer artifact exists but release/manifest.json has no installer sha256." -RecommendedAction "Package the installer through scripts/package_installer.ps1 so sha256 is recorded." -Path (To-RelativePath $InstallerPathForBeta) -Phase $Phase1)
            } elseif ($ActualHash -ne $ExpectedHash) {
                Add-BetaReadyItem "blockers" (New-BetaReadyRecord -Category "beta_ready_blocker" -Id "installer_sha256_mismatch" -State "sha256_mismatch" -Reason "Installer artifact sha256 does not match release/manifest.json." -RecommendedAction "Rebuild or repackage the installer before Beta distribution." -Path (To-RelativePath $InstallerPathForBeta) -Phase $Phase1)
            }
            if ($ReleaseManifest.toolhub.installer.size) {
                $ActualSize = (Get-Item -LiteralPath $InstallerPathForBeta).Length
                if ([int64]$ReleaseManifest.toolhub.installer.size -ne $ActualSize) {
                    Add-BetaReadyItem "blockers" (New-BetaReadyRecord -Category "beta_ready_blocker" -Id "installer_size_mismatch" -State "size_mismatch" -Reason "Installer artifact size does not match release/manifest.json." -RecommendedAction "Rebuild or repackage the installer before Beta distribution." -Path (To-RelativePath $InstallerPathForBeta) -Phase $Phase1)
                }
            } else {
                Add-BetaReadyItem "warnings" (New-BetaReadyRecord -Category "beta_ready_warning" -Id "installer_size_missing" -State "size_missing" -Reason "Installer artifact exists but release/manifest.json has no installer size." -RecommendedAction "Package the installer through scripts/package_installer.ps1 so size is recorded." -Path (To-RelativePath $InstallerPathForBeta) -Phase $Phase1)
            }
        } else {
            Add-BetaReadyItem "blockers" (New-BetaReadyRecord -Category "beta_ready_blocker" -Id "installer_artifact_missing" -State "missing" -Reason "release/manifest.json points to an installer, but the artifact is not present." -RecommendedAction "Build/package the installer before Beta distribution." -Path (To-RelativePath $InstallerPathForBeta) -Phase $Phase1)
        }
    } else {
        Add-BetaReadyItem "blockers" (New-BetaReadyRecord -Category "beta_ready_blocker" -Id "installer_manifest_entry_missing" -State "missing" -Reason "release/manifest.json does not define toolhub.installer.file." -RecommendedAction "Fix the release manifest through the packaging flow before Beta distribution." -Path (To-RelativePath $ReleaseManifestPath) -Phase $Phase1)
    }

    if (-not (Test-Path -LiteralPath $StageManifest -PathType Leaf)) {
        Add-BetaReadyItem "blockers" (New-BetaReadyRecord -Category "beta_ready_blocker" -Id "installer_staging_manifest_missing" -State "missing" -Reason "Installer staging manifest is not present, so payload contents have not been captured for this checkout." -RecommendedAction "Run the release packaging flow during Phase 1; do not generate artifacts in Phase 0." -Path (To-RelativePath $StageManifest) -Phase $Phase1)
    }

    if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
        Add-BetaReadyItem "blockers" (New-BetaReadyRecord -Category "beta_ready_blocker" -Id "python_runtime_missing" -State "missing" -Reason "runtime/python/python.exe is required for Beta installer environments that must not depend on user-installed Python." -RecommendedAction "Prepare an approved Python runtime archive and verify it with verify_runtime.ps1 -RequireRuntime during Phase 1." -Path (To-RelativePath $PythonExe) -Phase $Phase1)
    } else {
        Add-BetaReadyItem "manual_checks" (New-BetaReadyRecord -Category "beta_ready_manual_check" -Id "embedded_python_used_after_install" -State "manual_check_required" -Reason "Local runtime/python/python.exe exists, but this report cannot prove the installed app uses the bundled Python." -RecommendedAction "Verify in a clean installed environment that ToolHub uses runtime/python/python.exe instead of PATH Python." -Path (To-RelativePath $PythonExe) -Verification "manual" -Phase $Phase1)
    }

    if ($WebRuntimeFiles.Count -eq 0) {
        Add-BetaReadyItem "blockers" (New-BetaReadyRecord -Category "beta_ready_blocker" -Id "web_runtime_missing" -State "missing" -Reason "Web automation runtime files are required for Beta installer environments that run web automation apps." -RecommendedAction "Prepare an approved Web runtime archive and verify it with verify_runtime.ps1 -RequireRuntime during Phase 1." -Path (To-RelativePath $WebRuntimeDir) -Phase $Phase1)
    } else {
        Add-BetaReadyItem "manual_checks" (New-BetaReadyRecord -Category "beta_ready_manual_check" -Id "web_runtime_used_after_install" -State "manual_check_required" -Reason "Local Web automation runtime files exist, but this report cannot prove the installed app uses them." -RecommendedAction "Register or install a Web automation app and verify it in a clean installed environment." -Path (To-RelativePath $WebRuntimeDir) -Verification "manual" -Phase $Phase1)
    }

    Add-BetaReadyItem "manual_checks" (New-BetaReadyRecord -Category "beta_ready_manual_check" -Id "verify_runtime_require_runtime_release_machine" -State "manual_check_required" -Reason "Beta requires verify_runtime.ps1 -RequireRuntime to pass on the release build machine." -RecommendedAction "Run .\scripts\verify_runtime.ps1 -RequireRuntime during Phase 1." -Verification "manual" -Phase $Phase1)
    Add-BetaReadyItem "manual_checks" (New-BetaReadyRecord -Category "beta_ready_manual_check" -Id "real_install_uninstall" -State "manual_check_required" -Reason "Actual install and uninstall cannot be proven by this read-only report." -RecommendedAction "Install ToolHub_Setup.exe on a clean Windows user profile or VM, then verify uninstall preserves user data." -Verification "manual" -Phase $Phase1)
    Add-BetaReadyItem "manual_checks" (New-BetaReadyRecord -Category "beta_ready_manual_check" -Id "install_dir_localappdata_programs" -State "manual_check_required" -Reason "The report cannot prove the actual installer destination." -RecommendedAction "Verify installation under %LOCALAPPDATA%\Programs\ToolHub\." -Verification "manual" -Phase $Phase1)
    Add-BetaReadyItem "manual_checks" (New-BetaReadyRecord -Category "beta_ready_manual_check" -Id "user_data_separation" -State "manual_check_required" -Reason "The report cannot prove first-run user data behavior in an installed environment." -RecommendedAction "Verify %LOCALAPPDATA%\ToolHub\ is used and existing config/launcher.yaml is not overwritten." -Verification "manual" -Phase $Phase1)
    Add-BetaReadyItem "manual_checks" (New-BetaReadyRecord -Category "beta_ready_manual_check" -Id "no_user_dev_dependencies" -State "manual_check_required" -Reason "The report cannot prove the target user PC has no Python, Node.js, Rust, Tauri CLI, or pip package dependency." -RecommendedAction "Verify ToolHub on a clean machine without developer toolchains installed." -Verification "manual" -Phase $Phase1)
    Add-BetaReadyItem "manual_checks" (New-BetaReadyRecord -Category "beta_ready_manual_check" -Id "installed_app_cards" -State "manual_check_required" -Reason "The report cannot launch the installed UI or registered apps." -RecommendedAction "Verify the installed ToolHub UI and launch a deliberately registered validation app." -Verification "manual" -Phase $Phase1)

    $UpdateSource = Get-UpdateSourceFromConfig $DefaultLauncherConfigPath
    if ([string]::IsNullOrWhiteSpace($UpdateSource)) {
        Add-BetaReadyItem "manual_checks" (New-BetaReadyRecord -Category "beta_ready_manual_check" -Id "remote_update_source_not_configured" -State "manual_check_required" -Reason "config.default/launcher.yaml does not define updates.manifest_url, updates.source_url, or updates.url for a remote manifest." -RecommendedAction "Decide and configure the Beta remote manifest endpoint before distribution; do not fabricate a placeholder endpoint in code." -Path (To-RelativePath $DefaultLauncherConfigPath) -Verification "manual" -Phase $Phase2)
    }

    if (Test-Path -LiteralPath $CommandsPath -PathType Leaf) {
        $CommandsText = Get-Content -Raw -Encoding UTF8 $CommandsPath
        $RemoteFetchImplemented = ($CommandsText -match "check_updates_remote" -and $CommandsText -match "fetch_manifest_json")
        $InstallerDownloadImplemented = ($CommandsText -match "download_update_installer")
        $Sha256Implemented = ($CommandsText -match "expected_sha256" -and $CommandsText -match "sha256_file")
        $ResultLogImplemented = ($CommandsText -match "write_update_result_log" -and $CommandsText -match "latest_update_result.json")
        $LaunchBoundaryImplemented = ($CommandsText -match "validate_installer_cache_path" -and $CommandsText -match "installer_path_outside_update_cache")
        $InstallerNameImplemented = ($CommandsText -match "validate_installer_file_name" -and $CommandsText -match "ToolHub_Setup")
        $HttpBlockedImplemented = ($CommandsText -match "remote_http_blocked" -and $CommandsText -match "http:// update sources are not allowed")

        if (-not $RemoteFetchImplemented) {
            Add-BetaReadyItem "blockers" (New-BetaReadyRecord -Category "beta_ready_blocker" -Id "remote_manifest_fetch_not_implemented" -State "not_implemented" -Reason "The current update command is the local manifest MVP; remote manifest fetch is not implemented." -RecommendedAction "Implement remote manifest fetch as Phase 2 without changing manifest schema incompatibly." -Path (To-RelativePath $CommandsPath) -Phase $Phase2)
        } else {
            Add-BetaReadyItem "warnings" (New-BetaReadyRecord -Category "beta_ready_warning" -Id "remote_manifest_fetch_implemented_unverified" -State "implemented_unverified" -Reason "Remote manifest fetch is implemented, but this read-only report cannot prove a real Beta endpoint works." -RecommendedAction "Verify no_update, update_available, invalid manifest, and network failure against the chosen endpoint or a local file test." -Path (To-RelativePath $CommandsPath) -Phase $Phase2)
        }
        if (-not $InstallerDownloadImplemented) {
            Add-BetaReadyItem "blockers" (New-BetaReadyRecord -Category "beta_ready_blocker" -Id "installer_download_not_implemented" -State "not_implemented" -Reason "Installer download is still listed as an unsupported update action." -RecommendedAction "Implement installer download to %LOCALAPPDATA%\ToolHub\update_cache\ in Phase 3." -Path (To-RelativePath $CommandsPath) -Phase $Phase3)
        } else {
            Add-BetaReadyItem "warnings" (New-BetaReadyRecord -Category "beta_ready_warning" -Id "installer_download_implemented_unverified" -State "implemented_unverified" -Reason "Installer download is implemented, but this read-only report cannot prove a real installer can be downloaded from the Beta endpoint." -RecommendedAction "Verify successful download, interrupted download, size mismatch, and cache overwrite behavior with a test artifact." -Path (To-RelativePath $CommandsPath) -Phase $Phase3)
        }
        if (-not $Sha256Implemented) {
            Add-BetaReadyItem "blockers" (New-BetaReadyRecord -Category "beta_ready_blocker" -Id "downloaded_installer_sha256_verify_not_implemented" -State "not_implemented" -Reason "Downloaded installer sha256 verification is not implemented; this is mandatory even for Beta." -RecommendedAction "Verify downloaded installer sha256 against remote manifest before enabling installer launch in Phase 3." -Path (To-RelativePath $CommandsPath) -Phase $Phase3)
        } else {
            Add-BetaReadyItem "warnings" (New-BetaReadyRecord -Category "beta_ready_warning" -Id "installer_sha256_verify_implemented_unverified" -State "implemented_unverified" -Reason "Downloaded installer sha256 verification is implemented, but real artifact verification has not been proven by this report." -RecommendedAction "Verify exact match and mismatch cases before Beta distribution." -Path (To-RelativePath $CommandsPath) -Phase $Phase3)
        }
        if (-not $LaunchBoundaryImplemented) {
            Add-BetaReadyItem "blockers" (New-BetaReadyRecord -Category "beta_ready_blocker" -Id "installer_launch_cache_boundary_not_implemented" -State "not_implemented" -Reason "Verified installer launch does not prove cachePath is constrained to update_cache." -RecommendedAction "Canonicalize update_cache and cachePath, reject path traversal and paths outside update_cache before launching." -Path (To-RelativePath $CommandsPath) -Phase $Phase3)
        }
        if (-not $InstallerNameImplemented) {
            Add-BetaReadyItem "blockers" (New-BetaReadyRecord -Category "beta_ready_blocker" -Id "installer_file_name_safety_not_implemented" -State "not_implemented" -Reason "Installer file name and extension safety checks are missing." -RecommendedAction "Allow only ToolHub_Setup .exe/.msi files in update_cache for the Beta updater." -Path (To-RelativePath $CommandsPath) -Phase $Phase3)
        }
        if (-not $HttpBlockedImplemented) {
            Add-BetaReadyItem "blockers" (New-BetaReadyRecord -Category "beta_ready_blocker" -Id "http_update_source_not_blocked" -State "not_implemented" -Reason "http:// update sources are not explicitly blocked." -RecommendedAction "Require https:// for Beta remote distribution and keep file:// or relative paths for local tests only." -Path (To-RelativePath $CommandsPath) -Phase $Phase2)
        }
        if ($LaunchBoundaryImplemented -and $InstallerNameImplemented -and $HttpBlockedImplemented) {
            Add-BetaReadyItem "warnings" (New-BetaReadyRecord -Category "beta_ready_warning" -Id "updater_safety_checks_implemented_unverified" -State "implemented_unverified" -Reason "Updater path, file name, extension, and http:// blocking checks are implemented, but malicious path and real endpoint cases still need execution testing." -RecommendedAction "Exercise outside-cache path, path traversal, non-.exe/.msi, non-ToolHub_Setup name, http:// source, file:// test source, and https endpoint cases." -Path (To-RelativePath $CommandsPath) -Phase $Phase3)
        }
        if (-not $ResultLogImplemented) {
            Add-BetaReadyItem "blockers" (New-BetaReadyRecord -Category "beta_ready_blocker" -Id "updater_result_log_not_implemented" -State "not_implemented" -Reason "Persistent updater result logging is not implemented." -RecommendedAction "Add update check/download/verify/launch result logging in Phase 4." -Path (To-RelativePath $CommandsPath) -Phase $Phase4)
        } else {
            Add-BetaReadyItem "warnings" (New-BetaReadyRecord -Category "beta_ready_warning" -Id "updater_result_log_implemented_unverified" -State "implemented_unverified" -Reason "Updater result logging is implemented, but this read-only report cannot prove real check/download/launch logs in an installed environment." -RecommendedAction "Verify latest_update_result.json contains status, ok, checkedAt, operation, source kind, sanitized URLs, cachePath, expected/actual sha256, message, and failure reason." -Path (To-RelativePath $CommandsPath) -Phase $Phase4)
        }
    } else {
        Add-BetaReadyItem "blockers" (New-BetaReadyRecord -Category "beta_ready_blocker" -Id "update_command_source_missing" -State "missing" -Reason "The update command source file is missing, so update readiness cannot be checked." -RecommendedAction "Restore launcher/src-tauri/src/commands.rs." -Path (To-RelativePath $CommandsPath) -Phase $Phase2)
    }

    Add-BetaReadyItem "future_formal_only" (New-BetaReadyRecord -Category "future_formal_only" -Id "installer_code_signing" -State "formal_release_required" -Reason "Code signing may be deferred for internal Beta, but it is a formal release blocker unless policy explicitly says otherwise." -RecommendedAction "Decide signing policy before formal release; stop Beta if the distribution policy requires signing." -Phase $Phase5)
    Add-BetaReadyItem "future_formal_only" (New-BetaReadyRecord -Category "future_formal_only" -Id "manifest_signing" -State "formal_release_required" -Reason "Manifest authenticity is not guaranteed by sha256 alone if the manifest itself is compromised." -RecommendedAction "Add manifest signing or use a trusted release distribution path before formal release." -Phase $Phase5)
    Add-BetaReadyItem "future_formal_only" (New-BetaReadyRecord -Category "future_formal_only" -Id "backup_and_rollback" -State "formal_release_extension" -Reason "Backup and rollback are outside the Beta installer redistribution MVP." -RecommendedAction "Implement before differential or automatic updates." -Phase $Phase5)
    Add-BetaReadyItem "future_formal_only" (New-BetaReadyRecord -Category "future_formal_only" -Id "app_pack_and_runtime_unit_updates" -State "formal_release_extension" -Reason "App Pack and runtime unit updates are future extensions after whole-installer update works." -RecommendedAction "Keep Beta MVP on whole-installer redistribution first." -Phase $Phase5)
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
    beta_ready = [ordered]@{
        blockers = @()
        warnings = @()
        manual_checks = @()
        future_formal_only = @()
    }
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
            Add-ListItem $Report "intentional_warnings" (New-ItemRecord -Category "intentional_warnings" -Id $AppId -State "app_env_missing" -Reason "runtime/app_envs/<app_id> is missing. Current normal App Studio shared-env registration does not use app_env as the app source of truth." -RecommendedAction "Do not delete the app for this. Revisit only if an app-env execution mode is intentionally revived." -Path (To-RelativePath $AppEnvPath))
            Add-ListItem $Report "docs_check_adjustment_candidates" (New-ItemRecord -Category "docs_check_adjustment_candidates" -Id $AppId -State "strict_app_env_policy" -Reason "verify_release.ps1 -Strict should not require runtime/app_envs/<app_id> for normal App Studio shared-env apps." -RecommendedAction "Keep app_env checks limited to explicit app-env apps; shared-env apps must instead validate runtime/envs/<env_id>." -Path (To-RelativePath $AppEnvPath))
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

Add-BetaReadyClassifications

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
    beta_ready_blockers = @($Report.beta_ready.blockers).Count
    beta_ready_warnings = @($Report.beta_ready.warnings).Count
    beta_ready_manual_checks = @($Report.beta_ready.manual_checks).Count
    beta_ready_future_formal_only = @($Report.beta_ready.future_formal_only).Count
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
Write-Line "beta_ready_blockers: $($Report.summary.beta_ready_blockers)"
foreach ($Item in @($Report.beta_ready.blockers)) {
    Write-Line "  - [$($Item.phase)] $($Item.id): $($Item.reason)"
}
Write-Line "beta_ready_warnings: $($Report.summary.beta_ready_warnings)"
foreach ($Item in @($Report.beta_ready.warnings)) {
    Write-Line "  - [$($Item.phase)] $($Item.id): $($Item.reason)"
}
Write-Line "beta_ready_manual_checks: $($Report.summary.beta_ready_manual_checks)"
foreach ($Item in @($Report.beta_ready.manual_checks)) {
    Write-Line "  - [$($Item.phase)] $($Item.id): $($Item.reason)"
}
Write-Line "beta_ready_future_formal_only: $($Report.summary.beta_ready_future_formal_only)"
foreach ($Item in @($Report.beta_ready.future_formal_only)) {
    Write-Line "  - [$($Item.phase)] $($Item.id): $($Item.reason)"
}
Write-Line ""
Write-Line "No files were changed. Use -Json for machine-readable details."

if ($Failed) {
    exit 1
}
exit 0
