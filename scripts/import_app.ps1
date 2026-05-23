param(
    [Parameter(Mandatory = $true)]
    [string]$Entry,
    [string]$AppId,
    [string]$Name,
    [string]$Version,
    [ValidateSet("auto", "app-env", "frozen-folder", "existing-exe", "shared-env")]
    [string]$BuildMode = "shared-env",
    [string]$IconPrompt,
    [string]$IconPng,
    [switch]$CreateAppEnv,
    [switch]$RebuildAppEnv,
    [switch]$SkipAppEnvBuild,
    [switch]$GenerateLock,
    [switch]$SkipLock,
    [switch]$BuildFrozenFolder,
    [switch]$RebuildFrozenFolder,
    [switch]$SkipFrozenBuild,
    [switch]$VerifyRuntime,
    [switch]$ShowTerminal,
    [switch]$DryRun,
    [switch]$Suggest,
    [switch]$Apply
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

function Find-Python {
    $Python = Get-Command "python" -ErrorAction SilentlyContinue
    if ($Python) { return $Python.Source }
    $Py = Get-Command "py" -ErrorAction SilentlyContinue
    if ($Py) { return $Py.Source }
    return $null
}

try {
    $Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
    $StudioMain = Join-Path $Root "tools\app_studio\main.py"
    if (-not (Test-Path -LiteralPath $StudioMain -PathType Leaf)) {
        throw "ToolHub App Studio main script was not found: $StudioMain"
    }

    $ModeCount = @(@($DryRun, $Suggest, $Apply) | Where-Object { $_ }).Count
    if ($ModeCount -ne 1) {
        throw "Specify exactly one of -DryRun, -Suggest, or -Apply."
    }
    if ([System.IO.Path]::GetExtension($Entry).ToLowerInvariant() -eq ".exe") {
        throw "Normal App Studio registration accepts Python source only. Existing exe registration is not available in this flow."
    }
    if ($CreateAppEnv -or $RebuildAppEnv -or $SkipAppEnvBuild) {
        throw "Normal App Studio registration uses an internal build_env, not runtime/app_envs options."
    }
    if ($SkipLock -or $SkipFrozenBuild) {
        throw "Normal App Studio registration always generates requirements.lock and manages a shared runtime."
    }

    $Python = Find-Python
    if (-not $Python) {
        throw "python or py was not found. App Studio requires a development Python to run."
    }

    if ($BuildMode -ne "auto" -and $BuildMode -ne "shared-env") {
        Write-Host "BuildMode '$BuildMode' is a legacy option and will be ignored. Using shared-env."
    }

    $ArgsList = @($StudioMain, "import", "--entry", $Entry, "--build-mode", "shared-env", "--generate-lock", "--verify-runtime")
    if ($AppId) { $ArgsList += @("--app-id", $AppId) }
    if ($Name) { $ArgsList += @("--name", $Name) }
    if ($Version) { $ArgsList += @("--version", $Version) }
    if ($IconPrompt) { $ArgsList += @("--icon-prompt", $IconPrompt) }
    if ($IconPng) { $ArgsList += @("--icon-png", $IconPng) }
    if ($ShowTerminal) { $ArgsList += "--show-terminal" }
    if ($DryRun) { $ArgsList += "--dry-run" }
    if ($Suggest) { $ArgsList += "--suggest" }
    if ($Apply) { $ArgsList += "--apply" }

    Push-Location $Root
    try {
        & $Python @ArgsList
        $ExitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }

    if ($ExitCode -ne 0) {
        throw "ToolHub App Studio failed with exit code: $ExitCode"
    }
    exit 0
}
catch {
    Write-Host "ToolHub App Studio error: $($_.Exception.Message)"
    exit 1
}
