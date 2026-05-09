param(
    [string]$SharedRoot = "",
    [string]$InstallerPath = "",
    [string]$ManifestPath = "",
    [string]$ResultsDir = "",
    [int]$InstallerTimeoutMinutes = 30,
    [int]$UninstallerTimeoutMinutes = 20,
    [int]$LaunchSeconds = 15,
    [switch]$PauseForManualGuiChecks,
    [switch]$SkipUninstall,
    [switch]$SkipReinstall
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($SharedRoot)) {
    if (Test-Path -LiteralPath (Join-Path $ScriptDir "release\manifest.json") -PathType Leaf) {
        $SharedRoot = (Resolve-Path $ScriptDir).Path
    } else {
        $SharedRoot = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path
    }
} else {
    $SharedRoot = (Resolve-Path $SharedRoot).Path
}
if ([string]::IsNullOrWhiteSpace($ResultsDir)) {
    $ResultsDir = Join-Path $ScriptDir "results"
}
New-Item -ItemType Directory -Force -Path $ResultsDir | Out-Null

$StartedAt = Get-Date
$Stamp = $StartedAt.ToString("yyyyMMdd_HHmmss")
$Checks = New-Object System.Collections.Generic.List[object]
$Artifacts = [ordered]@{}

function Write-Utf8NoBom {
    param([string]$Path, [string]$Content)
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

function Get-CheckCount {
    param([string]$Status)
    $Count = 0
    foreach ($Check in $Checks) {
        if ([string]$Check.status -eq $Status) {
            $Count += 1
        }
    }
    return $Count
}

function Add-ManualPromptCheck {
    param([string]$Id, [string]$Description, [string]$Prompt)
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
    param([string[]]$BasePaths, [string]$RelativePath)
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

function Save-Results {
    param([string]$FatalMessage = "")
    $FailCount = Get-CheckCount -Status "fail"
    $ManualCount = Get-CheckCount -Status "manual_check"
    $PassCount = Get-CheckCount -Status "pass"
    $WarningCount = Get-CheckCount -Status "warning"
    $NotRunCount = Get-CheckCount -Status "not_run"
    $OverallStatus = if ($FailCount -gt 0 -or -not [string]::IsNullOrWhiteSpace($FatalMessage)) {
        "fail"
    } elseif ($ManualCount -gt 0) {
        "manual_check"
    } else {
        "pass"
    }
    $Report = [ordered]@{
        schema_version = 1
        test_name = "toolhub_beta_vm_install_test"
        started_at = $StartedAt.ToString("o")
        finished_at = (Get-Date).ToString("o")
        overall_status = $OverallStatus
        fatal_message = $FatalMessage
        shared_root = $SharedRoot
        results_dir = $ResultsDir
        local_app_data = $env:LOCALAPPDATA
        artifacts = $Artifacts
        counts = [ordered]@{
            pass = $PassCount
            fail = $FailCount
            warning = $WarningCount
            manual_check = $ManualCount
            "not_run" = $NotRunCount
        }
        checks = $Checks.ToArray()
    }

    $Json = $Report | ConvertTo-Json -Depth 10
    $JsonPath = Join-Path $ResultsDir "vm_install_result_$Stamp.json"
    $MarkdownPath = Join-Path $ResultsDir "vm_install_result_$Stamp.md"
    $LatestJsonPath = Join-Path $ResultsDir "latest_vm_install_result.json"
    $LatestMarkdownPath = Join-Path $ResultsDir "latest_vm_install_result.md"
    Write-Utf8NoBom -Path $JsonPath -Content $Json
    Write-Utf8NoBom -Path $LatestJsonPath -Content $Json

    $Lines = New-Object System.Collections.Generic.List[string]
    $Lines.Add("# ToolHub Beta VM Install Result") | Out-Null
    $Lines.Add("") | Out-Null
    $Lines.Add(("- overall_status: {0}" -f $OverallStatus)) | Out-Null
    $Lines.Add(("- local_app_data: {0}" -f $env:LOCALAPPDATA)) | Out-Null
    $Lines.Add("") | Out-Null
    $Lines.Add("| status | id | message |") | Out-Null
    $Lines.Add("| --- | --- | --- |") | Out-Null
    foreach ($Check in $Checks) {
        $SafeMessage = ([string]$Check.message).Replace("|", "\|")
        $Lines.Add(("| {0} | {1} | {2} |" -f $Check.status, $Check.id, $SafeMessage)) | Out-Null
    }
    Write-Utf8NoBom -Path $MarkdownPath -Content ($Lines -join [Environment]::NewLine)
    Write-Utf8NoBom -Path $LatestMarkdownPath -Content ($Lines -join [Environment]::NewLine)
    Write-Host "VM install result JSON: $JsonPath"
    Write-Host "VM install result Markdown: $MarkdownPath"
    if ($OverallStatus -eq "fail") {
        exit 1
    }
}

function Start-InstallerAndRecord {
    param(
        [string]$CheckId,
        [string]$Description
    )

    Write-Host "Start the ToolHub installer UI. Do not select any option that deletes user data."
    $StartedInstaller = Start-Process -FilePath $InstallerPath -PassThru -ErrorAction Stop
    if (-not $StartedInstaller.WaitForExit([Math]::Max(1, $InstallerTimeoutMinutes) * 60 * 1000)) {
        Add-Check -Id $CheckId -Description $Description -Status "manual_check" -Message "installer did not exit within $InstallerTimeoutMinutes minutes"
        return $false
    }
    if ($StartedInstaller.ExitCode -eq 0) {
        Add-Check -Id $CheckId -Description $Description -Status "pass" -Message "installer exited with code 0"
        return $true
    }
    Add-Check -Id $CheckId -Description $Description -Status "fail" -Message "installer exited with code $($StartedInstaller.ExitCode)"
    return $false
}

try {
    foreach ($ToolName in @("python", "pip", "node", "npm", "rustc", "cargo", "tauri")) {
        $Commands = @(Get-Command $ToolName -ErrorAction SilentlyContinue)
        if ($Commands.Count -eq 0) {
            Add-Check -Id "dev_tool_absent_$ToolName" -Description "$ToolName is absent from PATH" -Status "pass" -Message "$ToolName was not found in PATH"
        } else {
            Add-Check -Id "dev_tool_absent_$ToolName" -Description "$ToolName is absent from PATH" -Status "fail" -Message "$ToolName was found in PATH" -Data @{ paths = @($Commands | ForEach-Object { $_.Source }) }
        }
    }

    if ([string]::IsNullOrWhiteSpace($ManifestPath)) {
        $ManifestPath = Join-Path $SharedRoot "release\manifest.json"
    }
    if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
        Add-Check -Id "release_manifest_exists" -Description "release manifest exists" -Status "fail" -Message "release manifest not found: $ManifestPath"
        Save-Results
        return
    }
    $Manifest = Get-Content -Encoding UTF8 -Raw -LiteralPath $ManifestPath | ConvertFrom-Json
    $ExpectedFile = [string]$Manifest.toolhub.installer.file
    $ExpectedSize = [int64]$Manifest.toolhub.installer.size
    $ExpectedSha256 = [string]$Manifest.toolhub.installer.sha256
    if ([string]::IsNullOrWhiteSpace($InstallerPath)) {
        $InstallerPath = Join-Path (Join-Path $SharedRoot "release\dist_installer") $ExpectedFile
    }
    $Artifacts["manifest_path"] = $ManifestPath
    $Artifacts["installer_path"] = $InstallerPath
    $Artifacts["expected_size"] = $ExpectedSize
    $Artifacts["expected_sha256"] = $ExpectedSha256

    if (-not (Test-Path -LiteralPath $InstallerPath -PathType Leaf)) {
        Add-Check -Id "installer_exists" -Description "installer exists" -Status "fail" -Message "installer not found: $InstallerPath"
        Save-Results
        return
    }
    Add-Check -Id "installer_exists" -Description "installer exists" -Status "pass" -Message "installer found: $InstallerPath"

    $InstallerItem = Get-Item -LiteralPath $InstallerPath
    $ActualSize = [int64]$InstallerItem.Length
    $ActualSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $InstallerPath).Hash.ToLowerInvariant()
    if ($ActualSize -eq $ExpectedSize) {
        Add-Check -Id "installer_size_matches_manifest" -Description "installer size matches manifest" -Status "pass" -Message "installer size matched: $ActualSize"
    } else {
        Add-Check -Id "installer_size_matches_manifest" -Description "installer size matches manifest" -Status "fail" -Message "installer size mismatch. expected=$ExpectedSize actual=$ActualSize"
    }
    if ($ActualSha256 -eq $ExpectedSha256.ToLowerInvariant()) {
        Add-Check -Id "installer_sha256_matches_manifest" -Description "installer sha256 matches manifest" -Status "pass" -Message "installer sha256 matched: $ActualSha256"
    } else {
        Add-Check -Id "installer_sha256_matches_manifest" -Description "installer sha256 matches manifest" -Status "fail" -Message "installer sha256 mismatch. expected=$ExpectedSha256 actual=$ActualSha256"
    }

    $InstallerCompleted = Start-InstallerAndRecord -CheckId "installer_completed" -Description "installer completes"
    if (-not $InstallerCompleted) {
        Save-Results
        return
    }

    $InstallDir = Join-Path $env:LOCALAPPDATA "Programs\ToolHub"
    $UserDataDir = Join-Path $env:LOCALAPPDATA "ToolHub"
    $ToolHubExe = Join-Path $InstallDir "ToolHub.exe"
    $Artifacts["install_dir"] = $InstallDir
    $Artifacts["user_data_dir"] = $UserDataDir
    $Artifacts["toolhub_exe"] = $ToolHubExe

    if (Test-Path -LiteralPath $ToolHubExe -PathType Leaf) {
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

    if (Find-FirstExistingPath -BasePaths $PayloadRoots -RelativePath "runtime\python\python.exe") {
        Add-Check -Id "bundled_python_exists" -Description "bundled runtime python exists" -Status "pass" -Message "runtime/python/python.exe found"
    } else {
        Add-Check -Id "bundled_python_exists" -Description "bundled runtime python exists" -Status "fail" -Message "runtime/python/python.exe not found"
    }
    if (Find-FirstExistingPath -BasePaths $PayloadRoots -RelativePath "runtime\web_automation_runtime") {
        Add-Check -Id "web_automation_runtime_exists" -Description "bundled web automation runtime exists" -Status "pass" -Message "runtime/web_automation_runtime found"
    } else {
        Add-Check -Id "web_automation_runtime_exists" -Description "bundled web automation runtime exists" -Status "fail" -Message "runtime/web_automation_runtime not found"
    }

    if (Test-Path -LiteralPath $ToolHubExe -PathType Leaf) {
        $ToolHubProcess = Start-Process -FilePath $ToolHubExe -PassThru -ErrorAction Stop
        Start-Sleep -Seconds $LaunchSeconds
        if ($ToolHubProcess.HasExited) {
            if ($ToolHubProcess.ExitCode -eq 0) {
                Add-Check -Id "toolhub_launch" -Description "ToolHub launches" -Status "pass" -Message "ToolHub launched and exited with code 0"
            } else {
                Add-Check -Id "toolhub_launch" -Description "ToolHub launches" -Status "fail" -Message "ToolHub exited early with code $($ToolHubProcess.ExitCode)"
            }
        } else {
            Add-Check -Id "toolhub_launch" -Description "ToolHub launches" -Status "pass" -Message "ToolHub stayed running for $LaunchSeconds seconds"
            Add-ManualPromptCheck -Id "app_cards_visible" -Description "app cards are visible in GUI" -Prompt "Are app cards visible in the ToolHub window?"
            Add-ManualPromptCheck -Id "sample_gui_app_launch" -Description "sample_gui_app launches from installed ToolHub" -Prompt "Did sample_gui_app launch successfully?"
            Add-ManualPromptCheck -Id "sample_playwright_app_launch" -Description "sample_playwright_app launches from installed ToolHub" -Prompt "Did sample_playwright_app launch successfully?"
            $ToolHubProcess.CloseMainWindow() | Out-Null
            Start-Sleep -Seconds 3
            if (-not $ToolHubProcess.HasExited) {
                Stop-Process -Id $ToolHubProcess.Id -Force -ErrorAction SilentlyContinue
            }
        }
    } else {
        Add-Check -Id "toolhub_launch" -Description "ToolHub launches" -Status "not_run" -Message "ToolHub.exe was not found"
    }

    if (Test-Path -LiteralPath $UserDataDir -PathType Container) {
        Add-Check -Id "user_data_dir_created" -Description "user data dir is created" -Status "pass" -Message "user data dir exists: $UserDataDir"
    } else {
        Add-Check -Id "user_data_dir_created" -Description "user data dir is created" -Status "fail" -Message "user data dir not found: $UserDataDir"
    }

    if ($SkipUninstall) {
        Add-Check -Id "uninstall_completed" -Description "ToolHub uninstalls" -Status "not_run" -Message "SkipUninstall was specified"
        Add-Check -Id "user_data_preserved_after_uninstall" -Description "user data remains after uninstall" -Status "not_run" -Message "SkipUninstall was specified"
        Add-Check -Id "reinstall_completed" -Description "ToolHub reinstalls" -Status "not_run" -Message "SkipUninstall was specified"
        Add-Check -Id "user_data_preserved_after_reinstall" -Description "user data remains after reinstall" -Status "not_run" -Message "SkipUninstall was specified"
    } else {
        $UninstallSucceeded = $false
        $UninstallCandidates = @()
        if (Test-Path -LiteralPath $InstallDir -PathType Container) {
            $UninstallCandidates = @(Get-ChildItem -LiteralPath $InstallDir -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -match "uninstall" })
        }
        if ($UninstallCandidates.Count -eq 0) {
            Add-Check -Id "uninstall_completed" -Description "ToolHub uninstalls" -Status "manual_check" -Message "no uninstaller executable was found under $InstallDir"
            Add-Check -Id "user_data_preserved_after_uninstall" -Description "user data remains after uninstall" -Status "not_run" -Message "uninstaller was not found"
            Add-Check -Id "reinstall_completed" -Description "ToolHub reinstalls" -Status "not_run" -Message "uninstaller was not found"
            Add-Check -Id "user_data_preserved_after_reinstall" -Description "user data remains after reinstall" -Status "not_run" -Message "uninstaller was not found"
        } else {
            $UninstallerPath = $UninstallCandidates[0].FullName
            $Artifacts["uninstaller_path"] = $UninstallerPath
            Write-Host "Start the ToolHub uninstaller UI. Do not select any option that deletes user data."
            $UninstallerProcess = Start-Process -FilePath $UninstallerPath -PassThru -ErrorAction Stop
            if (-not $UninstallerProcess.WaitForExit([Math]::Max(1, $UninstallerTimeoutMinutes) * 60 * 1000)) {
                Add-Check -Id "uninstall_completed" -Description "ToolHub uninstalls" -Status "manual_check" -Message "uninstaller did not exit within $UninstallerTimeoutMinutes minutes"
            } elseif ($UninstallerProcess.ExitCode -eq 0) {
                Add-Check -Id "uninstall_completed" -Description "ToolHub uninstalls" -Status "pass" -Message "uninstaller exited with code 0"
                $UninstallSucceeded = $true
            } else {
                Add-Check -Id "uninstall_completed" -Description "ToolHub uninstalls" -Status "fail" -Message "uninstaller exited with code $($UninstallerProcess.ExitCode)"
            }

            if (Test-Path -LiteralPath $UserDataDir -PathType Container) {
                Add-Check -Id "user_data_preserved_after_uninstall" -Description "user data remains after uninstall" -Status "pass" -Message "user data dir still exists: $UserDataDir"
            } else {
                Add-Check -Id "user_data_preserved_after_uninstall" -Description "user data remains after uninstall" -Status "fail" -Message "user data dir was removed after uninstall: $UserDataDir"
            }

            if ($SkipReinstall) {
                Add-Check -Id "reinstall_completed" -Description "ToolHub reinstalls" -Status "not_run" -Message "SkipReinstall was specified"
                Add-Check -Id "user_data_preserved_after_reinstall" -Description "user data remains after reinstall" -Status "not_run" -Message "SkipReinstall was specified"
            } elseif ($UninstallSucceeded) {
                $ReinstallSucceeded = Start-InstallerAndRecord -CheckId "reinstall_completed" -Description "ToolHub reinstalls"
                if ($ReinstallSucceeded) {
                    if (Test-Path -LiteralPath $UserDataDir -PathType Container) {
                        Add-Check -Id "user_data_preserved_after_reinstall" -Description "user data remains after reinstall" -Status "pass" -Message "user data dir exists after reinstall: $UserDataDir"
                    } else {
                        Add-Check -Id "user_data_preserved_after_reinstall" -Description "user data remains after reinstall" -Status "fail" -Message "user data dir missing after reinstall: $UserDataDir"
                    }
                } else {
                    Add-Check -Id "user_data_preserved_after_reinstall" -Description "user data remains after reinstall" -Status "not_run" -Message "reinstall did not complete"
                }
            } else {
                Add-Check -Id "reinstall_completed" -Description "ToolHub reinstalls" -Status "not_run" -Message "uninstall did not complete successfully"
                Add-Check -Id "user_data_preserved_after_reinstall" -Description "user data remains after reinstall" -Status "not_run" -Message "uninstall did not complete successfully"
            }
        }
    }

    Save-Results
} catch {
    Add-Check -Id "unexpected_error" -Description "unexpected script error" -Status "fail" -Message $_.Exception.Message
    Save-Results -FatalMessage $_.Exception.Message
}
