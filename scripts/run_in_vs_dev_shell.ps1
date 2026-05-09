param(
    [Parameter(Mandatory = $true)]
    [string]$Command,
    [string]$VsDevCmdPath = "",
    [ValidateSet("x86", "x64", "arm64")]
    [string]$Arch = "x64",
    [string]$WorkingDirectory = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if ([string]::IsNullOrWhiteSpace($WorkingDirectory)) {
    $WorkingDirectory = $Root
}
$WorkingDirectory = (Resolve-Path $WorkingDirectory).Path

function Find-VsDevCmd {
    param([string]$ExplicitPath)

    $Candidates = @()
    if (-not [string]::IsNullOrWhiteSpace($ExplicitPath)) {
        $Candidates += $ExplicitPath
    }
    $Candidates += @(
        "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat",
        "C:\Program Files\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat"
    )

    $VsWhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
    if (Test-Path -LiteralPath $VsWhere -PathType Leaf) {
        try {
            $FoundByVsWhere = & $VsWhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -find "Common7\Tools\VsDevCmd.bat" 2>$null
            foreach ($Path in @($FoundByVsWhere)) {
                if (-not [string]::IsNullOrWhiteSpace($Path)) {
                    $Candidates += $Path
                }
            }
        } catch {
            # Keep the fixed candidate list when vswhere cannot be executed.
        }
    }

    foreach ($Candidate in $Candidates) {
        if (-not [string]::IsNullOrWhiteSpace($Candidate) -and (Test-Path -LiteralPath $Candidate -PathType Leaf)) {
            return (Resolve-Path $Candidate).Path
        }
    }
    return $null
}

$ResolvedVsDevCmd = Find-VsDevCmd $VsDevCmdPath
if ([string]::IsNullOrWhiteSpace($ResolvedVsDevCmd)) {
    Write-Error "VsDevCmd.bat was not found. Install Visual Studio Build Tools with Desktop development with C++ or pass -VsDevCmdPath."
    exit 1
}

$TempCmd = Join-Path $env:TEMP ("toolhub_vsdev_{0}.cmd" -f ([Guid]::NewGuid().ToString("N")))
$CmdLines = @(
    "@echo off",
    "call `"$ResolvedVsDevCmd`" -no_logo -arch=$Arch",
    "if errorlevel 1 exit /b %ERRORLEVEL%",
    "cd /d `"$WorkingDirectory`"",
    "if errorlevel 1 exit /b %ERRORLEVEL%",
    $Command,
    "exit /b %ERRORLEVEL%"
)

Write-Host "VsDevCmd: $ResolvedVsDevCmd"
Write-Host "WorkingDirectory: $WorkingDirectory"
Write-Host "Command: $Command"

if ($DryRun) {
    Write-Host ""
    Write-Host "DryRun command file:"
    $CmdLines | ForEach-Object { Write-Host $_ }
    exit 0
}

try {
    Set-Content -LiteralPath $TempCmd -Value $CmdLines -Encoding ASCII
    & cmd.exe /d /c $TempCmd
    $ExitCode = $LASTEXITCODE
} finally {
    if (Test-Path -LiteralPath $TempCmd) {
        Remove-Item -LiteralPath $TempCmd -Force
    }
}

exit $ExitCode
