param(
    [switch]$DryRun,
    [string]$ToolHubExePath = "",
    [string]$ResultsDir = "",
    [int]$LaunchSeconds = 15
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path
if ([string]::IsNullOrWhiteSpace($ResultsDir)) {
    $ResultsDir = Join-Path $ScriptDir "results"
}
New-Item -ItemType Directory -Force -Path $ResultsDir | Out-Null

$StartedAt = Get-Date
$Stamp = $StartedAt.ToString("yyyyMMdd_HHmmss")
$OriginalPath = $env:Path
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

function Test-CommandVisibleInPath {
    param([string]$Name, [string]$PathValue)

    $PathExtensions = @(".exe", ".cmd", ".bat", ".ps1", "")
    if ($env:PATHEXT) {
        $PathExtensions = @($env:PATHEXT.Split(";") + "")
    }

    foreach ($Part in @($PathValue.Split(";"))) {
        if ([string]::IsNullOrWhiteSpace($Part)) {
            continue
        }
        foreach ($Extension in $PathExtensions) {
            $Candidate = Join-Path $Part ($Name + $Extension)
            if (Test-Path -LiteralPath $Candidate -PathType Leaf) {
                return $Candidate
            }
        }
    }
    return ""
}

function Resolve-ToolHubExe {
    param([string]$ExplicitPath)

    $Candidates = New-Object System.Collections.Generic.List[string]
    if (-not [string]::IsNullOrWhiteSpace($ExplicitPath)) {
        $Candidates.Add($ExplicitPath) | Out-Null
    }
    $Candidates.Add((Join-Path $env:LOCALAPPDATA "Programs\ToolHub\ToolHub.exe")) | Out-Null
    $Candidates.Add((Join-Path $env:LOCALAPPDATA "Programs\ToolHub\toolhub.exe")) | Out-Null
    $Candidates.Add((Join-Path $RepoRoot "release\staging\installer_payload\ToolHub.exe")) | Out-Null
    $Candidates.Add((Join-Path $RepoRoot "release\staging\installer_payload\toolhub.exe")) | Out-Null
    $Candidates.Add((Join-Path $RepoRoot "launcher\src-tauri\target\release\ToolHub.exe")) | Out-Null
    $Candidates.Add((Join-Path $RepoRoot "launcher\src-tauri\target\release\toolhub.exe")) | Out-Null

    foreach ($Candidate in $Candidates) {
        if (-not [string]::IsNullOrWhiteSpace($Candidate) -and (Test-Path -LiteralPath $Candidate -PathType Leaf)) {
            return (Get-Item -LiteralPath $Candidate).FullName
        }
    }
    return ""
}

function Resolve-RuntimeRoot {
    param([string]$ExePath)

    $Candidates = New-Object System.Collections.Generic.List[string]
    if (-not [string]::IsNullOrWhiteSpace($ExePath)) {
        $ExeDir = Split-Path -Parent $ExePath
        $Candidates.Add($ExeDir) | Out-Null
        $Candidates.Add((Join-Path $ExeDir "resources")) | Out-Null
    }
    $Candidates.Add((Join-Path $RepoRoot "release\staging\installer_payload")) | Out-Null
    $Candidates.Add($RepoRoot) | Out-Null

    foreach ($Candidate in $Candidates) {
        $PythonPath = Join-Path $Candidate "runtime\python\python.exe"
        $WebRuntimePath = Join-Path $Candidate "runtime\web_automation_runtime"
        if ((Test-Path -LiteralPath $PythonPath -PathType Leaf) -and (Test-Path -LiteralPath $WebRuntimePath -PathType Container)) {
            return $Candidate
        }
    }
    return ""
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
        test_name = "toolhub_beta_isolated_path_test"
        dry_run = [bool]$DryRun
        started_at = $StartedAt.ToString("o")
        finished_at = (Get-Date).ToString("o")
        overall_status = $OverallStatus
        fatal_message = $FatalMessage
        repo_root = $RepoRoot
        results_dir = $ResultsDir
        note = "This test hides developer tools from PATH for this script/process only. It is not proof of a clean PC."
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
    $JsonPath = Join-Path $ResultsDir "isolated_path_result_$Stamp.json"
    $MarkdownPath = Join-Path $ResultsDir "isolated_path_result_$Stamp.md"
    $LatestJsonPath = Join-Path $ResultsDir "latest_isolated_path_result.json"
    $LatestMarkdownPath = Join-Path $ResultsDir "latest_isolated_path_result.md"
    Write-Utf8NoBom -Path $JsonPath -Content $Json
    Write-Utf8NoBom -Path $LatestJsonPath -Content $Json

    $Lines = New-Object System.Collections.Generic.List[string]
    $Lines.Add("# ToolHub Beta Isolated PATH Test Result") | Out-Null
    $Lines.Add("") | Out-Null
    $Lines.Add(("- overall_status: {0}" -f $OverallStatus)) | Out-Null
    $Lines.Add(("- dry_run: {0}" -f ([bool]$DryRun))) | Out-Null
    $Lines.Add("- note: This hides developer tools from PATH for this script/process only. It is not proof of a clean PC.") | Out-Null
    $Lines.Add("") | Out-Null
    $Lines.Add("| status | id | message |") | Out-Null
    $Lines.Add("| --- | --- | --- |") | Out-Null
    foreach ($Check in $Checks) {
        $SafeMessage = ([string]$Check.message).Replace("|", "\|")
        $Lines.Add(("| {0} | {1} | {2} |" -f $Check.status, $Check.id, $SafeMessage)) | Out-Null
    }
    Write-Utf8NoBom -Path $MarkdownPath -Content ($Lines -join [Environment]::NewLine)
    Write-Utf8NoBom -Path $LatestMarkdownPath -Content ($Lines -join [Environment]::NewLine)

    Write-Host $Json
    Write-Host "Isolated PATH result JSON: $JsonPath"
    Write-Host "Isolated PATH result Markdown: $MarkdownPath"

    if ($OverallStatus -eq "fail") {
        exit 1
    }
}

try {
    $SystemRoot = if ($env:SystemRoot) { $env:SystemRoot } else { "C:\Windows" }
    $IsolatedPath = @(
        (Join-Path $SystemRoot "System32"),
        $SystemRoot,
        (Join-Path $SystemRoot "System32\Wbem"),
        (Join-Path $SystemRoot "System32\WindowsPowerShell\v1.0")
    ) -join ";"
    $Artifacts["isolated_path"] = $IsolatedPath
    $Artifacts["original_path_changed_permanently"] = $false

    $env:Path = $IsolatedPath
    foreach ($ToolName in @("python", "pip", "node", "npm", "rustc", "cargo", "tauri")) {
        $Found = Test-CommandVisibleInPath -Name $ToolName -PathValue $IsolatedPath
        if ([string]::IsNullOrWhiteSpace($Found)) {
            Add-Check -Id "path_hidden_$ToolName" -Description "$ToolName is hidden from isolated PATH" -Status "pass" -Message "$ToolName is not visible in the isolated PATH"
        } else {
            Add-Check -Id "path_hidden_$ToolName" -Description "$ToolName is hidden from isolated PATH" -Status "fail" -Message "$ToolName is still visible in isolated PATH: $Found"
        }
    }

    $ResolvedExe = Resolve-ToolHubExe -ExplicitPath $ToolHubExePath
    $Artifacts["toolhub_exe"] = $ResolvedExe
    if ([string]::IsNullOrWhiteSpace($ResolvedExe)) {
        Add-Check -Id "toolhub_exe_exists" -Description "ToolHub.exe can be found for PATH isolation test" -Status "fail" -Message "ToolHub.exe was not found. Install ToolHub or pass -ToolHubExePath."
        Save-Results
        return
    }
    Add-Check -Id "toolhub_exe_exists" -Description "ToolHub.exe can be found for PATH isolation test" -Status "pass" -Message "ToolHub.exe found: $ResolvedExe"

    $RuntimeRoot = Resolve-RuntimeRoot -ExePath $ResolvedExe
    $Artifacts["runtime_root"] = $RuntimeRoot
    if ([string]::IsNullOrWhiteSpace($RuntimeRoot)) {
        Add-Check -Id "runtime_root_exists" -Description "runtime root is available near payload or repo" -Status "fail" -Message "No runtime root with runtime/python/python.exe and runtime/web_automation_runtime was found."
    } else {
        Add-Check -Id "runtime_root_exists" -Description "runtime root is available near payload or repo" -Status "pass" -Message "runtime root found: $RuntimeRoot"
        Add-Check -Id "runtime_python_exists" -Description "runtime/python/python.exe exists" -Status "pass" -Message (Join-Path $RuntimeRoot "runtime\python\python.exe")
        Add-Check -Id "web_automation_runtime_exists" -Description "runtime/web_automation_runtime exists" -Status "pass" -Message (Join-Path $RuntimeRoot "runtime\web_automation_runtime")
    }

    if ($DryRun) {
        Add-Check -Id "toolhub_launch" -Description "ToolHub launches with isolated PATH" -Status "not_run" -Message "DryRun specified. ToolHub.exe was not launched."
        Add-Check -Id "isolated_user_data_created" -Description "isolated LOCALAPPDATA ToolHub dir is created" -Status "not_run" -Message "DryRun specified."
        Add-Check -Id "isolated_logs_created" -Description "logs are created under isolated LOCALAPPDATA" -Status "not_run" -Message "DryRun specified."
        Save-Results
        return
    }

    $IsolatedLocalAppData = Join-Path $ResultsDir ("localappdata_" + $Stamp)
    $IsolatedAppData = Join-Path $ResultsDir ("appdata_" + $Stamp)
    New-Item -ItemType Directory -Force -Path $IsolatedLocalAppData | Out-Null
    New-Item -ItemType Directory -Force -Path $IsolatedAppData | Out-Null
    $Artifacts["isolated_local_app_data"] = $IsolatedLocalAppData
    $Artifacts["isolated_app_data"] = $IsolatedAppData

    $ProcessInfo = New-Object System.Diagnostics.ProcessStartInfo
    $ProcessInfo.FileName = $ResolvedExe
    $ProcessInfo.WorkingDirectory = Split-Path -Parent $ResolvedExe
    $ProcessInfo.UseShellExecute = $false
    $ProcessInfo.EnvironmentVariables["PATH"] = $IsolatedPath
    $ProcessInfo.EnvironmentVariables["LOCALAPPDATA"] = $IsolatedLocalAppData
    $ProcessInfo.EnvironmentVariables["APPDATA"] = $IsolatedAppData

    $Process = [System.Diagnostics.Process]::Start($ProcessInfo)
    Start-Sleep -Seconds $LaunchSeconds
    if ($Process.HasExited) {
        if ($Process.ExitCode -eq 0) {
            Add-Check -Id "toolhub_launch" -Description "ToolHub launches with isolated PATH" -Status "pass" -Message "ToolHub launched and exited with code 0"
        } else {
            Add-Check -Id "toolhub_launch" -Description "ToolHub launches with isolated PATH" -Status "fail" -Message "ToolHub exited early with code $($Process.ExitCode)"
        }
    } else {
        Add-Check -Id "toolhub_launch" -Description "ToolHub launches with isolated PATH" -Status "pass" -Message "ToolHub stayed running for $LaunchSeconds seconds with isolated PATH"
        $Closed = $Process.CloseMainWindow()
        Start-Sleep -Seconds 3
        if (-not $Process.HasExited) {
            Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
        }
        $Artifacts["close_main_window"] = $Closed
    }

    $IsolatedToolHubData = Join-Path $IsolatedLocalAppData "ToolHub"
    if (Test-Path -LiteralPath $IsolatedToolHubData -PathType Container) {
        Add-Check -Id "isolated_user_data_created" -Description "isolated LOCALAPPDATA ToolHub dir is created" -Status "pass" -Message "isolated user data dir exists: $IsolatedToolHubData"
        $LogFiles = @(Get-ChildItem -LiteralPath $IsolatedToolHubData -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Extension -in @(".log", ".json") })
        if ($LogFiles.Count -gt 0) {
            Add-Check -Id "isolated_logs_created" -Description "logs are created under isolated LOCALAPPDATA" -Status "pass" -Message "$($LogFiles.Count) log/json files found"
        } else {
            Add-Check -Id "isolated_logs_created" -Description "logs are created under isolated LOCALAPPDATA" -Status "warning" -Message "isolated user data dir exists, but no .log/.json files were found"
        }
    } else {
        Add-Check -Id "isolated_user_data_created" -Description "isolated LOCALAPPDATA ToolHub dir is created" -Status "fail" -Message "isolated user data dir not found: $IsolatedToolHubData"
        Add-Check -Id "isolated_logs_created" -Description "logs are created under isolated LOCALAPPDATA" -Status "not_run" -Message "isolated user data dir was not created"
    }

    Save-Results
} catch {
    Add-Check -Id "unexpected_error" -Description "unexpected script error" -Status "fail" -Message $_.Exception.Message
    Save-Results -FatalMessage $_.Exception.Message
} finally {
    $env:Path = $OriginalPath
}
