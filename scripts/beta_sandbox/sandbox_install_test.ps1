param(
    [string]$RepoRoot = "C:\ToolHubRepo",
    [string]$ResultsDir = "C:\ToolHubBetaResults",
    [int]$InstallerTimeoutMinutes = 30,
    [int]$UninstallerTimeoutMinutes = 20,
    [int]$LaunchSeconds = 15,
    [switch]$PauseForManualGuiChecks,
    [switch]$SkipUninstall
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$StartedAt = Get-Date
$Checks = New-Object System.Collections.Generic.List[object]
$Artifacts = [ordered]@{}

function Write-Utf8NoBom {
    param(
        [string]$Path,
        [string]$Content
    )
    $Encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $Encoding)
}

function Add-Check {
    param(
        [string]$Id,
        [string]$Description,
        [ValidateSet("pass", "fail", "warning", "manual_check", "not_run")]
        [string]$Status,
        [string]$Message,
        [hashtable]$Data = @{}
    )

    $Checks.Add([ordered]@{
        id = $Id
        description = $Description
        status = $Status
        ok = ($Status -eq "pass")
        message = $Message
        data = $Data
        checked_at = (Get-Date).ToString("o")
    }) | Out-Null
}

function Add-ManualPromptCheck {
    param(
        [string]$Id,
        [string]$Description,
        [string]$Prompt
    )

    if (-not $PauseForManualGuiChecks) {
        Add-Check -Id $Id -Description $Description -Status "manual_check" -Message "$Description requires GUI confirmation. Rerun with -PauseForManualGuiChecks to record a pass/fail answer."
        return
    }

    $Answer = Read-Host "$Prompt [y]es/[n]o/[s]kip"
    if ($Answer -match "^(y|yes)$") {
        Add-Check -Id $Id -Description $Description -Status "pass" -Message "manual GUI confirmation passed"
    } elseif ($Answer -match "^(n|no)$") {
        Add-Check -Id $Id -Description $Description -Status "fail" -Message "manual GUI confirmation failed"
    } else {
        Add-Check -Id $Id -Description $Description -Status "manual_check" -Message "manual GUI confirmation skipped"
    }
}

function Find-FirstExistingPath {
    param(
        [string[]]$BasePaths,
        [string]$RelativePath
    )

    foreach ($BasePath in $BasePaths) {
        if ([string]::IsNullOrWhiteSpace($BasePath)) {
            continue
        }
        $Candidate = Join-Path $BasePath $RelativePath
        if (Test-Path -LiteralPath $Candidate) {
            return $Candidate
        }
    }
    return $null
}

function Wait-StartedProcess {
    param(
        [System.Diagnostics.Process]$Process,
        [int]$TimeoutMinutes
    )
    $TimeoutMs = [Math]::Max(1, $TimeoutMinutes) * 60 * 1000
    return $Process.WaitForExit($TimeoutMs)
}

