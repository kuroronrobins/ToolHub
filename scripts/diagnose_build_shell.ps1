param(
    [switch]$Json
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Invoke-DiagnosticCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [string[]]$Arguments = @()
    )

    $CommandText = @($FilePath) + @($Arguments) -join " "
    try {
        $Output = & $FilePath @Arguments 2>&1
        $ExitCode = $LASTEXITCODE
        if ($null -eq $ExitCode) {
            $ExitCode = 0
        }
        $Text = ($Output | ForEach-Object { $_.ToString() }) -join "`n"
        return [ordered]@{
            command = $CommandText
            ok = ($ExitCode -eq 0)
            exit_code = $ExitCode
            output = $Text.Trim()
            application_control_blocked = ($Text -match "Application Control|blocked|4551|ブロック")
        }
    } catch {
        $Message = $_.Exception.Message
        return [ordered]@{
            command = $CommandText
            ok = $false
            exit_code = 1
            output = $Message
            application_control_blocked = ($Message -match "Application Control|blocked|4551|ブロック")
        }
    }
}

function Get-CommandRecord {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $Command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($null -eq $Command) {
        return [ordered]@{
            name = $Name
            found = $false
            source = ""
            command_type = ""
        }
    }

    return [ordered]@{
        name = $Name
        found = $true
        source = [string]$Command.Source
        command_type = [string]$Command.CommandType
    }
}

function Find-VsDevCmd {
    $Candidates = @(
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

    $Seen = @{}
    $Records = @()
    foreach ($Candidate in $Candidates) {
        if ([string]::IsNullOrWhiteSpace($Candidate)) {
            continue
        }
        $Key = $Candidate.ToLowerInvariant()
        if ($Seen.ContainsKey($Key)) {
            continue
        }
        $Seen[$Key] = $true
        $Records += [ordered]@{
            path = $Candidate
            exists = (Test-Path -LiteralPath $Candidate -PathType Leaf)
        }
    }
    return @($Records)
}

$WhereRecords = [ordered]@{
    rustc = Invoke-DiagnosticCommand "where.exe" @("rustc")
    cargo = Invoke-DiagnosticCommand "where.exe" @("cargo")
    cl = Invoke-DiagnosticCommand "where.exe" @("cl")
    link = Invoke-DiagnosticCommand "where.exe" @("link")
}

$VersionRecords = [ordered]@{
    rustc = Invoke-DiagnosticCommand "rustc" @("--version")
    cargo = Invoke-DiagnosticCommand "cargo" @("--version")
}

$GetCommandRecords = [ordered]@{
    rustc = Get-CommandRecord "rustc"
    cargo = Get-CommandRecord "cargo"
    cl = Get-CommandRecord "cl"
    link = Get-CommandRecord "link"
}

$VsDevCmdRecords = @(Find-VsDevCmd)
$AppControlBlocked = [bool]($VersionRecords.rustc.application_control_blocked)

$Report = [ordered]@{
    root = $Root
    where = $WhereRecords
    versions = $VersionRecords
    get_command = $GetCommandRecords
    vs_dev_cmd = $VsDevCmdRecords
    app_control_blocked = $AppControlBlocked
    notes = @(
        "This script is read-only.",
        "Missing cl.exe/link.exe can usually be fixed by running through scripts/run_in_vs_dev_shell.ps1.",
        "Windows Application Control blocking rustc.exe cannot be fixed by this repository; allowlist/trusted install path or a separate release build machine is required."
    )
}

if ($Json) {
    $Report | ConvertTo-Json -Depth 8
    exit 0
}

Write-Host "== Build shell diagnosis =="
Write-Host "root: $Root"
Write-Host ""
Write-Host "-- where.exe --"
foreach ($Name in $WhereRecords.Keys) {
    $Record = $WhereRecords[$Name]
    $Status = if ($Record.ok) { "OK" } else { "NG" }
    Write-Host ("[{0}] where.exe {1}" -f $Status, $Name)
    if (-not [string]::IsNullOrWhiteSpace($Record.output)) {
        Write-Host $Record.output
    }
}

Write-Host ""
Write-Host "-- versions --"
foreach ($Name in $VersionRecords.Keys) {
    $Record = $VersionRecords[$Name]
    $Status = if ($Record.ok) { "OK" } else { "NG" }
    Write-Host ("[{0}] {1} --version" -f $Status, $Name)
    if (-not [string]::IsNullOrWhiteSpace($Record.output)) {
        Write-Host $Record.output
    }
}

Write-Host ""
Write-Host "-- Get-Command --"
foreach ($Name in $GetCommandRecords.Keys) {
    $Record = $GetCommandRecords[$Name]
    $Status = if ($Record.found) { "OK" } else { "NG" }
    Write-Host ("[{0}] {1}: {2}" -f $Status, $Name, $Record.source)
}

Write-Host ""
Write-Host "-- VsDevCmd candidates --"
foreach ($Record in $VsDevCmdRecords) {
    $Status = if ($Record.exists) { "OK" } else { "NG" }
    Write-Host ("[{0}] {1}" -f $Status, $Record.path)
}

Write-Host ""
if ($AppControlBlocked) {
    Write-Host "[WARN] rustc appears to be blocked by Windows Application Control. Use an allowlisted toolchain path, Developer PowerShell manual execution, or another release build machine."
} else {
    Write-Host "[OK] rustc is not currently reporting a Windows Application Control block in this shell."
}
if (-not $WhereRecords.cl.ok -or -not $WhereRecords.link.ok) {
    Write-Host "[WARN] cl.exe/link.exe are not visible in the current shell. Use scripts/run_in_vs_dev_shell.ps1 or Developer PowerShell for VS."
}

exit 0
