param(
    [switch]$RequireRuntime,
    [switch]$Json
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RuntimeDir = Join-Path $Root "runtime"
$PythonDir = Join-Path $RuntimeDir "python"
$PythonExe = Join-Path $PythonDir "python.exe"
$WebRuntimeDir = Join-Path $RuntimeDir "web_automation_runtime"
$AppEnvsDir = Join-Path $RuntimeDir "app_envs"
$AppsDir = Join-Path $Root "apps"

$Items = New-Object System.Collections.ArrayList
$Failures = New-Object System.Collections.ArrayList

function To-RelativePath {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return "" }
    $Full = [System.IO.Path]::GetFullPath($Path)
    $TrimChars = [char[]]@([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)
    $RootFull = [System.IO.Path]::GetFullPath($Root).TrimEnd($TrimChars)
    if ($Full.StartsWith($RootFull, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $Full.Substring($RootFull.Length).TrimStart([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar) -replace "\\", "/"
    }
    return $Full
}

function Add-Item {
    param(
        [string]$Category,
        [string]$Id,
        [string]$State,
        [string]$Severity,
        [string]$Reason,
        [string]$Path = ""
    )
    $Record = [pscustomobject]@{
        category = $Category
        id = $Id
        state = $State
        severity = $Severity
        reason = $Reason
        path = To-RelativePath $Path
    }
    [void]$Items.Add($Record)
    if ($Severity -eq "fail") {
        [void]$Failures.Add($Record)
    }
}

function Get-NonPlaceholderItems {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        return @()
    }
    return @(Get-ChildItem -LiteralPath $Path -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notin @(".gitkeep", "README.md") })
}

if (Test-Path -LiteralPath $RuntimeDir -PathType Container) {
    Add-Item "runtime_root" "runtime" "present" "ok" "runtime/ exists." $RuntimeDir
} else {
    Add-Item "runtime_root" "runtime" "missing" "fail" "runtime/ is missing." $RuntimeDir
}

$PythonFound = Test-Path -LiteralPath $PythonExe -PathType Leaf
$PythonVersion = $null
if ($PythonFound) {
    try {
        $PythonVersion = (& $PythonExe "--version" 2>&1 | Select-Object -First 1)
        & $PythonExe "-c" "import json, pathlib, sys; print('stdlib-ok')" | Out-Null
        Add-Item "python_runtime" "python-runtime" "present" "ok" "Python runtime executable and minimal stdlib check passed. $PythonVersion" $PythonExe
    } catch {
        $Severity = if ($RequireRuntime) { "fail" } else { "warn" }
        Add-Item "python_runtime" "python-runtime" "present_but_failed" $Severity "python.exe exists but failed a version or stdlib check: $($_.Exception.Message)" $PythonExe
    }
} else {
    $Severity = if ($RequireRuntime) { "fail" } else { "warn" }
    Add-Item "python_runtime" "python-runtime" "missing" $Severity "Python runtime executable is not bundled. Use prepare_runtime.ps1 -PythonArchive <zip> -PythonSha256 <sha256> with an approved archive." $PythonExe
}

$WebRuntimeFiles = Get-NonPlaceholderItems $WebRuntimeDir
if ($WebRuntimeFiles.Count -gt 0) {
    Add-Item "web_automation_runtime" "web-automation-runtime" "present" "ok" "Web automation runtime has $($WebRuntimeFiles.Count) non-placeholder item(s)." $WebRuntimeDir
} else {
    $Severity = if ($RequireRuntime) { "fail" } else { "warn" }
    Add-Item "web_automation_runtime" "web-automation-runtime" "missing" $Severity "Web automation runtime files are not bundled. Use prepare_runtime.ps1 -WebRuntimeArchive <zip> -WebRuntimeSha256 <sha256> with an approved archive." $WebRuntimeDir
}

$SourceApps = @()
if (Test-Path -LiteralPath $AppsDir -PathType Container) {
    $SourceApps = @(Get-ChildItem -LiteralPath $AppsDir -Directory |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "app.yaml") -PathType Leaf } |
        Sort-Object Name)
}

$MissingAppEnv = @()
$PresentAppEnv = @()
foreach ($App in $SourceApps) {
    $EnvPath = Join-Path $AppEnvsDir $App.Name
    if (Test-Path -LiteralPath $EnvPath -PathType Container) {
        $RuntimeItems = Get-NonPlaceholderItems $EnvPath
        $State = if ($RuntimeItems.Count -gt 0) { "present_with_files" } else { "skeleton_only" }
        $PresentAppEnv += $App.Name
        Add-Item "app_env" $App.Name $State "info" "App env is optional for normal frozen-folder apps; this directory is compatibility-only unless the app explicitly uses app-env mode." $EnvPath
    } else {
        $MissingAppEnv += $App.Name
    }
}

if ($MissingAppEnv.Count -gt 0) {
    Add-Item "app_env_policy" "frozen-folder-app-env" "missing_for_source_apps" "info" "runtime/app_envs/<app_id> is missing for $($MissingAppEnv.Count) source app(s). This is acceptable for normal App Studio frozen-folder apps and should not be treated as runtime packaging failure." $AppEnvsDir
} else {
    Add-Item "app_env_policy" "frozen-folder-app-env" "all_source_apps_have_app_env_dirs" "info" "All source apps have app_env directories, but normal frozen-folder apps still do not require them at runtime." $AppEnvsDir
}

$Report = [pscustomobject]@{
    generated_at = (Get-Date).ToString("s")
    project_root = $Root
    require_runtime = [bool]$RequireRuntime
    summary = [pscustomobject]@{
        ok = ($Failures.Count -eq 0)
        python_runtime_found = [bool]$PythonFound
        python_version = $PythonVersion
        web_runtime_files_found = ($WebRuntimeFiles.Count -gt 0)
        web_runtime_file_count = $WebRuntimeFiles.Count
        source_app_count = $SourceApps.Count
        app_env_dirs_present = $PresentAppEnv.Count
        app_env_dirs_missing = $MissingAppEnv.Count
        failures = $Failures.Count
    }
    items = @($Items)
}

if ($Json) {
    $Report | ConvertTo-Json -Depth 10
} else {
    Write-Host "== Runtime readiness =="
    foreach ($Item in @($Items)) {
        $Prefix = switch ($Item.severity) {
            "ok" { "[OK]" }
            "warn" { "[WARN]" }
            "fail" { "[FAIL]" }
            default { "[INFO]" }
        }
        Write-Host "$Prefix $($Item.id): $($Item.reason)"
    }
}

if ($Failures.Count -gt 0) {
    exit 1
}