function Save-Results {
    param([string]$FatalMessage = "")

    New-Item -ItemType Directory -Force -Path $ResultsDir | Out-Null
    $FinishedAt = Get-Date
    $FailCount = @($Checks | Where-Object { $_.status -eq "fail" }).Count
    $ManualCount = @($Checks | Where-Object { $_.status -eq "manual_check" }).Count
    $WarningCount = @($Checks | Where-Object { $_.status -eq "warning" }).Count
    $OverallStatus = if ($FailCount -gt 0 -or -not [string]::IsNullOrWhiteSpace($FatalMessage)) {
        "fail"
    } elseif ($ManualCount -gt 0) {
        "manual_check"
    } else {
        "pass"
    }

    $Report = [ordered]@{
        schema_version = 1
        test_name = "toolhub_beta_sandbox_install_test"
        started_at = $StartedAt.ToString("o")
        finished_at = $FinishedAt.ToString("o")
        overall_status = $OverallStatus
        fatal_message = $FatalMessage
        repo_root = $RepoRoot
        results_dir = $ResultsDir
        sandbox_user = [Environment]::UserName
        local_app_data = $env:LOCALAPPDATA
        artifacts = $Artifacts
        counts = [ordered]@{
            pass = @($Checks | Where-Object { $_.status -eq "pass" }).Count
            fail = $FailCount
            warning = $WarningCount
            manual_check = $ManualCount
            not_run = @($Checks | Where-Object { $_.status -eq "not_run" }).Count
        }
        checks = @($Checks)
    }

    $Stamp = $StartedAt.ToString("yyyyMMdd_HHmmss")
    $JsonPath = Join-Path $ResultsDir "sandbox_install_result_$Stamp.json"
    $MarkdownPath = Join-Path $ResultsDir "sandbox_install_result_$Stamp.md"
    $LatestJsonPath = Join-Path $ResultsDir "latest_sandbox_install_result.json"
    $LatestMarkdownPath = Join-Path $ResultsDir "latest_sandbox_install_result.md"

    $Json = $Report | ConvertTo-Json -Depth 10
    Write-Utf8NoBom -Path $JsonPath -Content $Json
    Write-Utf8NoBom -Path $LatestJsonPath -Content $Json

    $Lines = New-Object System.Collections.Generic.List[string]
    $Lines.Add("# ToolHub Beta Sandbox Install Result") | Out-Null
    $Lines.Add("") | Out-Null
    $Lines.Add(("- overall_status: {0}" -f $OverallStatus)) | Out-Null
    $Lines.Add(("- started_at: {0}" -f $Report.started_at)) | Out-Null
    $Lines.Add(("- finished_at: {0}" -f $Report.finished_at)) | Out-Null
    $Lines.Add(("- sandbox_user: {0}" -f $Report.sandbox_user)) | Out-Null
    $Lines.Add(("- local_app_data: {0}" -f $Report.local_app_data)) | Out-Null
    if (-not [string]::IsNullOrWhiteSpace($FatalMessage)) {
        $Lines.Add(("- fatal_message: {0}" -f $FatalMessage)) | Out-Null
    }
    $Lines.Add("") | Out-Null
    $Lines.Add("## Checks") | Out-Null
    $Lines.Add("") | Out-Null
    $Lines.Add("| status | id | message |") | Out-Null
    $Lines.Add("| --- | --- | --- |") | Out-Null
    foreach ($Check in $Checks) {
        $SafeMessage = ([string]$Check.message).Replace("|", "\|")
        $Lines.Add(("| {0} | {1} | {2} |" -f $Check.status, $Check.id, $SafeMessage)) | Out-Null
    }
    Write-Utf8NoBom -Path $MarkdownPath -Content ($Lines -join [Environment]::NewLine)
    Write-Utf8NoBom -Path $LatestMarkdownPath -Content ($Lines -join [Environment]::NewLine)

    Write-Host "Sandbox install result JSON: $JsonPath"
    Write-Host "Sandbox install result Markdown: $MarkdownPath"

    if ($OverallStatus -eq "fail") {
        exit 1
    }
}

