param(
    [Parameter(Mandatory = $true)]
    [string]$Entry,
    [string]$AppId,
    [string]$Name,
    [ValidateSet("auto", "app-env", "frozen-folder", "existing-exe")]
    [string]$BuildMode = "auto",
    [string]$IconPrompt,
    [switch]$CreateAppEnv,
    [switch]$RebuildAppEnv,
    [switch]$SkipAppEnvBuild,
    [switch]$GenerateLock,
    [switch]$SkipLock,
    [switch]$BuildFrozenFolder,
    [switch]$RebuildFrozenFolder,
    [switch]$SkipFrozenBuild,
    [switch]$VerifyRuntime,
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

    $Python = Find-Python
    if (-not $Python) {
        throw "python or py was not found. App Studio requires a development Python to run."
    }

    $ArgsList = @($StudioMain, "import", "--entry", $Entry, "--build-mode", $BuildMode)
    if ($AppId) { $ArgsList += @("--app-id", $AppId) }
    if ($Name) { $ArgsList += @("--name", $Name) }
    if ($IconPrompt) { $ArgsList += @("--icon-prompt", $IconPrompt) }
    if ($CreateAppEnv) { $ArgsList += "--create-app-env" }
    if ($RebuildAppEnv) { $ArgsList += "--rebuild-app-env" }
    if ($SkipAppEnvBuild) { $ArgsList += "--skip-app-env-build" }
    if ($GenerateLock) { $ArgsList += "--generate-lock" }
    if ($SkipLock) { $ArgsList += "--skip-lock" }
    if ($BuildFrozenFolder) { $ArgsList += "--build-frozen-folder" }
    if ($RebuildFrozenFolder) { $ArgsList += "--rebuild-frozen-folder" }
    if ($SkipFrozenBuild) { $ArgsList += "--skip-frozen-build" }
    if ($VerifyRuntime) { $ArgsList += "--verify-runtime" }
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
