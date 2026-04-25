param(
    [Parameter(Mandatory = $true)]
    [string]$AppId,
    [switch]$StrictApproval,
    [switch]$AllowWarnings
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

    $Python = Find-Python
    if (-not $Python) {
        throw "python or py was not found. App Studio approval requires a development Python to run."
    }

    Push-Location $Root
    try {
        $ArgsList = @($StudioMain, "approve", "--app-id", $AppId)
        if ($StrictApproval) { $ArgsList += "--strict-approval" }
        if ($AllowWarnings) { $ArgsList += "--allow-warnings" }
        & $Python @ArgsList
        $ExitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }

    if ($ExitCode -ne 0) {
        throw "ToolHub App Studio approval failed with exit code: $ExitCode"
    }
    exit 0
}
catch {
    Write-Host "ToolHub App Studio error: $($_.Exception.Message)"
    exit 1
}