try {
    New-Item -ItemType Directory -Force -Path $ResultsDir | Out-Null

    foreach ($ToolName in @("python", "pip", "pip3", "node", "npm", "rustc", "cargo")) {
        $Commands = @(Get-Command $ToolName -ErrorAction SilentlyContinue)
        if ($Commands.Count -eq 0) {
            Add-Check -Id "dev_tool_absent_$ToolName" -Description "$ToolName is not available from PATH" -Status "pass" -Message "$ToolName was not found in PATH"
        } else {
            Add-Check -Id "dev_tool_absent_$ToolName" -Description "$ToolName is not available from PATH" -Status "fail" -Message "$ToolName was found in PATH" -Data @{ paths = @($Commands | ForEach-Object { $_.Source }) }
        }
    }

    $ManifestPath = Join-Path $RepoRoot "release\manifest.json"
    $StagingManifestPath = Join-Path $RepoRoot "release\staging\installer_payload\staging_manifest.json"
    if (-not (Test-Path -LiteralPath $ManifestPath)) {
        Add-Check -Id "release_manifest_exists" -Description "release manifest exists" -Status "fail" -Message "release manifest not found: $ManifestPath"
        Save-Results
        return
    }
    if (-not (Test-Path -LiteralPath $StagingManifestPath)) {
        Add-Check -Id "staging_manifest_exists" -Description "staging manifest exists" -Status "fail" -Message "staging manifest not found: $StagingManifestPath"
        Save-Results
        return
    }
    Add-Check -Id "staging_manifest_exists" -Description "staging manifest exists" -Status "pass" -Message "staging manifest found: $StagingManifestPath"

    $Manifest = Get-Content -Encoding UTF8 -Raw -LiteralPath $ManifestPath | ConvertFrom-Json
    $InstallerFile = [string]$Manifest.toolhub.installer.file
    $ExpectedSha256 = [string]$Manifest.toolhub.installer.sha256
    $ExpectedSize = [int64]$Manifest.toolhub.installer.size
    $InstallerPath = Join-Path (Join-Path $RepoRoot "release\dist_installer") $InstallerFile
    $Artifacts["release_manifest"] = $ManifestPath
    $Artifacts["staging_manifest"] = $StagingManifestPath
    $Artifacts["installer_path"] = $InstallerPath
    $Artifacts["expected_sha256"] = $ExpectedSha256
    $Artifacts["expected_size"] = $ExpectedSize

    if (-not (Test-Path -LiteralPath $InstallerPath)) {
        Add-Check -Id "installer_exists" -Description "installer exists" -Status "fail" -Message "installer not found: $InstallerPath"
        Save-Results
        return
    }
    Add-Check -Id "installer_exists" -Description "installer exists" -Status "pass" -Message "installer found: $InstallerPath"

    $InstallerItem = Get-Item -LiteralPath $InstallerPath
    $ActualSize = [int64]$InstallerItem.Length
    $ActualSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $InstallerPath).Hash.ToLowerInvariant()
    $Artifacts["actual_size"] = $ActualSize
    $Artifacts["actual_sha256"] = $ActualSha256

    if ($ActualSize -eq $ExpectedSize) {
        Add-Check -Id "installer_size_matches_manifest" -Description "installer size matches release manifest" -Status "pass" -Message "installer size matched: $ActualSize"
    } else {
        Add-Check -Id "installer_size_matches_manifest" -Description "installer size matches release manifest" -Status "fail" -Message "installer size mismatch. expected=$ExpectedSize actual=$ActualSize"
    }

    if ($ActualSha256 -eq $ExpectedSha256.ToLowerInvariant()) {
        Add-Check -Id "installer_sha256_matches_manifest" -Description "installer sha256 matches release manifest" -Status "pass" -Message "installer sha256 matched: $ActualSha256"
    } else {
        Add-Check -Id "installer_sha256_matches_manifest" -Description "installer sha256 matches release manifest" -Status "fail" -Message "installer sha256 mismatch. expected=$ExpectedSha256 actual=$ActualSha256"
    }

    Write-Host "Starting ToolHub installer. Complete the installer UI in Windows Sandbox. Do not choose any option that deletes user data."
    $InstallerProcess = Start-Process -FilePath $InstallerPath -PassThru -ErrorAction Stop
    $InstallerExited = Wait-StartedProcess -Process $InstallerProcess -TimeoutMinutes $InstallerTimeoutMinutes
    if (-not $InstallerExited) {
        Add-Check -Id "installer_completed" -Description "installer completes" -Status "manual_check" -Message "installer did not exit within $InstallerTimeoutMinutes minutes. Complete the installer manually and rerun if needed."
        Save-Results
        return
    }
    if ($InstallerProcess.ExitCode -eq 0) {
        Add-Check -Id "installer_completed" -Description "installer completes" -Status "pass" -Message "installer exited with code 0"
    } else {
        Add-Check -Id "installer_completed" -Description "installer completes" -Status "fail" -Message "installer exited with code $($InstallerProcess.ExitCode)"
    }

    $InstallDir = Join-Path $env:LOCALAPPDATA "Programs\ToolHub"
    $UserDataDir = Join-Path $env:LOCALAPPDATA "ToolHub"
    $ToolHubExe = Join-Path $InstallDir "ToolHub.exe"
    $Artifacts["install_dir"] = $InstallDir
    $Artifacts["user_data_dir"] = $UserDataDir
    $Artifacts["toolhub_exe"] = $ToolHubExe

    if (Test-Path -LiteralPath $InstallDir) {
        Add-Check -Id "install_dir_exists" -Description "install dir exists" -Status "pass" -Message "install dir exists: $InstallDir"
    } else {
        Add-Check -Id "install_dir_exists" -Description "install dir exists" -Status "fail" -Message "install dir not found: $InstallDir"
    }

    if (Test-Path -LiteralPath $ToolHubExe) {
        Add-Check -Id "toolhub_exe_exists" -Description "ToolHub.exe exists in install dir" -Status "pass" -Message "ToolHub.exe found: $ToolHubExe"
    } else {
        Add-Check -Id "toolhub_exe_exists" -Description "ToolHub.exe exists in install dir" -Status "fail" -Message "ToolHub.exe not found: $ToolHubExe"
    }

    $PayloadRoots = @($InstallDir, (Join-Path $InstallDir "resources"))
    foreach ($RequiredPath in @("runner", "apps", "runtime", "config.default", "release")) {
        $FoundPath = Find-FirstExistingPath -BasePaths $PayloadRoots -RelativePath $RequiredPath
        if ($null -ne $FoundPath) {
            Add-Check -Id "payload_$($RequiredPath.Replace('.', '_'))_exists" -Description "$RequiredPath payload exists" -Status "pass" -Message "$RequiredPath found: $FoundPath"
        } else {
            Add-Check -Id "payload_$($RequiredPath.Replace('.', '_'))_exists" -Description "$RequiredPath payload exists" -Status "fail" -Message "$RequiredPath not found under install dir or resources dir"
        }
    }

    $BundledPython = Find-FirstExistingPath -BasePaths $PayloadRoots -RelativePath "runtime\python\python.exe"
    if ($null -ne $BundledPython) {
        Add-Check -Id "bundled_python_exists" -Description "bundled runtime python exists" -Status "pass" -Message "bundled python found: $BundledPython"
    } else {
        Add-Check -Id "bundled_python_exists" -Description "bundled runtime python exists" -Status "fail" -Message "runtime\python\python.exe not found under install dir or resources dir"
    }

    $WebRuntime = Find-FirstExistingPath -BasePaths $PayloadRoots -RelativePath "runtime\web_automation_runtime"
    if ($null -ne $WebRuntime) {
        Add-Check -Id "web_automation_runtime_exists" -Description "bundled web automation runtime exists" -Status "pass" -Message "web automation runtime found: $WebRuntime"
    } else {
        Add-Check -Id "web_automation_runtime_exists" -Description "bundled web automation runtime exists" -Status "fail" -Message "runtime\web_automation_runtime not found under install dir or resources dir"
    }

    if (Test-Path -LiteralPath $ToolHubExe) {
        $ToolHubProcess = Start-Process -FilePath $ToolHubExe -PassThru -ErrorAction Stop
        Start-Sleep -Seconds $LaunchSeconds
        if ($ToolHubProcess.HasExited) {
            if ($ToolHubProcess.ExitCode -eq 0) {
                Add-Check -Id "toolhub_launch" -Description "ToolHub launches" -Status "pass" -Message "ToolHub launched and exited with code 0"
            } else {
                Add-Check -Id "toolhub_launch" -Description "ToolHub launches" -Status "fail" -Message "ToolHub exited early with code $($ToolHubProcess.ExitCode)"
            }
            Add-Check -Id "app_cards_visible" -Description "app cards are visible in GUI" -Status "not_run" -Message "ToolHub was not running when GUI checks were requested"
        } else {
            Add-Check -Id "toolhub_launch" -Description "ToolHub launches" -Status "pass" -Message "ToolHub process stayed running for $LaunchSeconds seconds"
            if ($PauseForManualGuiChecks) {
                Write-Host ""
                Write-Host "ToolHub is running. Complete GUI checks before continuing:"
                Write-Host "1. Confirm the ToolHub window is usable."
                Write-Host "2. If a validation app has been registered, launch it from ToolHub."
                Write-Host "Answer the prompts below after checking the ToolHub window."
            }
            Add-ManualPromptCheck -Id "app_cards_visible" -Description "app cards are visible in GUI" -Prompt "Are app cards visible in the ToolHub window?"
            $Closed = $ToolHubProcess.CloseMainWindow()
            Start-Sleep -Seconds 3
            if (-not $ToolHubProcess.HasExited) {
                Stop-Process -Id $ToolHubProcess.Id -Force -ErrorAction SilentlyContinue
            }
            $Artifacts["toolhub_close_main_window"] = $Closed
        }
    } else {
        Add-Check -Id "toolhub_launch" -Description "ToolHub launches" -Status "not_run" -Message "ToolHub.exe was not found"
        Add-Check -Id "app_cards_visible" -Description "app cards are visible in GUI" -Status "not_run" -Message "ToolHub.exe was not found"
    }

    if (Test-Path -LiteralPath $UserDataDir) {
        Add-Check -Id "user_data_dir_created" -Description "user data dir is created" -Status "pass" -Message "user data dir exists: $UserDataDir"
    } else {
        Add-Check -Id "user_data_dir_created" -Description "user data dir is created" -Status "fail" -Message "user data dir not found: $UserDataDir"
    }

    if (Test-Path -LiteralPath $UserDataDir) {
        $LogFiles = @(Get-ChildItem -LiteralPath $UserDataDir -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Extension -in @(".log", ".json") })
        if ($LogFiles.Count -gt 0) {
            Add-Check -Id "logs_created" -Description "logs or JSON records are created under user data dir" -Status "pass" -Message "$($LogFiles.Count) log/json files found under user data dir" -Data @{ sample_paths = @($LogFiles | Select-Object -First 10 | ForEach-Object { $_.FullName }) }
        } else {
            Add-Check -Id "logs_created" -Description "logs or JSON records are created under user data dir" -Status "warning" -Message "no .log or .json files were found under user data dir after first launch"
        }
    } else {
        Add-Check -Id "logs_created" -Description "logs or JSON records are created under user data dir" -Status "not_run" -Message "user data dir was not found"
    }

    if ($SkipUninstall) {
        Add-Check -Id "uninstall_completed" -Description "ToolHub uninstalls" -Status "not_run" -Message "SkipUninstall was specified"
        Add-Check -Id "user_data_preserved_after_uninstall" -Description "user data remains after uninstall" -Status "not_run" -Message "SkipUninstall was specified"
    } else {
        $UninstallCandidates = @()
        if (Test-Path -LiteralPath $InstallDir) {
            $UninstallCandidates = @(Get-ChildItem -LiteralPath $InstallDir -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -match "uninstall" })
        }

        if ($UninstallCandidates.Count -eq 0) {
            Add-Check -Id "uninstall_completed" -Description "ToolHub uninstalls" -Status "manual_check" -Message "no uninstaller executable was found under $InstallDir"
            Add-Check -Id "user_data_preserved_after_uninstall" -Description "user data remains after uninstall" -Status "not_run" -Message "uninstaller was not found"
        } else {
            $UninstallerPath = $UninstallCandidates[0].FullName
            $Artifacts["uninstaller_path"] = $UninstallerPath
            Write-Host "Starting ToolHub uninstaller. If prompted, do not select any option that deletes user data."
            $UninstallerProcess = Start-Process -FilePath $UninstallerPath -PassThru -ErrorAction Stop
            $UninstallerExited = Wait-StartedProcess -Process $UninstallerProcess -TimeoutMinutes $UninstallerTimeoutMinutes
            if (-not $UninstallerExited) {
                Add-Check -Id "uninstall_completed" -Description "ToolHub uninstalls" -Status "manual_check" -Message "uninstaller did not exit within $UninstallerTimeoutMinutes minutes"
                Add-Check -Id "user_data_preserved_after_uninstall" -Description "user data remains after uninstall" -Status "not_run" -Message "uninstaller did not complete"
            } elseif ($UninstallerProcess.ExitCode -eq 0) {
                Add-Check -Id "uninstall_completed" -Description "ToolHub uninstalls" -Status "pass" -Message "uninstaller exited with code 0"
                if (Test-Path -LiteralPath $UserDataDir) {
                    Add-Check -Id "user_data_preserved_after_uninstall" -Description "user data remains after uninstall" -Status "pass" -Message "user data dir still exists after uninstall: $UserDataDir"
                } else {
                    Add-Check -Id "user_data_preserved_after_uninstall" -Description "user data remains after uninstall" -Status "fail" -Message "user data dir was removed after uninstall: $UserDataDir"
                }
            } else {
                Add-Check -Id "uninstall_completed" -Description "ToolHub uninstalls" -Status "fail" -Message "uninstaller exited with code $($UninstallerProcess.ExitCode)"
                Add-Check -Id "user_data_preserved_after_uninstall" -Description "user data remains after uninstall" -Status "not_run" -Message "uninstaller failed"
            }
        }
    }

    Save-Results
} catch {
    Add-Check -Id "unexpected_error" -Description "unexpected script error" -Status "fail" -Message $_.Exception.Message
    Save-Results -FatalMessage $_.Exception.Message
}
