param(
    [string]$SharedRoot = "",
    [string]$InstallerPath = "",
    [string]$ManifestPath = "",
    [string]$ResultsDir = "",
    [string]$InstallerWriteErrorPath = "",
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
$ExpectedInstallDir = Join-Path $env:LOCALAPPDATA "Programs\ToolHub"
$ExpectedToolHubExe = Join-Path $ExpectedInstallDir "ToolHub.exe"
$UserDataDir = Join-Path $env:LOCALAPPDATA "ToolHub"
$CandidateInstallDirs = New-Object System.Collections.Generic.List[string]
$DiscoveredInstallDirs = New-Object System.Collections.Generic.List[string]
$DiscoveredToolHubExes = New-Object System.Collections.Generic.List[object]
$PayloadLayoutSummary = New-Object System.Collections.Generic.List[object]
$ShortcutRecords = @()
$UninstallRegistryRecords = @()
$ToolHubProcessRecords = @()
$InstallerExecution = [ordered]@{}
$LogSummary = [ordered]@{
    searched_paths = @()
    files = @()
    matched_lines = @()
}
$LaunchedToolHubExe = ""
$ResourceRootCandidate = ""
$LikelyFailureCategory = "unknown"
$InstallDirUserDataCollision = $false
$DirtyVmPreviousInstallResidue = $false
$PreInstallState = [ordered]@{}
$EnvironmentSnapshot = [ordered]@{
    local_app_data = $env:LOCALAPPDATA
    app_data = $env:APPDATA
    program_files = $env:ProgramFiles
    program_files_x86 = ${env:ProgramFiles(x86)}
    user_profile = $env:USERPROFILE
    username = $env:USERNAME
    computer_name = $env:COMPUTERNAME
    powershell_version = $PSVersionTable.PSVersion.ToString()
    process_architecture = [System.Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture.ToString()
}

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
        [object]$Data = $null
    )
    if ($null -eq $Data) {
        $Data = @{}
    }
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

function Get-CheckStatus {
    param([string]$Id)
    $Match = @($Checks | Where-Object { $_.id -eq $Id } | Select-Object -First 1)
    if ($Match.Count -eq 0) {
        return ""
    }
    return [string]$Match[0].status
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

function Add-UniquePath {
    param(
        [System.Collections.Generic.List[string]]$List,
        [string]$Path,
        [switch]$OnlyIfExists
    )
    if ([string]::IsNullOrWhiteSpace($Path)) {
        return
    }
    try {
        $FullPath = [System.IO.Path]::GetFullPath($Path)
    } catch {
        return
    }
    if ($OnlyIfExists -and -not (Test-Path -LiteralPath $FullPath)) {
        return
    }
    if (-not $List.Contains($FullPath)) {
        $List.Add($FullPath) | Out-Null
    }
}

function Test-PathUnderRoot {
    param([string]$Path, [string]$Root)
    if ([string]::IsNullOrWhiteSpace($Path) -or [string]::IsNullOrWhiteSpace($Root)) {
        return $false
    }
    try {
        $FullPath = [System.IO.Path]::GetFullPath($Path).TrimEnd("\")
        $FullRoot = [System.IO.Path]::GetFullPath($Root).TrimEnd("\")
        return ($FullPath.Equals($FullRoot, [System.StringComparison]::OrdinalIgnoreCase) -or
            $FullPath.StartsWith("$FullRoot\", [System.StringComparison]::OrdinalIgnoreCase))
    } catch {
        return $false
    }
}

function Get-PathState {
    param([string]$Path)
    $Exists = Test-Path -LiteralPath $Path
    $Type = "missing"
    $ChildCount = 0
    $ToolHubExeCount = 0
    if ($Exists) {
        if (Test-Path -LiteralPath $Path -PathType Container) {
            $Type = "directory"
            $ChildCount = @(Get-ChildItem -LiteralPath $Path -Force -ErrorAction SilentlyContinue).Count
            $ToolHubExeCount = @(Get-ChildItem -LiteralPath $Path -File -Filter "ToolHub*.exe" -Recurse -ErrorAction SilentlyContinue).Count
        } elseif (Test-Path -LiteralPath $Path -PathType Leaf) {
            $Type = "file"
        }
    }
    return [ordered]@{
        path = $Path
        exists = $Exists
        type = $Type
        child_count = $ChildCount
        toolhub_exe_count = $ToolHubExeCount
    }
}

function Record-PreInstallState {
    $LocalToolHubDir = Join-Path $env:LOCALAPPDATA "ToolHub"
    $ProgramFilesToolHubDir = Join-Path $env:ProgramFiles "ToolHub"
    $ProgramFilesX86ToolHubDir = ""
    if (-not [string]::IsNullOrWhiteSpace(${env:ProgramFiles(x86)})) {
        $ProgramFilesX86ToolHubDir = Join-Path ${env:ProgramFiles(x86)} "ToolHub"
    }

    $ExistingShortcuts = @(Get-ShortcutRecords)
    $ExistingRegistry = @(Get-UninstallRegistryRecords)
    $ExistingProcesses = @(Get-ToolHubProcessRecords)
    $PathStates = @(
        (Get-PathState -Path $ExpectedInstallDir),
        (Get-PathState -Path $LocalToolHubDir),
        (Get-PathState -Path $ProgramFilesToolHubDir)
    )
    if (-not [string]::IsNullOrWhiteSpace($ProgramFilesX86ToolHubDir)) {
        $PathStates += (Get-PathState -Path $ProgramFilesX86ToolHubDir)
    }

    $script:DirtyVmPreviousInstallResidue = $false
    foreach ($State in $PathStates) {
        if ([bool]$State.exists) {
            $script:DirtyVmPreviousInstallResidue = $true
            break
        }
    }
    if ($ExistingShortcuts.Count -gt 0 -or $ExistingRegistry.Count -gt 0 -or $ExistingProcesses.Count -gt 0) {
        $script:DirtyVmPreviousInstallResidue = $true
    }

    $script:PreInstallState = [ordered]@{
        captured_at = (Get-Date).ToString("o")
        expected_install_dir = $ExpectedInstallDir
        user_data_or_legacy_install_dir = $LocalToolHubDir
        path_states = @($PathStates)
        existing_shortcuts = @($ExistingShortcuts)
        existing_uninstall_registry = @($ExistingRegistry)
        existing_toolhub_processes = @($ExistingProcesses)
        dirty_vm_previous_install_residue = $script:DirtyVmPreviousInstallResidue
    }
}

function Get-PathFromCommandLine {
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) {
        return ""
    }
    $Trimmed = $Text.Trim()
    if ($Trimmed -match '^\s*"([^"]+?\.exe)"') {
        return $Matches[1]
    }
    if ($Trimmed -match '^\s*([A-Za-z]:\\[^\s"]+?\.exe)') {
        return $Matches[1]
    }
    if ($Trimmed -match '([A-Za-z]:\\[^"]+?\.exe)') {
        return $Matches[1]
    }
    return ""
}

function Get-ShortcutRecords {
    $Records = @()
    $ShortcutRoots = @(
        (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu"),
        (Join-Path $env:ProgramData "Microsoft\Windows\Start Menu"),
        (Join-Path $env:USERPROFILE "Desktop")
    )
    try {
        $Shell = New-Object -ComObject WScript.Shell
        foreach ($Root in $ShortcutRoots) {
            if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
                continue
            }
            $Links = @(Get-ChildItem -LiteralPath $Root -Filter "*.lnk" -Recurse -ErrorAction SilentlyContinue |
                Where-Object { $_.BaseName -like "*ToolHub*" })
            foreach ($Link in $Links) {
                try {
                    $Shortcut = $Shell.CreateShortcut($Link.FullName)
                    $Records += [ordered]@{
                        path = $Link.FullName
                        target_path = [string]$Shortcut.TargetPath
                        arguments = [string]$Shortcut.Arguments
                        working_directory = [string]$Shortcut.WorkingDirectory
                    }
                } catch {
                    $Records += [ordered]@{
                        path = $Link.FullName
                        target_path = ""
                        arguments = ""
                        working_directory = ""
                        error = $_.Exception.Message
                    }
                }
            }
        }
    } catch {
        $Records += [ordered]@{
            path = ""
            target_path = ""
            arguments = ""
            working_directory = ""
            error = $_.Exception.Message
        }
    }
    return @($Records)
}

function Get-UninstallRegistryRecords {
    $Records = @()
    $RegistryRoots = @(
        "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )
    foreach ($Root in $RegistryRoots) {
        $Items = @(Get-ItemProperty -Path $Root -ErrorAction SilentlyContinue)
        foreach ($Item in $Items) {
            $Fields = @(
                [string]$Item.DisplayName,
                [string]$Item.DisplayIcon,
                [string]$Item.InstallLocation,
                [string]$Item.UninstallString
            ) -join " "
            if ($Fields -notlike "*ToolHub*") {
                continue
            }
            $Records += [ordered]@{
                registry_path = [string]$Item.PSPath
                display_name = [string]$Item.DisplayName
                display_version = [string]$Item.DisplayVersion
                publisher = [string]$Item.Publisher
                install_location = [string]$Item.InstallLocation
                display_icon = [string]$Item.DisplayIcon
                uninstall_string = [string]$Item.UninstallString
                quiet_uninstall_string = [string]$Item.QuietUninstallString
            }
        }
    }
    return @($Records)
}

function Get-ToolHubProcessRecords {
    $Records = @()
    try {
        $Processes = @(Get-CimInstance Win32_Process -Filter "Name LIKE 'ToolHub%'" -ErrorAction SilentlyContinue)
        foreach ($Process in $Processes) {
            $Records += [ordered]@{
                id = [int]$Process.ProcessId
                name = [string]$Process.Name
                executable_path = [string]$Process.ExecutablePath
                command_line = [string]$Process.CommandLine
            }
        }
    } catch {
        $Processes = @(Get-Process -Name "ToolHub*" -ErrorAction SilentlyContinue)
        foreach ($Process in $Processes) {
            $Path = ""
            try {
                $Path = [string]$Process.Path
            } catch {
                $Path = ""
            }
            $Records += [ordered]@{
                id = [int]$Process.Id
                name = [string]$Process.ProcessName
                executable_path = $Path
                command_line = ""
            }
        }
    }
    return @($Records)
}

function Add-ToolHubExeRecord {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return
    }
    try {
        $Item = Get-Item -LiteralPath $Path
        $FullPath = $Item.FullName
        foreach ($Existing in $DiscoveredToolHubExes) {
            if ([string]$Existing.path -eq $FullPath) {
                return
            }
        }
        $DiscoveredToolHubExes.Add([ordered]@{
            path = $FullPath
            directory = $Item.DirectoryName
            size = [int64]$Item.Length
            last_write_time_utc = $Item.LastWriteTimeUtc.ToString("o")
        }) | Out-Null
    } catch {
        return
    }
}

function Test-PayloadRoot {
    param([string]$Root)
    $Exists = Test-Path -LiteralPath $Root -PathType Container
    $Apps = Join-Path $Root "apps"
    $Runner = Join-Path $Root "runner"
    $Runtime = Join-Path $Root "runtime"
    $ConfigDefault = Join-Path $Root "config.default"
    $Release = Join-Path $Root "release"
    $ReleaseManifest = Join-Path $Release "manifest.json"
    $AppManifest = Join-Path $Release "app_manifest.json"
    $PythonExe = Join-Path $Runtime "python\python.exe"
    $WebRuntime = Join-Path $Runtime "web_automation_runtime"
    $AppYamlCount = 0
    if (Test-Path -LiteralPath $Apps -PathType Container) {
        $AppYamlCount = @(Get-ChildItem -LiteralPath $Apps -Filter "app.yaml" -Recurse -ErrorAction SilentlyContinue).Count
    }
    return [ordered]@{
        root = $Root
        exists = $Exists
        apps = (Test-Path -LiteralPath $Apps -PathType Container)
        app_yaml_count = $AppYamlCount
        runner = (Test-Path -LiteralPath $Runner -PathType Container)
        runtime = (Test-Path -LiteralPath $Runtime -PathType Container)
        config_default = (Test-Path -LiteralPath $ConfigDefault -PathType Container)
        release = (Test-Path -LiteralPath $Release -PathType Container)
        release_manifest = (Test-Path -LiteralPath $ReleaseManifest -PathType Leaf)
        app_manifest = (Test-Path -LiteralPath $AppManifest -PathType Leaf)
        runtime_python = (Test-Path -LiteralPath $PythonExe -PathType Leaf)
        web_automation_runtime = (Test-Path -LiteralPath $WebRuntime -PathType Container)
    }
}

function Add-PayloadRootSummary {
    param([string]$Root)
    if ([string]::IsNullOrWhiteSpace($Root)) {
        return
    }
    try {
        $FullRoot = [System.IO.Path]::GetFullPath($Root)
    } catch {
        return
    }
    foreach ($Existing in $PayloadLayoutSummary) {
        if ([string]$Existing.root -eq $FullRoot) {
            return
        }
    }
    $PayloadLayoutSummary.Add((Test-PayloadRoot -Root $FullRoot)) | Out-Null
}

function Add-PayloadRootVariants {
    param([string]$Root)
    if ([string]::IsNullOrWhiteSpace($Root)) {
        return
    }
    Add-PayloadRootSummary -Root $Root
    Add-PayloadRootSummary -Root (Join-Path $Root "resources")
    Add-PayloadRootSummary -Root (Join-Path (Join-Path $Root "_up_") "_up_")
    Add-PayloadRootSummary -Root (Join-Path (Join-Path (Join-Path $Root "resources") "_up_") "_up_")
}

function Update-InstallDiscovery {
    Add-UniquePath -List $CandidateInstallDirs -Path $ExpectedInstallDir
    Add-UniquePath -List $CandidateInstallDirs -Path (Join-Path $env:LOCALAPPDATA "ToolHub")
    Add-UniquePath -List $CandidateInstallDirs -Path (Join-Path $env:ProgramFiles "ToolHub")
    if (-not [string]::IsNullOrWhiteSpace(${env:ProgramFiles(x86)})) {
        Add-UniquePath -List $CandidateInstallDirs -Path (Join-Path ${env:ProgramFiles(x86)} "ToolHub")
    }
    Add-UniquePath -List $CandidateInstallDirs -Path (Join-Path $env:LOCALAPPDATA "Programs\com.toolhub.launcher")
    Add-UniquePath -List $CandidateInstallDirs -Path (Join-Path $env:LOCALAPPDATA "Programs\ToolHub\ToolHub")

    foreach ($Path in $CandidateInstallDirs.ToArray()) {
        Add-UniquePath -List $DiscoveredInstallDirs -Path $Path -OnlyIfExists
    }

    $ProgramsDir = Join-Path $env:LOCALAPPDATA "Programs"
    if (Test-Path -LiteralPath $ProgramsDir -PathType Container) {
        foreach ($Pattern in @("ToolHub*", "*ToolHub*", "com.toolhub*")) {
            $Matches = @(Get-ChildItem -LiteralPath $ProgramsDir -Directory -Filter $Pattern -ErrorAction SilentlyContinue)
            foreach ($Match in $Matches) {
                Add-UniquePath -List $CandidateInstallDirs -Path $Match.FullName
                Add-UniquePath -List $DiscoveredInstallDirs -Path $Match.FullName -OnlyIfExists
            }
        }
    }

    $script:ShortcutRecords = @(Get-ShortcutRecords)
    foreach ($Shortcut in $ShortcutRecords) {
        if (-not [string]::IsNullOrWhiteSpace($Shortcut.target_path)) {
            Add-ToolHubExeRecord -Path $Shortcut.target_path
            $Parent = Split-Path -Parent $Shortcut.target_path
            Add-UniquePath -List $CandidateInstallDirs -Path $Parent
            Add-UniquePath -List $DiscoveredInstallDirs -Path $Parent -OnlyIfExists
        }
        if (-not [string]::IsNullOrWhiteSpace($Shortcut.working_directory)) {
            Add-UniquePath -List $CandidateInstallDirs -Path $Shortcut.working_directory
            Add-UniquePath -List $DiscoveredInstallDirs -Path $Shortcut.working_directory -OnlyIfExists
        }
    }

    $script:UninstallRegistryRecords = @(Get-UninstallRegistryRecords)
    foreach ($Entry in $UninstallRegistryRecords) {
        foreach ($Path in @($Entry.install_location)) {
            Add-UniquePath -List $CandidateInstallDirs -Path $Path
            Add-UniquePath -List $DiscoveredInstallDirs -Path $Path -OnlyIfExists
        }
        foreach ($CommandText in @($Entry.display_icon, $Entry.uninstall_string, $Entry.quiet_uninstall_string)) {
            $CommandPath = Get-PathFromCommandLine -Text $CommandText
            if (-not [string]::IsNullOrWhiteSpace($CommandPath)) {
                Add-ToolHubExeRecord -Path $CommandPath
                $Parent = Split-Path -Parent $CommandPath
                Add-UniquePath -List $CandidateInstallDirs -Path $Parent
                Add-UniquePath -List $DiscoveredInstallDirs -Path $Parent -OnlyIfExists
            }
        }
    }

    $script:ToolHubProcessRecords = @(Get-ToolHubProcessRecords)
    foreach ($Process in $ToolHubProcessRecords) {
        if (-not [string]::IsNullOrWhiteSpace($Process.executable_path)) {
            Add-ToolHubExeRecord -Path $Process.executable_path
            $Parent = Split-Path -Parent $Process.executable_path
            Add-UniquePath -List $CandidateInstallDirs -Path $Parent
            Add-UniquePath -List $DiscoveredInstallDirs -Path $Parent -OnlyIfExists
        }
    }

    Add-ToolHubExeRecord -Path $ExpectedToolHubExe
    foreach ($InstallDir in $DiscoveredInstallDirs.ToArray()) {
        $ExeMatches = @(Get-ChildItem -LiteralPath $InstallDir -File -Filter "ToolHub*.exe" -Recurse -ErrorAction SilentlyContinue)
        foreach ($Exe in $ExeMatches) {
            Add-ToolHubExeRecord -Path $Exe.FullName
        }
    }

    foreach ($InstallDir in $DiscoveredInstallDirs.ToArray()) {
        Add-PayloadRootVariants -Root $InstallDir
    }
    foreach ($Exe in $DiscoveredToolHubExes) {
        Add-PayloadRootVariants -Root $Exe.directory
    }

    $script:InstallDirUserDataCollision = $false
    try {
        $UserDataFull = [System.IO.Path]::GetFullPath($UserDataDir).TrimEnd("\")
        foreach ($InstallDir in $DiscoveredInstallDirs.ToArray()) {
            $InstallDirFull = [System.IO.Path]::GetFullPath($InstallDir).TrimEnd("\")
            if ($InstallDirFull.Equals($UserDataFull, [System.StringComparison]::OrdinalIgnoreCase)) {
                $script:InstallDirUserDataCollision = $true
                break
            }
        }
    } catch {
        $script:InstallDirUserDataCollision = $false
    }
}

function Find-PayloadRoot {
    foreach ($Summary in $PayloadLayoutSummary) {
        if ($Summary.apps -and $Summary.runner -and $Summary.app_manifest) {
            return [string]$Summary.root
        }
    }
    foreach ($Summary in $PayloadLayoutSummary) {
        if ($Summary.apps -and $Summary.runner) {
            return [string]$Summary.root
        }
    }
    return ""
}

function Get-PayloadFlag {
    param([string]$Name)
    foreach ($Summary in $PayloadLayoutSummary) {
        if ([bool]$Summary.$Name) {
            return $true
        }
    }
    return $false
}

function Get-LogSummary {
    $SearchRoots = @(
        (Join-Path $UserDataDir "data\logs"),
        (Join-Path $UserDataDir "logs"),
        $UserDataDir
    )
    $Searched = @()
    $Files = @()
    $MatchedLines = @()
    foreach ($Root in $SearchRoots) {
        if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
            continue
        }
        $Searched += $Root
        $LogFiles = @(Get-ChildItem -LiteralPath $Root -File -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.Extension -in @(".log", ".json", ".txt") } |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 25)
        foreach ($File in $LogFiles) {
            $Files += [ordered]@{
                path = $File.FullName
                size = [int64]$File.Length
                last_write_time_utc = $File.LastWriteTimeUtc.ToString("o")
            }
            try {
                $Matches = @(Select-String -LiteralPath $File.FullName -Pattern "error|failed|panic|project root|app_manifest|app.yaml|list_apps|アプリ" -SimpleMatch:$false -ErrorAction SilentlyContinue |
                    Select-Object -First 20)
                foreach ($Match in $Matches) {
                    $MatchedLines += [ordered]@{
                        path = $File.FullName
                        line = [int]$Match.LineNumber
                        text = [string]$Match.Line
                    }
                }
            } catch {
                $MatchedLines += [ordered]@{
                    path = $File.FullName
                    line = 0
                    text = "log scan failed: $($_.Exception.Message)"
                }
            }
        }
    }
    return [ordered]@{
        searched_paths = @($Searched)
        files = @($Files)
        matched_lines = @($MatchedLines)
    }
}

function Set-LikelyFailureCategory {
    if ((Get-CheckStatus "installer_completed") -ne "pass") {
        if ($DirtyVmPreviousInstallResidue -or (Test-PathUnderRoot -Path $InstallerWriteErrorPath -Root $UserDataDir)) {
            $script:LikelyFailureCategory = "dirty_vm_previous_install_residue"
            return
        }
        $script:LikelyFailureCategory = "installer_not_completed"
        return
    }
    if ($DiscoveredToolHubExes.Count -eq 0 -and $DiscoveredInstallDirs.Count -eq 0) {
        $script:LikelyFailureCategory = "install_dir_unexpected"
        return
    }
    if ($InstallDirUserDataCollision -or -not (Test-Path -LiteralPath $ExpectedInstallDir -PathType Container)) {
        $script:LikelyFailureCategory = "install_dir_unexpected"
        return
    }
    if ($DiscoveredToolHubExes.Count -gt 0 -and -not (Get-PayloadFlag "runner") -and -not (Get-PayloadFlag "apps") -and -not (Get-PayloadFlag "release")) {
        $script:LikelyFailureCategory = "installed_payload_missing"
        return
    }
    if (-not (Get-PayloadFlag "apps")) {
        $script:LikelyFailureCategory = "apps_not_in_payload"
        return
    }
    if (-not (Get-PayloadFlag "app_manifest")) {
        $script:LikelyFailureCategory = "app_manifest_load_failed"
        return
    }
    foreach ($Line in @($LogSummary.matched_lines)) {
        $Text = [string]$Line.text
        if ($Text -match "project root|root was not found") {
            $script:LikelyFailureCategory = "root_resolution_failed"
            return
        }
        if ($Text -match "app.yaml") {
            $script:LikelyFailureCategory = "app_yaml_load_failed"
            return
        }
    }
    if ((Get-CheckStatus "app_cards_visible") -eq "fail") {
        $script:LikelyFailureCategory = "root_resolution_failed"
        return
    }
    if ((Get-CheckStatus "user_data_dir_created") -eq "fail") {
        $script:LikelyFailureCategory = "user_data_or_config_issue"
        return
    }
    $script:LikelyFailureCategory = "unknown"
}

function Save-Results {
    param([string]$FatalMessage = "")
    $script:ResourceRootCandidate = Find-PayloadRoot
    $script:LogSummary = Get-LogSummary
    Set-LikelyFailureCategory

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
        schema_version = 2
        test_name = "toolhub_beta_vm_install_test"
        started_at = $StartedAt.ToString("o")
        finished_at = (Get-Date).ToString("o")
        overall_status = $OverallStatus
        fatal_message = $FatalMessage
        shared_root = $SharedRoot
        results_dir = $ResultsDir
        environment = $EnvironmentSnapshot
        local_app_data = $env:LOCALAPPDATA
        user_data_dir = $UserDataDir
        expected_install_dir = $ExpectedInstallDir
        expected_install_dir_exists = (Test-Path -LiteralPath $ExpectedInstallDir -PathType Container)
        pre_install_state = $PreInstallState
        dirty_vm_previous_install_residue = $DirtyVmPreviousInstallResidue
        installer_write_error_path = $InstallerWriteErrorPath
        install_dir_user_data_collision = $InstallDirUserDataCollision
        candidate_install_dirs = @($CandidateInstallDirs.ToArray())
        discovered_install_dirs = @($DiscoveredInstallDirs.ToArray())
        discovered_toolhub_exes = @($DiscoveredToolHubExes.ToArray())
        launched_toolhub_exe = $LaunchedToolHubExe
        shortcut_records = @($ShortcutRecords)
        uninstall_registry_records = @($UninstallRegistryRecords)
        toolhub_process_records = @($ToolHubProcessRecords)
        installer_execution = $InstallerExecution
        payload_layout_summary = @($PayloadLayoutSummary.ToArray())
        apps_dir_found = (Get-PayloadFlag "apps")
        runner_dir_found = (Get-PayloadFlag "runner")
        runtime_dir_found = (Get-PayloadFlag "runtime")
        release_manifest_found = (Get-PayloadFlag "release_manifest")
        app_manifest_found = (Get-PayloadFlag "app_manifest")
        resource_root_candidate = $ResourceRootCandidate
        log_summary = $LogSummary
        likely_failure_category = $LikelyFailureCategory
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

    $Json = $Report | ConvertTo-Json -Depth 12
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
    $Lines.Add(("- likely_failure_category: {0}" -f $LikelyFailureCategory)) | Out-Null
    $Lines.Add(("- expected_install_dir: {0}" -f $ExpectedInstallDir)) | Out-Null
    $Lines.Add(("- expected_install_dir_exists: {0}" -f (Test-Path -LiteralPath $ExpectedInstallDir -PathType Container))) | Out-Null
    $Lines.Add(("- user_data_dir: {0}" -f $UserDataDir)) | Out-Null
    $Lines.Add(("- dirty_vm_previous_install_residue: {0}" -f $DirtyVmPreviousInstallResidue)) | Out-Null
    if (-not [string]::IsNullOrWhiteSpace($InstallerWriteErrorPath)) {
        $Lines.Add(("- installer_write_error_path: {0}" -f $InstallerWriteErrorPath)) | Out-Null
    }
    $Lines.Add(("- install_dir_user_data_collision: {0}" -f $InstallDirUserDataCollision)) | Out-Null
    $Lines.Add(("- launched_toolhub_exe: {0}" -f $LaunchedToolHubExe)) | Out-Null
    $Lines.Add(("- resource_root_candidate: {0}" -f $ResourceRootCandidate)) | Out-Null
    $Lines.Add("") | Out-Null
    $Lines.Add("## Discovered Install Dirs") | Out-Null
    foreach ($Path in $DiscoveredInstallDirs.ToArray()) {
        $Lines.Add(("- {0}" -f $Path)) | Out-Null
    }
    if ($DiscoveredInstallDirs.Count -eq 0) {
        $Lines.Add("- none") | Out-Null
    }
    $Lines.Add("") | Out-Null
    $Lines.Add("## Discovered ToolHub Exes") | Out-Null
    foreach ($Exe in $DiscoveredToolHubExes.ToArray()) {
        $Lines.Add(("- {0}" -f $Exe.path)) | Out-Null
    }
    if ($DiscoveredToolHubExes.Count -eq 0) {
        $Lines.Add("- none") | Out-Null
    }
    $Lines.Add("") | Out-Null
    $Lines.Add("## Payload Layout Summary") | Out-Null
    $Lines.Add("| root | apps | runner | runtime | release_manifest | app_manifest | app_yaml_count |") | Out-Null
    $Lines.Add("| --- | --- | --- | --- | --- | --- | --- |") | Out-Null
    foreach ($Summary in $PayloadLayoutSummary.ToArray()) {
        $Lines.Add(("| {0} | {1} | {2} | {3} | {4} | {5} | {6} |" -f $Summary.root, $Summary.apps, $Summary.runner, $Summary.runtime, $Summary.release_manifest, $Summary.app_manifest, $Summary.app_yaml_count)) | Out-Null
    }
    if ($PayloadLayoutSummary.Count -eq 0) {
        $Lines.Add("| none | False | False | False | False | False | 0 |") | Out-Null
    }
    $Lines.Add("") | Out-Null
    $Lines.Add("## Checks") | Out-Null
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
    $BeforeProcesses = @(Get-ToolHubProcessRecords)
    $InstallerExecution = [ordered]@{
        installer_path = $InstallerPath
        installer_write_error_path = $InstallerWriteErrorPath
        started_at = (Get-Date).ToString("o")
        process_id = $null
        exit_code = $null
        timed_out = $false
        finished_at = ""
        toolhub_processes_before = @($BeforeProcesses)
        toolhub_processes_after = @()
    }
    try {
        $StartedInstaller = Start-Process -FilePath $InstallerPath -PassThru -ErrorAction Stop
        $InstallerExecution.process_id = $StartedInstaller.Id
        if (-not $StartedInstaller.WaitForExit([Math]::Max(1, $InstallerTimeoutMinutes) * 60 * 1000)) {
            $InstallerExecution.timed_out = $true
            $InstallerExecution.finished_at = (Get-Date).ToString("o")
            $InstallerExecution.toolhub_processes_after = @(Get-ToolHubProcessRecords)
            Add-Check -Id $CheckId -Description $Description -Status "manual_check" -Message "installer did not exit within $InstallerTimeoutMinutes minutes" -Data $InstallerExecution
            return $false
        }
        $InstallerExecution.exit_code = $StartedInstaller.ExitCode
        $InstallerExecution.finished_at = (Get-Date).ToString("o")
        $InstallerExecution.toolhub_processes_after = @(Get-ToolHubProcessRecords)
        if ($StartedInstaller.ExitCode -eq 0) {
            Add-Check -Id $CheckId -Description $Description -Status "pass" -Message "installer exited with code 0" -Data $InstallerExecution
            return $true
        }
        Add-Check -Id $CheckId -Description $Description -Status "fail" -Message "installer exited with code $($StartedInstaller.ExitCode)" -Data $InstallerExecution
        return $false
    } catch {
        $InstallerExecution.finished_at = (Get-Date).ToString("o")
        $InstallerExecution.error = $_.Exception.Message
        Add-Check -Id $CheckId -Description $Description -Status "fail" -Message "installer start failed: $($_.Exception.Message)" -Data $InstallerExecution
        return $false
    } finally {
        $script:InstallerExecution = $InstallerExecution
    }
}

function Select-LaunchExe {
    foreach ($Process in @(Get-ToolHubProcessRecords)) {
        if (-not [string]::IsNullOrWhiteSpace($Process.executable_path) -and (Test-Path -LiteralPath $Process.executable_path -PathType Leaf)) {
            return [string]$Process.executable_path
        }
    }
    foreach ($Exe in $DiscoveredToolHubExes.ToArray()) {
        if ([string]$Exe.path -like "*ToolHub.exe") {
            return [string]$Exe.path
        }
    }
    if ($DiscoveredToolHubExes.Count -gt 0) {
        return [string]$DiscoveredToolHubExes[0].path
    }
    return ""
}

function Record-ToolHubLaunch {
    $RunningBeforeLaunch = @(Get-ToolHubProcessRecords)
    if ($RunningBeforeLaunch.Count -gt 0) {
        $script:LaunchedToolHubExe = [string]$RunningBeforeLaunch[0].executable_path
        Add-Check -Id "toolhub_launch" -Description "ToolHub launches" -Status "pass" -Message "ToolHub was already running after installer" -Data @{ processes = @($RunningBeforeLaunch) }
        Add-ManualPromptCheck -Id "app_cards_visible" -Description "app cards are visible in GUI" -Prompt "Are app cards visible in the ToolHub window?"
        Add-ManualPromptCheck -Id "sample_gui_app_launch" -Description "sample_gui_app launches from installed ToolHub" -Prompt "Did sample_gui_app launch successfully?"
        Add-ManualPromptCheck -Id "sample_playwright_app_launch" -Description "sample_playwright_app launches from installed ToolHub" -Prompt "Did sample_playwright_app launch successfully?"
        return
    }

    $LaunchExe = Select-LaunchExe
    if ([string]::IsNullOrWhiteSpace($LaunchExe)) {
        Add-Check -Id "toolhub_launch" -Description "ToolHub launches" -Status "not_run" -Message "No ToolHub.exe candidate was found"
        return
    }
    $script:LaunchedToolHubExe = $LaunchExe
    try {
        $ToolHubProcess = Start-Process -FilePath $LaunchExe -PassThru -ErrorAction Stop
        Start-Sleep -Seconds $LaunchSeconds
        $RunningAfterLaunch = @(Get-ToolHubProcessRecords)
        if ($ToolHubProcess.HasExited) {
            if ($ToolHubProcess.ExitCode -eq 0) {
                Add-Check -Id "toolhub_launch" -Description "ToolHub launches" -Status "pass" -Message "ToolHub launched and exited with code 0" -Data @{ launched_exe = $LaunchExe; processes = @($RunningAfterLaunch) }
            } else {
                Add-Check -Id "toolhub_launch" -Description "ToolHub launches" -Status "fail" -Message "ToolHub exited early with code $($ToolHubProcess.ExitCode)" -Data @{ launched_exe = $LaunchExe; processes = @($RunningAfterLaunch) }
            }
        } else {
            Add-Check -Id "toolhub_launch" -Description "ToolHub launches" -Status "pass" -Message "ToolHub stayed running for $LaunchSeconds seconds" -Data @{ launched_exe = $LaunchExe; processes = @($RunningAfterLaunch) }
            Add-ManualPromptCheck -Id "app_cards_visible" -Description "app cards are visible in GUI" -Prompt "Are app cards visible in the ToolHub window?"
            Add-ManualPromptCheck -Id "sample_gui_app_launch" -Description "sample_gui_app launches from installed ToolHub" -Prompt "Did sample_gui_app launch successfully?"
            Add-ManualPromptCheck -Id "sample_playwright_app_launch" -Description "sample_playwright_app launches from installed ToolHub" -Prompt "Did sample_playwright_app launch successfully?"
            $ToolHubProcess.CloseMainWindow() | Out-Null
            Start-Sleep -Seconds 3
            if (-not $ToolHubProcess.HasExited) {
                Stop-Process -Id $ToolHubProcess.Id -Force -ErrorAction SilentlyContinue
            }
        }
    } catch {
        Add-Check -Id "toolhub_launch" -Description "ToolHub launches" -Status "fail" -Message "ToolHub launch failed: $($_.Exception.Message)" -Data @{ launched_exe = $LaunchExe }
    }
}

function Find-UninstallCandidates {
    $Candidates = New-Object System.Collections.Generic.List[string]
    foreach ($Entry in $UninstallRegistryRecords) {
        foreach ($CommandText in @($Entry.uninstall_string, $Entry.quiet_uninstall_string)) {
            $CommandPath = Get-PathFromCommandLine -Text $CommandText
            Add-UniquePath -List $Candidates -Path $CommandPath -OnlyIfExists
        }
    }
    foreach ($InstallDir in $DiscoveredInstallDirs.ToArray()) {
        $Matches = @(Get-ChildItem -LiteralPath $InstallDir -File -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match "uninstall|unins" })
        foreach ($Match in $Matches) {
            Add-UniquePath -List $Candidates -Path $Match.FullName -OnlyIfExists
        }
    }
    return @($Candidates.ToArray())
}

try {
    Add-Check -Id "environment_snapshot_recorded" -Description "VM environment paths are recorded" -Status "pass" -Message "environment snapshot recorded" -Data $EnvironmentSnapshot

    Record-PreInstallState
    if ($DirtyVmPreviousInstallResidue) {
        Add-Check -Id "dirty_vm_previous_install_residue" -Description "previous ToolHub install residue is absent before install" -Status "warning" -Message "ToolHub-related paths, shortcuts, registry entries, or processes existed before installer execution. Treat this as a dirty VM rerun, not a clean proof." -Data $PreInstallState
    } else {
        Add-Check -Id "dirty_vm_previous_install_residue" -Description "previous ToolHub install residue is absent before install" -Status "pass" -Message "no ToolHub-related pre-install residue was detected" -Data $PreInstallState
    }
    if (-not [string]::IsNullOrWhiteSpace($InstallerWriteErrorPath)) {
        $WriteErrorStatus = if (Test-PathUnderRoot -Path $InstallerWriteErrorPath -Root $UserDataDir) { "warning" } else { "manual_check" }
        Add-Check -Id "installer_write_error_path_recorded" -Description "installer write error path was recorded by tester" -Status $WriteErrorStatus -Message "tester-recorded installer write error path: $InstallerWriteErrorPath" -Data @{ installer_write_error_path = $InstallerWriteErrorPath; user_data_dir = $UserDataDir }
    }

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
    $Artifacts["expected_install_dir"] = $ExpectedInstallDir
    $Artifacts["expected_toolhub_exe"] = $ExpectedToolHubExe
    $Artifacts["user_data_dir"] = $UserDataDir

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
    Update-InstallDiscovery

    if (Test-Path -LiteralPath $ExpectedInstallDir -PathType Container) {
        Add-Check -Id "expected_install_dir_exists" -Description "expected install dir exists" -Status "pass" -Message "expected install dir exists: $ExpectedInstallDir"
    } else {
        Add-Check -Id "expected_install_dir_exists" -Description "expected install dir exists" -Status "fail" -Message "expected install dir is missing: $ExpectedInstallDir"
    }
    if ($DiscoveredInstallDirs.Count -gt 0) {
        Add-Check -Id "install_location_discovery" -Description "install location discovery finds candidates" -Status "pass" -Message "discovered $($DiscoveredInstallDirs.Count) install dir candidate(s)" -Data @{ discovered_install_dirs = @($DiscoveredInstallDirs.ToArray()); shortcuts = @($ShortcutRecords); registry = @($UninstallRegistryRecords) }
    } else {
        Add-Check -Id "install_location_discovery" -Description "install location discovery finds candidates" -Status "fail" -Message "no install dir candidates were discovered" -Data @{ candidate_install_dirs = @($CandidateInstallDirs.ToArray()); shortcuts = @($ShortcutRecords); registry = @($UninstallRegistryRecords) }
    }
    if ($DiscoveredInstallDirs.Count -eq 0) {
        Add-Check -Id "install_dir_user_data_separated" -Description "install dir and user data dir are separated" -Status "not_run" -Message "install dir was not discovered"
    } elseif ($InstallDirUserDataCollision) {
        Add-Check -Id "install_dir_user_data_separated" -Description "install dir and user data dir are separated" -Status "fail" -Message "install dir collides with user data dir: $UserDataDir" -Data @{ discovered_install_dirs = @($DiscoveredInstallDirs.ToArray()); user_data_dir = $UserDataDir }
    } else {
        Add-Check -Id "install_dir_user_data_separated" -Description "install dir and user data dir are separated" -Status "pass" -Message "no discovered install dir equals user data dir" -Data @{ discovered_install_dirs = @($DiscoveredInstallDirs.ToArray()); user_data_dir = $UserDataDir }
    }
    if ($DiscoveredToolHubExes.Count -gt 0) {
        Add-Check -Id "toolhub_exe_discovery" -Description "ToolHub.exe discovery finds candidates" -Status "pass" -Message "discovered $($DiscoveredToolHubExes.Count) ToolHub exe candidate(s)" -Data @{ discovered_toolhub_exes = @($DiscoveredToolHubExes.ToArray()) }
    } else {
        Add-Check -Id "toolhub_exe_discovery" -Description "ToolHub.exe discovery finds candidates" -Status "fail" -Message "no ToolHub exe candidates were discovered"
    }

    foreach ($RequiredPath in @("runner", "apps", "runtime", "config_default", "release")) {
        $Field = if ($RequiredPath -eq "config_default") { "config_default" } else { $RequiredPath }
        $Found = Get-PayloadFlag $Field
        $CheckIdName = $RequiredPath.Replace(".", "_")
        if ($Found) {
            Add-Check -Id "payload_$($CheckIdName)_exists" -Description "$RequiredPath payload exists" -Status "pass" -Message "$RequiredPath found in discovered payload layout"
        } else {
            Add-Check -Id "payload_$($CheckIdName)_exists" -Description "$RequiredPath payload exists" -Status "fail" -Message "$RequiredPath not found in discovered payload layout" -Data @{ payload_layout_summary = @($PayloadLayoutSummary.ToArray()) }
        }
    }
    if (Get-PayloadFlag "runtime_python") {
        Add-Check -Id "bundled_python_exists" -Description "bundled runtime python exists" -Status "pass" -Message "runtime/python/python.exe found in discovered payload layout"
    } else {
        Add-Check -Id "bundled_python_exists" -Description "bundled runtime python exists" -Status "fail" -Message "runtime/python/python.exe not found in discovered payload layout"
    }
    if (Get-PayloadFlag "web_automation_runtime") {
        Add-Check -Id "web_automation_runtime_exists" -Description "bundled web automation runtime exists" -Status "pass" -Message "runtime/web_automation_runtime found in discovered payload layout"
    } else {
        Add-Check -Id "web_automation_runtime_exists" -Description "bundled web automation runtime exists" -Status "fail" -Message "runtime/web_automation_runtime not found in discovered payload layout"
    }
    if (Get-PayloadFlag "release_manifest") {
        Add-Check -Id "release_manifest_found" -Description "installed release manifest exists" -Status "pass" -Message "release/manifest.json found in discovered payload layout"
    } else {
        Add-Check -Id "release_manifest_found" -Description "installed release manifest exists" -Status "fail" -Message "release/manifest.json not found in discovered payload layout"
    }
    if (Get-PayloadFlag "app_manifest") {
        Add-Check -Id "app_manifest_found" -Description "installed app manifest exists" -Status "pass" -Message "release/app_manifest.json found in discovered payload layout"
    } else {
        Add-Check -Id "app_manifest_found" -Description "installed app manifest exists" -Status "fail" -Message "release/app_manifest.json not found in discovered payload layout"
    }

    if ($InstallerCompleted) {
        Record-ToolHubLaunch
    } else {
        Add-Check -Id "toolhub_launch" -Description "ToolHub launches" -Status "not_run" -Message "installer did not complete"
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
        $UninstallCandidates = @(Find-UninstallCandidates)
        if ($UninstallCandidates.Count -eq 0) {
            Add-Check -Id "uninstall_completed" -Description "ToolHub uninstalls" -Status "manual_check" -Message "no uninstaller executable was found in registry or discovered install dirs"
            Add-Check -Id "user_data_preserved_after_uninstall" -Description "user data remains after uninstall" -Status "not_run" -Message "uninstaller was not found"
            Add-Check -Id "reinstall_completed" -Description "ToolHub reinstalls" -Status "not_run" -Message "uninstaller was not found"
            Add-Check -Id "user_data_preserved_after_reinstall" -Description "user data remains after reinstall" -Status "not_run" -Message "uninstaller was not found"
        } else {
            $UninstallerPath = $UninstallCandidates[0]
            $Artifacts["uninstaller_path"] = $UninstallerPath
            Write-Host "Start the ToolHub uninstaller UI. Do not select any option that deletes user data."
            $UninstallerProcess = Start-Process -FilePath $UninstallerPath -PassThru -ErrorAction Stop
            if (-not $UninstallerProcess.WaitForExit([Math]::Max(1, $UninstallerTimeoutMinutes) * 60 * 1000)) {
                Add-Check -Id "uninstall_completed" -Description "ToolHub uninstalls" -Status "manual_check" -Message "uninstaller did not exit within $UninstallerTimeoutMinutes minutes" -Data @{ uninstaller_path = $UninstallerPath }
            } elseif ($UninstallerProcess.ExitCode -eq 0) {
                Add-Check -Id "uninstall_completed" -Description "ToolHub uninstalls" -Status "pass" -Message "uninstaller exited with code 0" -Data @{ uninstaller_path = $UninstallerPath }
                $UninstallSucceeded = $true
            } else {
                Add-Check -Id "uninstall_completed" -Description "ToolHub uninstalls" -Status "fail" -Message "uninstaller exited with code $($UninstallerProcess.ExitCode)" -Data @{ uninstaller_path = $UninstallerPath }
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
                    Update-InstallDiscovery
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
