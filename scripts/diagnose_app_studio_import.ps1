param(
    [string]$AppId,
    [string]$Entry,
    [string]$OutputDir,
    [string]$RepoRoot,
    [switch]$NoWrite,
    [switch]$AsJson,
    [switch]$VerboseFiles
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

if ([string]::IsNullOrWhiteSpace($AppId)) {
    Write-Host "Missing required parameter: -AppId <string>"
    Write-Host "Usage: powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\diagnose_app_studio_import.ps1 -AppId <app_id> [-Entry <main.py>] [-OutputDir <ToolHub_AppStudio_Output\app_id>] [-NoWrite] [-AsJson] [-VerboseFiles]"
    exit 2
}

function Find-RepoRoot {
    param([string]$Start)
    $Current = [System.IO.Path]::GetFullPath($Start)
    while ($Current) {
        if ((Test-Path -LiteralPath (Join-Path $Current "AGENTS.md") -PathType Leaf) -and
            (Test-Path -LiteralPath (Join-Path $Current "scripts") -PathType Container)) {
            return $Current
        }
        $Parent = Split-Path -Parent $Current
        if ([string]::IsNullOrWhiteSpace($Parent) -or $Parent -eq $Current) {
            break
        }
        $Current = $Parent
    }
    return $null
}

function Resolve-RepoRoot {
    if (-not [string]::IsNullOrWhiteSpace($RepoRoot)) {
        return [System.IO.Path]::GetFullPath($RepoRoot)
    }
    $ScriptDir = $PSScriptRoot
    if ([string]::IsNullOrWhiteSpace($ScriptDir)) {
        $ScriptDir = (Get-Location).Path
    }
    $FromScript = Find-RepoRoot -Start $ScriptDir
    if ($FromScript) {
        return $FromScript
    }
    $FromCwd = Find-RepoRoot -Start (Get-Location).Path
    if ($FromCwd) {
        return $FromCwd
    }
    return [System.IO.Path]::GetFullPath((Get-Location).Path)
}

$Root = Resolve-RepoRoot
$LogDir = Join-Path (Join-Path (Join-Path $Root "data") "logs") "app_studio"
$AppsDir = Join-Path $Root "apps"
$AppDir = Join-Path $AppsDir $AppId
$AppYamlPath = Join-Path $AppDir "app.yaml"
$AppBinRoot = Join-Path (Join-Path $AppDir "bin") $AppId
$AppExePath = Join-Path $AppBinRoot ($AppId + ".exe")

$Classifications = New-Object System.Collections.ArrayList
$Actions = New-Object System.Collections.ArrayList
$Evidence = New-Object System.Collections.ArrayList
$ParseErrors = New-Object System.Collections.ArrayList

function Add-Classification {
    param([string]$Name)
    if (-not [string]::IsNullOrWhiteSpace($Name) -and -not $script:Classifications.Contains($Name)) {
        [void]$script:Classifications.Add($Name)
    }
}

function Add-Action {
    param([string]$Text)
    if (-not [string]::IsNullOrWhiteSpace($Text) -and -not $script:Actions.Contains($Text)) {
        [void]$script:Actions.Add($Text)
    }
}

function Get-Prop {
    param([object]$Object, [string]$Name)
    if ($null -eq $Object) {
        return $null
    }
    $Prop = $Object.PSObject.Properties[$Name]
    if ($Prop) {
        return $Prop.Value
    }
    return $null
}

function Get-ResultOutputDir {
    param([object]$Data)
    if ($null -eq $Data) {
        return ""
    }
    $Value = [string](Get-Prop -Object $Data -Name "output_dir")
    if (-not [string]::IsNullOrWhiteSpace($Value)) {
        return $Value
    }
    $Evidence = Get-Prop -Object $Data -Name "evidence"
    $EvidenceOutput = [string](Get-Prop -Object $Evidence -Name "output_dir")
    if (-not [string]::IsNullOrWhiteSpace($EvidenceOutput)) {
        return $EvidenceOutput
    }
    return ""
}

function Test-SamePathText {
    param([string]$Left, [string]$Right)
    if ([string]::IsNullOrWhiteSpace($Left) -or [string]::IsNullOrWhiteSpace($Right)) {
        return $false
    }
    $LeftFull = Resolve-FullPathSafe -Value $Left
    $RightFull = Resolve-FullPathSafe -Value $Right
    if ([string]::IsNullOrWhiteSpace($LeftFull) -or [string]::IsNullOrWhiteSpace($RightFull)) {
        return $false
    }
    return [string]::Equals($LeftFull, $RightFull, [System.StringComparison]::OrdinalIgnoreCase)
}

function Read-JsonFile {
    param([string]$Path)
    $Result = [ordered]@{
        status = "missing"
        path = $Path
        data = $null
        error = $null
        last_write_time = $null
    }
    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return [pscustomobject]$Result
    }
    try {
        $Item = Get-Item -LiteralPath $Path
        $Text = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
        $Result.status = "ok"
        $Result.data = $Text | ConvertFrom-Json
        $Result.last_write_time = $Item.LastWriteTime
    } catch {
        $Result.status = "parse_error"
        $Result.error = $_.Exception.Message
        [void]$script:ParseErrors.Add("$Path : $($Result.error)")
    }
    return [pscustomobject]$Result
}

function Read-TextFile {
    param([string]$Path)
    $Result = [ordered]@{
        status = "missing"
        path = $Path
        text = ""
        error = $null
        last_write_time = $null
    }
    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return [pscustomobject]$Result
    }
    try {
        $Item = Get-Item -LiteralPath $Path
        $Result.status = "ok"
        $Result.text = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
        $Result.last_write_time = $Item.LastWriteTime
    } catch {
        $Result.status = "read_error"
        $Result.error = $_.Exception.Message
        [void]$script:ParseErrors.Add("$Path : $($Result.error)")
    }
    return [pscustomobject]$Result
}

function Get-YamlScalar {
    param([string]$Path, [string]$Key)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $null
    }
    try {
        foreach ($Line in (Get-Content -LiteralPath $Path -Encoding UTF8)) {
            if ($Line -match ("^\s*" + [regex]::Escape($Key) + "\s*:\s*(.+?)\s*$")) {
                return $Matches[1].Trim().Trim("'").Trim('"')
            }
        }
    } catch {
        return $null
    }
    return $null
}

function Join-RelativePath {
    param([string]$Base, [string]$Relative)
    $Current = $Base
    if ([string]::IsNullOrWhiteSpace($Relative) -or $Relative -eq ".") {
        return $Current
    }
    foreach ($Part in ($Relative -split "[\\/]+")) {
        if (-not [string]::IsNullOrWhiteSpace($Part) -and $Part -ne ".") {
            $Current = Join-Path $Current $Part
        }
    }
    return $Current
}

function Get-AddDataDestination {
    param([string]$BinRoot, [string]$Destination, [string]$Source)
    $Leaf = Split-Path -Leaf $Source
    $DestRoot = Join-RelativePath -Base $BinRoot -Relative $Destination
    return Join-Path $DestRoot $Leaf
}

function Normalize-RelativeText {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value) -or $Value -eq ".") {
        return ""
    }
    $Normalized = ($Value -replace "\\", "/").Trim("/")
    while ($Normalized -match "//") {
        $Normalized = $Normalized -replace "//", "/"
    }
    if ($Normalized -eq ".") {
        return ""
    }
    return $Normalized
}

function Join-RelativeText {
    param([string]$Left, [string]$Right)
    $LeftNorm = Normalize-RelativeText -Value $Left
    $RightNorm = Normalize-RelativeText -Value $Right
    if ([string]::IsNullOrWhiteSpace($LeftNorm)) {
        return $RightNorm
    }
    if ([string]::IsNullOrWhiteSpace($RightNorm)) {
        return $LeftNorm
    }
    return ($LeftNorm + "/" + $RightNorm)
}

function Get-RelativeSuffixText {
    param([string]$Child, [string]$Base)
    $ChildNorm = Normalize-RelativeText -Value $Child
    $BaseNorm = Normalize-RelativeText -Value $Base
    if ([string]::IsNullOrWhiteSpace($BaseNorm)) {
        return $ChildNorm
    }
    if ($ChildNorm -eq $BaseNorm) {
        return ""
    }
    if ($ChildNorm.StartsWith($BaseNorm + "/")) {
        return $ChildNorm.Substring($BaseNorm.Length + 1)
    }
    return $null
}

function Get-ExistingPath {
    param([object[]]$Paths)
    foreach ($Candidate in @($Paths)) {
        if (-not [string]::IsNullOrWhiteSpace([string]$Candidate) -and (Test-Path -LiteralPath ([string]$Candidate))) {
            return [string]$Candidate
        }
    }
    return $null
}

function Get-ExpectedAddDataRelatives {
    param(
        [string]$Source,
        [string]$Destination,
        [string]$SourcePath,
        [object[]]$RequiredFiles
    )
    $Relatives = @()
    $SourceNorm = Normalize-RelativeText -Value $Source
    $DestinationNorm = Normalize-RelativeText -Value $Destination
    $SourceIsDirectory = $false
    if (-not [string]::IsNullOrWhiteSpace($SourcePath) -and (Test-Path -LiteralPath $SourcePath -PathType Container)) {
        $SourceIsDirectory = $true
    }

    foreach ($RequiredRaw in @($RequiredFiles)) {
        $RequiredNorm = Normalize-RelativeText -Value ([string]$RequiredRaw)
        if ([string]::IsNullOrWhiteSpace($RequiredNorm)) {
            continue
        }
        $Suffix = Get-RelativeSuffixText -Child $RequiredNorm -Base $SourceNorm
        if ($null -eq $Suffix) {
            continue
        }
        if ($SourceIsDirectory) {
            $Relatives += (Join-RelativeText -Left $DestinationNorm -Right $Suffix)
        } else {
            $Relatives += (Join-RelativeText -Left $DestinationNorm -Right (Split-Path -Leaf $SourceNorm))
        }
    }

    if ($Relatives.Count -eq 0) {
        if ($SourceIsDirectory) {
            try {
                $SourceRootFull = [System.IO.Path]::GetFullPath($SourcePath).TrimEnd([char[]]"\/")
                $Files = Get-ChildItem -LiteralPath $SourcePath -Recurse -File -ErrorAction SilentlyContinue | Select-Object -First 200
                foreach ($File in @($Files)) {
                    $FileFull = [System.IO.Path]::GetFullPath($File.FullName)
                    if ($FileFull.StartsWith($SourceRootFull, [System.StringComparison]::OrdinalIgnoreCase)) {
                        $Inside = $FileFull.Substring($SourceRootFull.Length).TrimStart([char[]]"\/")
                        $Relatives += (Join-RelativeText -Left $DestinationNorm -Right $Inside)
                    }
                }
            } catch {
                $Relatives += $DestinationNorm
            }
            if ($Relatives.Count -eq 0) {
                $Relatives += $DestinationNorm
            }
        } else {
            $Relatives += (Join-RelativeText -Left $DestinationNorm -Right (Split-Path -Leaf $SourceNorm))
        }
    }

    return @($Relatives | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique)
}

function Get-FileEvidence {
    param([string]$Label, [string]$Path)
    $Exists = $false
    $Kind = "missing"
    $Size = $null
    $LastWrite = $null
    if (-not [string]::IsNullOrWhiteSpace($Path) -and (Test-Path -LiteralPath $Path)) {
        $Exists = $true
        $Item = Get-Item -LiteralPath $Path
        if ($Item.PSIsContainer) {
            $Kind = "directory"
        } else {
            $Kind = "file"
            $Size = $Item.Length
        }
        $LastWrite = $Item.LastWriteTime
    }
    $Obj = [pscustomobject][ordered]@{
        label = $Label
        path = $Path
        exists = $Exists
        kind = $Kind
        size = $Size
        last_write_time = $LastWrite
    }
    [void]$script:Evidence.Add($Obj)
    return $Obj
}

function Format-Time {
    param([object]$Value)
    if ($null -eq $Value) {
        return "missing"
    }
    try {
        return ([datetime]$Value).ToString("yyyy-MM-dd HH:mm:ss")
    } catch {
        return [string]$Value
    }
}

function Contains-Text {
    param([string]$Text, [string]$Needle)
    if ($null -eq $Text -or $null -eq $Needle) {
        return $false
    }
    return $Text.IndexOf($Needle, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
}

function Get-ApprovalRecordScalar {
    param([string]$Text, [string]$Key)
    if ([string]::IsNullOrWhiteSpace($Text)) {
        return "missing"
    }
    foreach ($Line in ($Text -split "`r?`n")) {
        if ($Line -match ("^\s*-\s*" + [regex]::Escape($Key) + "\s*:\s*(.*)$")) {
            return $Matches[1].Trim().Trim([char]0x60)
        }
    }
    return "missing"
}

function Get-ApprovalRecordFailures {
    param([string]$Text)
    $Failures = @()
    $InSection = $false
    foreach ($Line in ($Text -split "`r?`n")) {
        $Trim = $Line.Trim()
        if ($Trim.StartsWith("## ")) {
            $InSection = ($Trim -eq "## Failures")
            continue
        }
        if ($InSection -and $Trim.StartsWith("- ")) {
            $Failures += $Trim.Substring(2).Trim()
        }
    }
    return $Failures
}

function Select-NewestExistingFile {
    param([string[]]$Paths)
    $Items = @()
    foreach ($Path in $Paths) {
        if (-not [string]::IsNullOrWhiteSpace($Path) -and (Test-Path -LiteralPath $Path -PathType Leaf)) {
            $Items += Get-Item -LiteralPath $Path
        }
    }
    if ($Items.Count -eq 0) {
        return $null
    }
    return ($Items | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
}

function Find-OutputDirFromLogs {
    param([string]$Directory, [string]$Id)
    if (-not (Test-Path -LiteralPath $Directory -PathType Container)) {
        return $null
    }
    $Files = Get-ChildItem -LiteralPath $Directory -Filter ($Id + "_*.md") -File -ErrorAction SilentlyContinue
    foreach ($File in $Files) {
        try {
            $Text = Get-Content -LiteralPath $File.FullName -Raw -Encoding UTF8
            if ($Text -match '(?im)output_dir[`"''\s:=]+(.+)$') {
                return $Matches[1].Trim().Trim('"').Trim("'").Trim('`')
            }
            if ($Text -match '(?im)^\s*-\s*output\s*:\s*`?(.+?)`?\s*$') {
                return $Matches[1].Trim().Trim('"').Trim('`')
            }
        } catch {
        }
    }
    return $null
}

function Resolve-OutputDir {
    if (-not [string]::IsNullOrWhiteSpace($OutputDir)) {
        return Resolve-FullPathSafe -Value $OutputDir
    }
    if (-not [string]::IsNullOrWhiteSpace($Entry)) {
        $EntryFull = Resolve-FullPathSafe -Value $Entry
        if ([string]::IsNullOrWhiteSpace($EntryFull)) {
            return $null
        }
        $EntryParent = Split-Path -Parent $EntryFull
        return (Join-Path (Join-Path $EntryParent "ToolHub_AppStudio_Output") $AppId)
    }
    $Mirror = Get-YamlScalar -Path $AppYamlPath -Key "output_mirror"
    if (-not [string]::IsNullOrWhiteSpace($Mirror)) {
        return Resolve-FullPathSafe -Value $Mirror
    }
    $ExecutionCandidate = Join-Path $LogDir ($AppId + "_execution_test_result.json")
    if (Test-Path -LiteralPath $ExecutionCandidate -PathType Leaf) {
        try {
            $ExecutionData = Get-Content -LiteralPath $ExecutionCandidate -Raw -Encoding UTF8 | ConvertFrom-Json
            $Evidence = Get-Prop -Object $ExecutionData -Name "evidence"
            $EvidenceOutput = [string](Get-Prop -Object $Evidence -Name "output_dir")
            if (-not [string]::IsNullOrWhiteSpace($EvidenceOutput)) {
                return Resolve-FullPathSafe -Value $EvidenceOutput
            }
        } catch {
        }
    }
    $FromLogs = Find-OutputDirFromLogs -Directory $LogDir -Id $AppId
    if (-not [string]::IsNullOrWhiteSpace($FromLogs)) {
        return Resolve-FullPathSafe -Value $FromLogs
    }
    return $null
}

function Resolve-FullPathSafe {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $null
    }
    $Clean = $Value.Trim().Trim('"').Trim("'").Trim('`')
    if ([string]::IsNullOrWhiteSpace($Clean)) {
        return $null
    }
    if ($Clean.IndexOfAny([System.IO.Path]::GetInvalidPathChars()) -ge 0) {
        return $null
    }
    try {
        return [System.IO.Path]::GetFullPath($Clean)
    } catch {
        return $null
    }
}

$ResolvedOutputDir = Resolve-OutputDir
$FinalAppDir = $null
$OutputBinRoot = $null
$OutputExePath = $null
if (-not [string]::IsNullOrWhiteSpace($ResolvedOutputDir)) {
    $FinalAppDir = Join-Path $ResolvedOutputDir "final_app"
    $OutputBinRoot = Join-Path (Join-Path $FinalAppDir "bin") $AppId
    $OutputExePath = Join-Path $OutputBinRoot ($AppId + ".exe")
}

$ExecutionJsonPath = Join-Path $LogDir ($AppId + "_execution_test_result.json")
$ExecutionReportPath = Join-Path $LogDir ($AppId + "_execution_test_report.md")
$RuntimeJsonPath = Join-Path $LogDir ($AppId + "_runtime_check_result.json")
$RuntimeReportPath = Join-Path $LogDir ($AppId + "_runtime_check_report.md")
$FrozenLogReportPath = Join-Path $LogDir ($AppId + "_frozen_folder_build_report.md")
$AppEnvLogReportPath = Join-Path $LogDir ($AppId + "_app_env_build_report.md")
$LockLogReportPath = Join-Path $LogDir ($AppId + "_lock_generation_report.md")
$ApprovalRecordPath = Join-Path $LogDir ($AppId + "_approval_record.md")

$OutputExecutionJsonPath = if ($ResolvedOutputDir) { Join-Path $ResolvedOutputDir "execution_test_result.json" } else { $null }
$OutputRuntimeJsonPath = if ($ResolvedOutputDir) { Join-Path $ResolvedOutputDir "runtime_check_result.json" } else { $null }
$OutputImportPlanPath = if ($ResolvedOutputDir) { Join-Path $ResolvedOutputDir "import_plan.json" } else { $null }
$OutputSecretReportPath = if ($ResolvedOutputDir) { Join-Path $ResolvedOutputDir "secret_scan_report.md" } else { $null }
$OutputSecretJsonPath = if ($ResolvedOutputDir) { Join-Path $ResolvedOutputDir "secret_scan_report.json" } else { $null }
$OutputFileInventoryPath = if ($ResolvedOutputDir) { Join-Path $ResolvedOutputDir "file_inventory.json" } else { $null }
$OutputFrozenReportPath = if ($ResolvedOutputDir) { Join-Path $ResolvedOutputDir "frozen_folder_build_report.md" } else { $null }
$OutputAppEnvReportPath = if ($ResolvedOutputDir) { Join-Path $ResolvedOutputDir "app_env_build_report.md" } else { $null }
$OutputLockReportPath = if ($ResolvedOutputDir) { Join-Path $ResolvedOutputDir "lock_generation_report.md" } else { $null }
$OutputBuildProfilePath = if ($ResolvedOutputDir) { Join-Path $ResolvedOutputDir "build_profile.json" } else { $null }
$OutputInventoryPath = if ($ResolvedOutputDir) { Join-Path $ResolvedOutputDir "file_inventory.json" } else { $null }
$FinalAppBuildProfilePath = if ($FinalAppDir) { Join-Path $FinalAppDir "build_profile.json" } else { $null }
$FinalAppInventoryPath = if ($FinalAppDir) { Join-Path $FinalAppDir "file_inventory.json" } else { $null }
$AppBuildProfilePath = Join-Path $AppDir "build_profile.json"

$RepoFiles = @(
    @("repo app.yaml", $AppYamlPath),
    @("repo README.md", (Join-Path $AppDir "README.md")),
    @("repo requirements.txt", (Join-Path $AppDir "requirements.txt")),
    @("repo requirements.lock", (Join-Path $AppDir "requirements.lock")),
    @("repo build_profile.json", $AppBuildProfilePath),
    @("repo exe_readiness.json", (Join-Path $AppDir "exe_readiness.json")),
    @("repo BUILD_REQUIRED.txt", (Join-Path (Join-Path $AppDir "bin") "BUILD_REQUIRED.txt")),
    @("repo exe", $AppExePath),
    @("repo bin folder", $AppBinRoot),
    @("release app_manifest.json", (Join-Path (Join-Path $Root "release") "app_manifest.json"))
)
foreach ($Pair in $RepoFiles) {
    Get-FileEvidence -Label $Pair[0] -Path $Pair[1] | Out-Null
}

$LogFiles = @(
    @("log execution_test_result.json", $ExecutionJsonPath),
    @("log execution_test_report.md", $ExecutionReportPath),
    @("log runtime_check_result.json", $RuntimeJsonPath),
    @("log runtime_check_report.md", $RuntimeReportPath),
    @("log frozen_folder_build_report.md", $FrozenLogReportPath),
    @("log app_env_build_report.md", $AppEnvLogReportPath),
    @("log lock_generation_report.md", $LockLogReportPath),
    @("log approval_record.md", $ApprovalRecordPath)
)
foreach ($Pair in $LogFiles) {
    Get-FileEvidence -Label $Pair[0] -Path $Pair[1] | Out-Null
}

if ($ResolvedOutputDir) {
    $OutputFiles = @(
        @("output import_plan.json", $OutputImportPlanPath),
        @("output secret_scan_report.md", $OutputSecretReportPath),
        @("output secret_scan_report.json", $OutputSecretJsonPath),
        @("output file_inventory.json", $OutputFileInventoryPath),
        @("output build_profile.json", $OutputBuildProfilePath),
        @("output exe_readiness.json", (Join-Path $ResolvedOutputDir "exe_readiness.json")),
        @("output execution_test_result.json", $OutputExecutionJsonPath),
        @("output execution_test_report.md", (Join-Path $ResolvedOutputDir "execution_test_report.md")),
        @("output runtime_check_result.json", $OutputRuntimeJsonPath),
        @("output runtime_check_report.md", (Join-Path $ResolvedOutputDir "runtime_check_report.md")),
        @("output frozen_folder_build_report.md", $OutputFrozenReportPath),
        @("output app_env_build_report.md", $OutputAppEnvReportPath),
        @("output lock_generation_report.md", $OutputLockReportPath),
        @("output final_app app.yaml", (Join-Path $FinalAppDir "app.yaml")),
        @("output final_app build_profile.json", $FinalAppBuildProfilePath),
        @("output final_app exe_readiness.json", (Join-Path $FinalAppDir "exe_readiness.json")),
        @("output final_app BUILD_REQUIRED.txt", (Join-Path (Join-Path $FinalAppDir "bin") "BUILD_REQUIRED.txt")),
        @("output final_app exe", $OutputExePath),
        @("output final_app bin folder", $OutputBinRoot)
    )
    foreach ($Pair in $OutputFiles) {
        Get-FileEvidence -Label $Pair[0] -Path $Pair[1] | Out-Null
    }
}

$ExecutionState = Read-JsonFile -Path $ExecutionJsonPath
$OutputExecutionState = Read-JsonFile -Path $OutputExecutionJsonPath
$RuntimeState = Read-JsonFile -Path $RuntimeJsonPath
$ImportPlanState = Read-JsonFile -Path $OutputImportPlanPath
$ApprovalRecordState = Read-TextFile -Path $ApprovalRecordPath
$SecretJsonState = Read-JsonFile -Path $OutputSecretJsonPath
$SecretTextState = Read-TextFile -Path $OutputSecretReportPath
$FileInventoryState = Read-JsonFile -Path $OutputFileInventoryPath
$TracePolicyId = if ($ImportPlanState.status -eq "ok") { [string](Get-Prop -Object $ImportPlanState.data -Name "app_studio_policy_id") } else { "" }
$TraceBuildEnvPython = if ($ImportPlanState.status -eq "ok") { [string](Get-Prop -Object $ImportPlanState.data -Name "build_env_python") } else { "" }
$TraceProbePython = if ($ImportPlanState.status -eq "ok") { [string](Get-Prop -Object $ImportPlanState.data -Name "pyinstaller_probe_python") } else { "" }
$TraceBuildPython = if ($ImportPlanState.status -eq "ok") { [string](Get-Prop -Object $ImportPlanState.data -Name "pyinstaller_build_python") } else { "" }
$ManifestPath = Join-Path (Join-Path $Root "release") "app_manifest.json"
$ManifestState = Read-JsonFile -Path $ManifestPath

$ApprovalAllowed = "missing"
$OverallStatus = "missing"
$ExecutionResultAppId = ""
$ExecutionResultOutputDir = ""
$ExecutionBlockingWarningsCount = 0
$FailChecks = @()
$WarnChecks = @()
if ($ExecutionState.status -eq "ok") {
    $ExecutionResultAppId = [string](Get-Prop -Object $ExecutionState.data -Name "app_id")
    $ExecutionResultOutputDir = Get-ResultOutputDir -Data $ExecutionState.data
    $ApprovalRaw = Get-Prop -Object $ExecutionState.data -Name "approval_allowed"
    if ($null -ne $ApprovalRaw) {
        $ApprovalAllowed = [string]$ApprovalRaw
    }
    $OverallRaw = Get-Prop -Object $ExecutionState.data -Name "overall_status"
    if ($null -ne $OverallRaw) {
        $OverallStatus = [string]$OverallRaw
    }
    $BlockingRaw = Get-Prop -Object $ExecutionState.data -Name "approval_blocking_warnings_count"
    if ($null -ne $BlockingRaw) {
        $ExecutionBlockingWarningsCount = [int]($BlockingRaw -as [int])
    }
    foreach ($CheckItem in @((Get-Prop -Object $ExecutionState.data -Name "checks"))) {
        $Status = [string](Get-Prop -Object $CheckItem -Name "status")
        if ($Status -eq "fail") {
            $FailChecks += $CheckItem
        } elseif ($Status -eq "warn") {
            $WarnChecks += $CheckItem
        }
    }
} elseif ($ExecutionState.status -eq "parse_error") {
    $ApprovalAllowed = "parse_error"
    $OverallStatus = "parse_error"
}

$RuntimeOverallStatus = "missing"
$RuntimeResultAppId = ""
$RuntimeResultOutputDir = ""
$RuntimeBlockingWarningsCount = 0
$RuntimeFailChecks = @()
if ($RuntimeState.status -eq "ok") {
    $RuntimeResultAppId = [string](Get-Prop -Object $RuntimeState.data -Name "app_id")
    $RuntimeResultOutputDir = Get-ResultOutputDir -Data $RuntimeState.data
    $RuntimeOverallRaw = Get-Prop -Object $RuntimeState.data -Name "overall_status"
    if ($null -ne $RuntimeOverallRaw) {
        $RuntimeOverallStatus = [string]$RuntimeOverallRaw
    }
    $RuntimeBlockingRaw = Get-Prop -Object $RuntimeState.data -Name "approval_blocking_warnings_count"
    if ($null -ne $RuntimeBlockingRaw) {
        $RuntimeBlockingWarningsCount = [int]($RuntimeBlockingRaw -as [int])
    }
    foreach ($CheckItem in @((Get-Prop -Object $RuntimeState.data -Name "checks"))) {
        $Status = [string](Get-Prop -Object $CheckItem -Name "status")
        if ($Status -eq "fail") {
            $RuntimeFailChecks += $CheckItem
        }
    }
} elseif ($RuntimeState.status -eq "parse_error") {
    $RuntimeOverallStatus = "parse_error"
}

if (-not [string]::IsNullOrWhiteSpace($ExecutionResultAppId) -and $ExecutionResultAppId -ne $AppId) {
    Add-Classification "execution_result_wrong_app"
    Add-Action "execution_test_result.json belongs to a different app_id. Rerun Apply for this app and verify result app_id matches before approving."
}
if (-not [string]::IsNullOrWhiteSpace($ResolvedOutputDir) -and -not [string]::IsNullOrWhiteSpace($ExecutionResultOutputDir) -and -not (Test-SamePathText -Left $ResolvedOutputDir -Right $ExecutionResultOutputDir)) {
    Add-Classification "execution_result_output_dir_mismatch"
    Add-Action "execution_test_result.json points at a different output_dir. Refresh the App Studio result or rerun Apply for the current output mirror."
}
if ($OverallStatus -eq "fail") {
    Add-Classification "execution_result_fail"
    Add-Action "execution_test_result.json has overall_status=fail. Fix the fail checks and rerun Apply before approving."
}
if ($ExecutionBlockingWarningsCount -gt 0) {
    Add-Classification "execution_approval_blocking_warning"
    Add-Action "execution_test_result.json has approval-blocking warnings. Resolve them, rerun Apply, and retry Approve."
}
if (-not [string]::IsNullOrWhiteSpace($RuntimeResultAppId) -and $RuntimeResultAppId -ne $AppId) {
    Add-Classification "runtime_result_wrong_app"
    Add-Action "runtime_check_result.json belongs to a different app_id. Rerun Apply for this app and verify runtime result app_id matches before approving."
}
if (-not [string]::IsNullOrWhiteSpace($ResolvedOutputDir) -and -not [string]::IsNullOrWhiteSpace($RuntimeResultOutputDir) -and -not (Test-SamePathText -Left $ResolvedOutputDir -Right $RuntimeResultOutputDir)) {
    Add-Classification "runtime_result_output_dir_mismatch"
    Add-Action "runtime_check_result.json points at a different output_dir. Rerun Apply so runtime and execution results come from the same output mirror."
}
if ($RuntimeOverallStatus -eq "fail" -or $RuntimeFailChecks.Count -gt 0) {
    Add-Classification "runtime_result_fail"
    Add-Action "runtime_check_result.json blocks approval. Fix the distribution check failure and rerun Apply before approving."
}
if ($RuntimeBlockingWarningsCount -gt 0) {
    Add-Classification "runtime_approval_blocking_warning"
    Add-Action "runtime_check_result.json has approval-blocking warnings. Resolve the runtime distribution risk and rerun Apply before approving."
}

if ($ApprovalAllowed -eq "True" -or $ApprovalAllowed -eq "true") {
    Add-Classification "approval_ready"
} elseif ($ApprovalAllowed -eq "False" -or $ApprovalAllowed -eq "false") {
    Add-Classification "approval_block_only"
    Add-Action "Approve is blocked by execution_test_result.json. Fix or regenerate the Apply-side fail checks before approving."
}

$SecretBlockingCount = 0
$SecretWarningCount = 0
$SecretManualCount = 0
$SecretAiBlocked = $false
$SecretApplyBlocked = $false
$SecretTopBlocking = @()
if ($ImportPlanState.status -eq "ok") {
    $SecretBlockingCount = [int]((Get-Prop -Object $ImportPlanState.data -Name "blocking_secret_findings_count") -as [int])
    $SecretWarningCount = [int]((Get-Prop -Object $ImportPlanState.data -Name "warning_secret_findings_count") -as [int])
    $SecretManualCount = [int]((Get-Prop -Object $ImportPlanState.data -Name "manual_check_secret_findings_count") -as [int])
    $SecretAiBlockedRaw = Get-Prop -Object $ImportPlanState.data -Name "ai_blocked_by_secret_scan"
    $SecretApplyBlockedRaw = Get-Prop -Object $ImportPlanState.data -Name "apply_blocked_by_secret_scan"
    $SecretAiBlocked = ($SecretAiBlockedRaw -eq $true)
    $SecretApplyBlocked = ($SecretApplyBlockedRaw -eq $true)
    foreach ($Item in @((Get-Prop -Object $ImportPlanState.data -Name "blocking_secret_findings"))) {
        if ($null -ne $Item) {
            $SecretTopBlocking += [string]$Item
        }
    }
}
if ($SecretJsonState.status -eq "ok") {
    $Summary = Get-Prop -Object $SecretJsonState.data -Name "summary"
    if ($Summary) {
        $SecretBlockingCount = [int]((Get-Prop -Object $Summary -Name "blocking_findings") -as [int])
        $SecretWarningCount = [int]((Get-Prop -Object $Summary -Name "warning_findings") -as [int])
        $SecretManualCount = [int]((Get-Prop -Object $Summary -Name "manual_check_findings") -as [int])
    }
}
$SecretFailChecks = @($FailChecks | Where-Object {
    (Contains-Text -Text ([string](Get-Prop -Object $_ -Name "name")) -Needle "secret") -or
    (Contains-Text -Text ([string](Get-Prop -Object $_ -Name "detail")) -Needle "secret")
})
if ($SecretApplyBlocked -or $SecretFailChecks.Count -gt 0) {
    Add-Classification "secret_scan_blocked_apply"
    Add-Action "Open secret_scan_report.md and remove or reclassify only the blocking findings before rerunning Apply."
}
if ($SecretBlockingCount -gt 0) {
    Add-Classification "secret_scan_packaged_secret_risk"
    Add-Action "Blocking secret findings affect packaged files or cannot be proven excluded; remove real secrets or adjust file inventory/add_data safely."
}
if ($SecretAiBlocked -and -not $SecretApplyBlocked) {
    Add-Classification "secret_scan_ai_only_block"
    Add-Action "AI generation can stay in fallback mode while Apply proceeds if distribution checks pass."
}
if ($SecretTextState.status -eq "ok") {
    $SecretText = $SecretTextState.text
    if ((Contains-Text -Text $SecretText -Needle "OPENAI_API_KEY") -or
        (Contains-Text -Text $SecretText -Needle "placeholder") -or
        (Contains-Text -Text $SecretText -Needle "false positive")) {
        if ($SecretApplyBlocked -or $SecretFailChecks.Count -gt 0) {
            Add-Classification "secret_scan_overblocking_suspected"
            Add-Action "Check whether blocking findings are documentation-only environment variable names or placeholders; current scanner should classify those as warnings/manual checks."
        }
    }
}

$FrozenReportPath = Select-NewestExistingFile -Paths @($OutputFrozenReportPath, $FrozenLogReportPath)
$FrozenTextState = Read-TextFile -Path $FrozenReportPath
$FrozenStatus = "unknown"
if ($FrozenTextState.status -eq "ok") {
    if ($FrozenTextState.text -match '(?im)^\s*-\s*status\s*:\s*`?(PASS|FAIL)`?') {
        $FrozenStatus = $Matches[1].ToUpperInvariant()
    }
}
$FrozenHints = @()
foreach ($Needle in @(
    "PyInstaller --onedir build failed",
    "PyInstaller is not available",
    "No module named PyInstaller",
    "Expected frozen executable was not found",
    "Refusing to run PyInstaller with --onefile",
    "BUILD_REQUIRED",
    "obsolete pathlib",
    "PYTHONNOUSERSITE"
)) {
    if ($FrozenTextState.status -eq "ok" -and (Contains-Text -Text $FrozenTextState.text -Needle $Needle)) {
        $FrozenHints += $Needle
    }
}
$PyInstallerCommandLines = @()
$PyInstallerContentsDirectoryDot = $false
if ($FrozenTextState.status -eq "ok") {
    $PyInstallerCommandLines = @($FrozenTextState.text -split "`r?`n" | Where-Object { $_ -match "PyInstaller|--onedir|--contents-directory" })
    foreach ($Line in $PyInstallerCommandLines) {
        $CleanLine = ([string]$Line) -replace "[`"']", ""
        if ($CleanLine -match "--contents-directory\s+\.") {
            $PyInstallerContentsDirectoryDot = $true
        }
    }
}

$OutputExeExists = $false
$AppsExeExists = $false
if ($OutputExePath -and (Test-Path -LiteralPath $OutputExePath -PathType Leaf)) {
    $OutputExeExists = $true
}
if (Test-Path -LiteralPath $AppExePath -PathType Leaf) {
    $AppsExeExists = $true
}

if ($FrozenStatus -eq "FAIL" -or (-not $OutputExeExists -and -not $AppsExeExists)) {
    Add-Classification "frozen_build_failed"
    Add-Action "Review frozen_folder_build_report.md and the PyInstaller stderr section."
}
if ($OutputExeExists -and -not $AppsExeExists) {
    Add-Classification "registration_copy_failed_or_not_reached"
    Add-Action "Check whether Apply reached apply_registration and whether apps/<app_id> was copied after the frozen build."
}

$OutputBuildRequired = if ($FinalAppDir) { Join-Path (Join-Path $FinalAppDir "bin") "BUILD_REQUIRED.txt" } else { $null }
$AppsBuildRequired = Join-Path (Join-Path $AppDir "bin") "BUILD_REQUIRED.txt"
$OutputBuildRequiredExists = $OutputBuildRequired -and (Test-Path -LiteralPath $OutputBuildRequired -PathType Leaf)
$AppsBuildRequiredExists = Test-Path -LiteralPath $AppsBuildRequired -PathType Leaf
$BuildRequiredInterpretation = "not present"
if (($OutputBuildRequiredExists -or $AppsBuildRequiredExists) -and (-not $OutputExeExists -and -not $AppsExeExists)) {
    $BuildRequiredInterpretation = "BUILD_REQUIRED.txt remains and no exe was found; frozen build did not complete."
    Add-Classification "build_not_run_or_incomplete"
    Add-Action "Rerun Apply with the current code and inspect the frozen build report."
} elseif (($OutputBuildRequiredExists -or $AppsBuildRequiredExists) -and ($OutputExeExists -or $AppsExeExists)) {
    $BuildRequiredInterpretation = "BUILD_REQUIRED.txt remains while an exe exists; exporter residue or copy-order mismatch is possible."
} elseif (-not $OutputBuildRequiredExists -and -not $AppsBuildRequiredExists) {
    $BuildRequiredInterpretation = "BUILD_REQUIRED.txt was not found."
}

$BuildProfilePath = Select-NewestExistingFile -Paths @($OutputBuildProfilePath, $FinalAppBuildProfilePath, $AppBuildProfilePath)
$BuildProfileState = Read-JsonFile -Path $BuildProfilePath
$AddData = @()
$RequiredFiles = @()
if ($BuildProfileState.status -eq "ok") {
    $AddData = @((Get-Prop -Object $BuildProfileState.data -Name "add_data"))
    $RequiredFiles = @((Get-Prop -Object $BuildProfileState.data -Name "required_files"))
}
$AddDataSources = @()
$ExpectedPackagedRelatives = @()
$MissingPackagedData = @()
$PlacementMismatches = @()
$InternalOnlyData = @()
$ImportantFiles = @()

$SourceRoot = $null
if ($ImportPlanState.status -eq "ok") {
    $SourceRoot = [string](Get-Prop -Object $ImportPlanState.data -Name "source_root")
}
if ([string]::IsNullOrWhiteSpace($SourceRoot) -and -not [string]::IsNullOrWhiteSpace($Entry)) {
    $SourceRoot = Split-Path -Parent ([System.IO.Path]::GetFullPath($Entry))
}

foreach ($Item in $AddData) {
    if ($null -eq $Item) {
        continue
    }
    $Source = [string](Get-Prop -Object $Item -Name "source")
    $Destination = [string](Get-Prop -Object $Item -Name "destination")
    if ([string]::IsNullOrWhiteSpace($Destination)) {
        $Destination = "."
    }
    if ([string]::IsNullOrWhiteSpace($Source)) {
        continue
    }
    $AddDataSources += $Source
    $SourceCandidates = @()
    if (-not [string]::IsNullOrWhiteSpace($SourceRoot)) {
        $SourceCandidates += (Join-RelativePath -Base $SourceRoot -Relative $Source)
    }
    if ($ResolvedOutputDir) {
        $SourceCandidates += (Join-RelativePath -Base $ResolvedOutputDir -Relative $Source)
        $SourceCandidates += (Join-RelativePath -Base $FinalAppDir -Relative $Source)
    }
    $SourcePath = Get-ExistingPath -Paths $SourceCandidates
    $SourceFound = -not [string]::IsNullOrWhiteSpace($SourcePath)
    $ExpectedRelatives = Get-ExpectedAddDataRelatives -Source $Source -Destination $Destination -SourcePath $SourcePath -RequiredFiles $RequiredFiles

    foreach ($ExpectedRelative in @($ExpectedRelatives)) {
        if ([string]::IsNullOrWhiteSpace($ExpectedRelative)) {
            continue
        }
        $ExpectedPackagedRelatives += $ExpectedRelative
        $ExpectedApps = Join-RelativePath -Base $AppBinRoot -Relative $ExpectedRelative
        $InternalApps = Join-RelativePath -Base (Join-Path $AppBinRoot "_internal") -Relative $ExpectedRelative
        $ExpectedOutput = if ($OutputBinRoot) { Join-RelativePath -Base $OutputBinRoot -Relative $ExpectedRelative } else { $null }
        $InternalOutput = if ($OutputBinRoot) { Join-RelativePath -Base (Join-Path $OutputBinRoot "_internal") -Relative $ExpectedRelative } else { $null }
        $ExpectedExists = Test-Path -LiteralPath $ExpectedApps
        $InternalExists = Test-Path -LiteralPath $InternalApps
        $OutputExpectedExists = $ExpectedOutput -and (Test-Path -LiteralPath $ExpectedOutput)
        $OutputInternalExists = $InternalOutput -and (Test-Path -LiteralPath $InternalOutput)

        if ($ExpectedExists) {
            continue
        }
        if ($InternalExists) {
            $InternalOnlyData += [pscustomobject][ordered]@{
                source = $Source
                destination = $Destination
                expected_relative = $ExpectedRelative
                apps_internal_path = $InternalApps
            }
            $PlacementMismatches += "$ExpectedRelative exists under _internal only; with --contents-directory . new builds should place it beside the exe."
            continue
        }
        $MissingPackagedData += [pscustomobject][ordered]@{
            source = $Source
            destination = $Destination
            expected_relative = $ExpectedRelative
            source_found = $SourceFound
            expected_apps_path = $ExpectedApps
            found_under_apps_internal = $InternalExists
            found_under_output_expected = $OutputExpectedExists
            found_under_output_internal = $OutputInternalExists
        }
        if ($OutputExpectedExists -or $OutputInternalExists) {
            $PlacementMismatches += "$ExpectedRelative exists in the output mirror but not in apps/<app_id>; Apply registration copy may be stale or incomplete."
        }
    }
}
if ($MissingPackagedData.Count -gt 0) {
    Add-Classification "packaged_data_missing"
    Add-Action "Compare build_profile.add_data destinations with runtime_checker/execution_tester expected placement."
}

if (Test-Path -LiteralPath $AppBinRoot -PathType Container) {
    $ImportantExtensions = @(".json", ".csv", ".yaml", ".yml", ".toml", ".ini", ".flow")
    $ImportantFiles = Get-ChildItem -LiteralPath $AppBinRoot -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $ImportantExtensions -contains $_.Extension.ToLowerInvariant() -or $_.Name -eq "config.yaml" } |
        Select-Object -First 80 |
        ForEach-Object { $_.FullName.Substring($AppBinRoot.Length).TrimStart("\", "/") }
}

$InventoryPath = Select-NewestExistingFile -Paths @($OutputInventoryPath, $FinalAppInventoryPath)
$InventoryState = Read-JsonFile -Path $InventoryPath
$IncludedAssetsNotInAddData = @()
if ($InventoryState.status -eq "ok") {
    foreach ($Record in @((Get-Prop -Object $InventoryState.data -Name "records"))) {
        $Include = Get-Prop -Object $Record -Name "include"
        $Category = [string](Get-Prop -Object $Record -Name "category")
        $Rel = [string](Get-Prop -Object $Record -Name "relative_path")
        $CoveredByAddData = $false
        foreach ($SourceRel in @($AddDataSources)) {
            if ($null -ne (Get-RelativeSuffixText -Child $Rel -Base ([string]$SourceRel))) {
                $CoveredByAddData = $true
                break
            }
        }
        if ($Include -eq $true -and $Category -eq "asset" -and -not [string]::IsNullOrWhiteSpace($Rel) -and -not $CoveredByAddData) {
            $IncludedAssetsNotInAddData += $Rel
        }
    }
}
if ($IncludedAssetsNotInAddData.Count -gt 0) {
    Add-Classification "build_profile_detection_gap"
    Add-Action "Review file_inventory assets that were included but not reflected in build_profile.add_data."
}

$OldSignals = @()
$AppEnvTextState = Read-TextFile -Path (Select-NewestExistingFile -Paths @($OutputAppEnvReportPath, $AppEnvLogReportPath))
$CombinedOldText = (($FrozenTextState.text, $AppEnvTextState.text) -join "`n")
if (Contains-Text -Text $CombinedOldText -Needle ("runtime/app_envs/" + $AppId)) {
    $OldSignals += "runtime/app_envs/<app_id> appears in reports"
    if ($TracePolicyId -eq "normal_python_source_to_frozen_folder_build_env_v2") {
        $OldSignals += "current import_plan uses build_env policy; runtime/app_envs in reports is likely stale output from an older run"
    }
}
if (Contains-Text -Text $CombinedOldText -Needle "No module named PyInstaller") {
    $OldSignals += "No module named PyInstaller appears in reports"
}
if ((Contains-Text -Text $CombinedOldText -Needle "app_env") -and -not (Contains-Text -Text $CombinedOldText -Needle "build_env")) {
    $OldSignals += "reports mention app_env without build_env"
}
if ($FrozenHints -contains "No module named PyInstaller") {
    $OldSignals += "frozen report has No module named PyInstaller"
}

$TimestampSignals = @()
$RuntimeTimestampSignals = @()
$ExecutionItem = if (Test-Path -LiteralPath $ExecutionJsonPath -PathType Leaf) { Get-Item -LiteralPath $ExecutionJsonPath } else { $null }
$RuntimeItem = if (Test-Path -LiteralPath $RuntimeJsonPath -PathType Leaf) { Get-Item -LiteralPath $RuntimeJsonPath } else { $null }
$FrozenItem = if ($FrozenReportPath -and (Test-Path -LiteralPath $FrozenReportPath -PathType Leaf)) { Get-Item -LiteralPath $FrozenReportPath } else { $null }
$AppsExeItem = if (Test-Path -LiteralPath $AppExePath -PathType Leaf) { Get-Item -LiteralPath $AppExePath } else { $null }
$AppYamlItem = if (Test-Path -LiteralPath $AppYamlPath -PathType Leaf) { Get-Item -LiteralPath $AppYamlPath } else { $null }
$AppBuildProfileItem = if (Test-Path -LiteralPath $AppBuildProfilePath -PathType Leaf) { Get-Item -LiteralPath $AppBuildProfilePath } else { $null }
$FinalAppYamlPath = if ($FinalAppDir) { Join-Path $FinalAppDir "app.yaml" } else { $null }
$FinalAppYamlItem = if ($FinalAppYamlPath -and (Test-Path -LiteralPath $FinalAppYamlPath -PathType Leaf)) { Get-Item -LiteralPath $FinalAppYamlPath } else { $null }
if ($ExecutionItem -and $FrozenItem -and $ExecutionItem.LastWriteTime -lt $FrozenItem.LastWriteTime) {
    $TimestampSignals += "execution_test_result.json is older than frozen_folder_build_report.md"
}
if ($ExecutionItem -and $AppsExeItem -and $ExecutionItem.LastWriteTime -lt $AppsExeItem.LastWriteTime) {
    $TimestampSignals += "execution_test_result.json is older than apps exe"
}
if ($ExecutionItem -and $AppYamlItem -and $ExecutionItem.LastWriteTime -lt $AppYamlItem.LastWriteTime) {
    $TimestampSignals += "execution_test_result.json is older than apps app.yaml"
}
if ($ExecutionItem -and $AppBuildProfileItem -and $ExecutionItem.LastWriteTime -lt $AppBuildProfileItem.LastWriteTime) {
    $TimestampSignals += "execution_test_result.json is older than apps build_profile.json"
}
if ($RuntimeItem -and $FinalAppYamlItem -and $RuntimeItem.LastWriteTime -lt $FinalAppYamlItem.LastWriteTime) {
    $RuntimeTimestampSignals += "runtime_check_result.json is older than final_app/app.yaml"
}
if ($RuntimeItem -and $FinalAppYamlPath) {
    $FinalAppRunEntry = Get-YamlScalar -Path $FinalAppYamlPath -Key "entry"
    if (-not [string]::IsNullOrWhiteSpace($FinalAppRunEntry)) {
        $FinalAppRunEntryPath = Join-RelativePath -Base $FinalAppDir -Relative $FinalAppRunEntry
        if (Test-Path -LiteralPath $FinalAppRunEntryPath -PathType Leaf) {
            $FinalAppRunEntryItem = Get-Item -LiteralPath $FinalAppRunEntryPath
            if ($RuntimeItem.LastWriteTime -lt $FinalAppRunEntryItem.LastWriteTime) {
                $RuntimeTimestampSignals += "runtime_check_result.json is older than final_app run.entry"
            }
        }
    }
}
if ($ImportPlanState.status -eq "ok") {
    $SelectedBuildMode = [string](Get-Prop -Object $ImportPlanState.data -Name "selected_build_mode")
    $BuildEnvValue = [string](Get-Prop -Object $ImportPlanState.data -Name "build_env")
    $RegistrationPolicy = [string](Get-Prop -Object $ImportPlanState.data -Name "registration_policy")
    if ($SelectedBuildMode -and $SelectedBuildMode -ne "frozen-folder") {
        $OldSignals += "import_plan selected_build_mode is not frozen-folder: $SelectedBuildMode"
    }
    if ([string]::IsNullOrWhiteSpace($BuildEnvValue)) {
        $OldSignals += "import_plan build_env is missing"
    }
    if ([string]::IsNullOrWhiteSpace($RegistrationPolicy)) {
        $OldSignals += "import_plan registration_policy is missing"
    }
}
if ($OldSignals.Count -gt 0) {
    Add-Classification "old_app_env_pyinstaller_path"
    Add-Action "Confirm the local App Studio code is current; archive old ToolHub_AppStudio_Output and data/logs results before rerunning Apply."
}
if (($AppsExeExists -and ($ApprovalAllowed -eq "False" -or $ApprovalAllowed -eq "false") -and $TimestampSignals.Count -gt 0) -or
    ($AppsExeExists -and ($ApprovalAllowed -eq "False" -or $ApprovalAllowed -eq "false") -and $FrozenStatus -eq "PASS") -or
    ($AppsExeExists -and ($ApprovalAllowed -eq "False" -or $ApprovalAllowed -eq "false") -and $FrozenStatus -eq "FAIL")) {
    Add-Classification "stale_execution_result_suspected"
    if ($FrozenStatus -eq "FAIL") {
        $TimestampSignals += "apps exe exists while execution_test_result/frozen report still records failure"
    }
    Add-Action "Rerun Apply with the current code and verify execution_test_result.json LastWriteTime changes."
}
if ($RuntimeTimestampSignals.Count -gt 0) {
    Add-Classification "runtime_result_stale_suspected"
    Add-Action "Rerun Apply with the current code and verify runtime_check_result.json LastWriteTime changes."
}

$MirrorOnly = @()
$AppsOnly = @()
$MajorRelatives = @("app.yaml", "build_profile.json", "exe_readiness.json", "requirements.lock", ("bin/" + $AppId + "/" + $AppId + ".exe"))
foreach ($Rel in @($ExpectedPackagedRelatives | Select-Object -Unique)) {
    if (-not [string]::IsNullOrWhiteSpace($Rel)) {
        $MajorRelatives += ("bin/" + $AppId + "/" + $Rel)
        $MajorRelatives += ("bin/" + $AppId + "/_internal/" + $Rel)
    }
}
foreach ($Rel in ($MajorRelatives | Select-Object -Unique)) {
    if (-not $FinalAppDir) {
        continue
    }
    $OutPath = Join-RelativePath -Base $FinalAppDir -Relative $Rel
    $AppPath = Join-RelativePath -Base $AppDir -Relative $Rel
    $OutExists = Test-Path -LiteralPath $OutPath
    $AppExists = Test-Path -LiteralPath $AppPath
    if ($OutExists -and -not $AppExists) {
        $MirrorOnly += $Rel
    } elseif ($AppExists -and -not $OutExists) {
        $AppsOnly += $Rel
    }
}

$ManifestEntry = $null
$ManifestEnabled = "missing"
$ManifestVersion = "missing"
$ManifestPackage = "missing"
$ManifestSha = "missing"
$AppPackPath = $null
$AppPackExists = $false
if ($ManifestState.status -eq "ok") {
    $Apps = Get-Prop -Object $ManifestState.data -Name "apps"
    $ManifestEntry = Get-Prop -Object $Apps -Name $AppId
    if ($ManifestEntry) {
        $ManifestEnabled = [string](Get-Prop -Object $ManifestEntry -Name "enabled")
        $ManifestVersion = [string](Get-Prop -Object $ManifestEntry -Name "version")
        $ManifestPackage = [string](Get-Prop -Object $ManifestEntry -Name "package")
        $ManifestSha = [string](Get-Prop -Object $ManifestEntry -Name "sha256")
        if (-not [string]::IsNullOrWhiteSpace($ManifestPackage)) {
            if ([System.IO.Path]::IsPathRooted($ManifestPackage)) {
                $AppPackPath = $ManifestPackage
            } else {
                $AppPackPath = Join-Path (Join-Path $Root "release") $ManifestPackage
            }
            $AppPackExists = Test-Path -LiteralPath $AppPackPath -PathType Leaf
            Get-FileEvidence -Label "release app pack" -Path $AppPackPath | Out-Null
        }
    }
}
if (-not $ManifestEntry) {
    Add-Classification "manifest_not_registered"
    Add-Action "If output mirror has artifacts but release/app_manifest.json has no app entry, Apply likely stopped before registration."
}

$ApprovalRecordStatus = Get-ApprovalRecordScalar -Text $ApprovalRecordState.text -Key "status"
$ApprovalRecordTargetedStatus = Get-ApprovalRecordScalar -Text $ApprovalRecordState.text -Key "targeted_verification_status"
$ApprovalRecordVerifyBefore = Get-ApprovalRecordScalar -Text $ApprovalRecordState.text -Key "verify_release_before"
$ApprovalRecordVerifyAfter = Get-ApprovalRecordScalar -Text $ApprovalRecordState.text -Key "verify_release_after"
$ApprovalRecordManifestEnabledAfter = Get-ApprovalRecordScalar -Text $ApprovalRecordState.text -Key "manifest_enabled_after"
$ApprovalRecordFailures = @(Get-ApprovalRecordFailures -Text $ApprovalRecordState.text)
if ($ApprovalRecordStatus -eq "failed" -or $ApprovalRecordStatus -eq "rolled_back") {
    Add-Classification "approval_rolled_back_or_failed"
    Add-Action "Open approval_record.md; approval did not complete and release/app_manifest.json may have been restored."
}
if ($ApprovalRecordStatus -eq "approved_with_global_warnings") {
    Add-Classification "approval_succeeded_with_global_verify_warnings"
    Add-Action "The app was approved, but verify_release still has pre-existing unrelated failures. Fix release manifest separately before production release."
}
if (($ManifestEnabled -eq "False" -or $ManifestEnabled -eq "false") -and ($ApprovalRecordStatus -eq "failed" -or $ApprovalRecordStatus -eq "rolled_back")) {
    Add-Classification "manifest_disabled_after_approval_failure"
}
if (($ManifestEnabled -eq "True" -or $ManifestEnabled -eq "true") -and ($AppYamlPath -and -not (Test-Path -LiteralPath $AppYamlPath -PathType Leaf))) {
    Add-Classification "catalog_app_yaml_missing"
}

$CatalogVisible = "unknown"
$CatalogEnabled = "unknown"
$CatalogDisabledReason = "unknown"
$AppYamlExists = Test-Path -LiteralPath $AppYamlPath -PathType Leaf
$YamlRunEntry = Get-YamlScalar -Path $AppYamlPath -Key "entry"
$YamlRunner = Get-YamlScalar -Path $AppYamlPath -Key "runner"
$YamlMode = Get-YamlScalar -Path $AppYamlPath -Key "mode"
if ($ManifestEnabled -eq "True" -or $ManifestEnabled -eq "true") {
    $CatalogEnabled = "true"
    if (-not $AppYamlExists) {
        $CatalogVisible = "false"
        $CatalogDisabledReason = "app_yaml_missing"
    } elseif ([string]::IsNullOrWhiteSpace($YamlRunEntry) -or [string]::IsNullOrWhiteSpace($YamlRunner) -or [string]::IsNullOrWhiteSpace($YamlMode)) {
        $CatalogVisible = "false"
        $CatalogDisabledReason = "app_yaml_parse_or_required_field_error"
    } else {
        $CatalogVisible = "true"
        $CatalogDisabledReason = "none"
    }
} elseif ($ManifestEnabled -eq "False" -or $ManifestEnabled -eq "false") {
    $CatalogEnabled = "false"
    $CatalogVisible = "false"
    $CatalogDisabledReason = "disabled_by_manifest"
}

if ($Classifications.Count -eq 0) {
    Add-Classification "inconclusive"
    Add-Action "Provide -Entry or -OutputDir, then rerun the diagnostic to include the output mirror."
}
if (($ExecutionState.status -ne "ok") -and (-not $OutputExeExists) -and (-not $AppsExeExists)) {
    Add-Classification "inconclusive"
}

switch -Regex (($Classifications -join "|")) {
    "frozen_build_failed" { Add-Action "Open frozen_folder_build_report.md and inspect PyInstaller stderr, environment hints, and expected exe path." }
    "registration_copy_failed_or_not_reached" { Add-Action "Compare output mirror final_app with apps/<app_id>; Apply may have stopped before apply_registration." }
    "packaged_data_missing" { Add-Action "Check whether add_data files are under _internal from an older build or beside the exe as current verification expects." }
    "build_profile_detection_gap" { Add-Action "Update file classification or build_profile generation so included runtime assets become add_data." }
    "old_app_env_pyinstaller_path" { Add-Action "Old app_env/PyInstaller logs are present; separate old output/log folders from a new Apply run." }
    "manifest_not_registered" { Add-Action "Run Apply successfully before Approve; Approve requires release/app_manifest.json to contain the app." }
    "approval_ready" { Add-Action "approval_allowed=true; if Approve still fails, inspect strict warning settings and verify_release output." }
    "secret_scan_blocked_apply" { Add-Action "Secret scan stopped Apply before build_env/PyInstaller; review only blocks_apply=true findings." }
    "secret_scan_overblocking_suspected" { Add-Action "Documentation-only OPENAI_API_KEY or placeholder values should not block Apply after rerunning with the updated scanner." }
    "secret_scan_packaged_secret_risk" { Add-Action "A secret finding appears packaged or not safely excluded; remove it before distribution." }
    "secret_scan_ai_only_block" { Add-Action "AI fallback is expected; Apply can continue when apply_blocked_by_secret_scan=false." }
    "execution_result_wrong_app" { Add-Action "Approval gate will reject this result because app_id does not match the requested app." }
    "execution_result_output_dir_mismatch" { Add-Action "Approval gate will reject this result because output_mirror and execution evidence point at different folders." }
    "execution_result_fail" { Add-Action "Approval gate will reject this result until execution overall_status is no longer fail." }
    "execution_approval_blocking_warning" { Add-Action "Approval gate will reject this result until approval-blocking execution warnings are resolved." }
    "runtime_result_wrong_app" { Add-Action "Approval gate will reject this runtime result because app_id does not match the requested app." }
    "runtime_result_output_dir_mismatch" { Add-Action "Approval gate will reject this runtime result because output_mirror and runtime evidence point at different folders." }
    "runtime_result_fail" { Add-Action "Approval gate will reject this runtime result until runtime overall_status is no longer fail." }
    "runtime_approval_blocking_warning" { Add-Action "Approval gate will reject this runtime result until runtime approval-blocking warnings are resolved." }
    "runtime_result_stale_suspected" { Add-Action "Approval gate can reject stale runtime results; rerun Apply so runtime_check_result.json is newer than final_app artifacts." }
    "approval_rolled_back_or_failed" { Add-Action "Approval did not complete; compare targeted verification failures and verify_release_before/after in approval_record.md." }
    "approval_succeeded_with_global_verify_warnings" { Add-Action "Home visibility should depend on manifest enabled=true and catalog parsing; global verify warnings are pre-existing release debt." }
    "manifest_disabled_after_approval_failure" { Add-Action "release/app_manifest.json still has enabled=false because approval failed or rolled back." }
}

$Conclusion = "Diagnostic completed."
if ($Classifications.Count -gt 0) {
    $Conclusion = "Classified as: " + ($Classifications -join ", ")
}

function Format-CheckList {
    param([object[]]$Checks)
    if (-not $Checks -or $Checks.Count -eq 0) {
        return @("- none")
    }
    $Lines = @()
    foreach ($CheckItem in $Checks) {
        $Name = [string](Get-Prop -Object $CheckItem -Name "name")
        $Status = [string](Get-Prop -Object $CheckItem -Name "status")
        $Detail = [string](Get-Prop -Object $CheckItem -Name "detail")
        $Lines += "- [$Status] $Name - $Detail"
    }
    return $Lines
}

function Format-ArrayLines {
    param([object[]]$Items)
    if (-not $Items -or $Items.Count -eq 0) {
        return @("- none")
    }
    return @($Items | ForEach-Object { "- $_" })
}

function Format-MissingDataLines {
    param([object[]]$Items)
    if (-not $Items -or $Items.Count -eq 0) {
        return @("- none")
    }
    $Lines = @()
    foreach ($Item in $Items) {
        $Lines += "- expected=$($Item.expected_relative), source=$($Item.source), destination=$($Item.destination), source_found=$($Item.source_found), expected_apps=$($Item.expected_apps_path), found_internal=$($Item.found_under_apps_internal), found_output=$($Item.found_under_output_expected), found_output_internal=$($Item.found_under_output_internal)"
    }
    return $Lines
}

function Format-InternalOnlyDataLines {
    param([object[]]$Items)
    if (-not $Items -or $Items.Count -eq 0) {
        return @("- none")
    }
    return @($Items | ForEach-Object { "- expected=$($_.expected_relative), source=$($_.source), destination=$($_.destination), apps_internal=$($_.apps_internal_path)" })
}

$ReportLines = @(
    "# App Studio Import Diagnostic Report",
    "",
    "- app_id: $AppId",
    "- generated_at: $((Get-Date).ToString("yyyy-MM-dd HH:mm:ss"))",
    "- repo_root: $Root",
    "- entry: $(if ($Entry) { $Entry } else { "unknown" })",
    "- output_dir: $(if ($ResolvedOutputDir) { $ResolvedOutputDir } else { "unknown" })",
    "- conclusion: $Conclusion",
    "- classifications: $($Classifications -join ', ')",
    "",
    "## Direct Approval Gate",
    "",
    "- approval_allowed: $ApprovalAllowed",
    "- overall_status: $OverallStatus",
    "- execution result app_id: $(if ($ExecutionResultAppId) { $ExecutionResultAppId } else { "missing" })",
    "- execution result output_dir: $(if ($ExecutionResultOutputDir) { $ExecutionResultOutputDir } else { "missing" })",
    "- execution approval_blocking_warnings_count: $ExecutionBlockingWarningsCount",
    "- execution_test_result path: $ExecutionJsonPath",
    "- last_write_time: $(Format-Time $ExecutionState.last_write_time)",
    "- interpretation: $(if ($ApprovalAllowed -eq "False" -or $ApprovalAllowed -eq "false") { "Approve is directly blocked by approval_allowed=false; root cause is the fail check content below." } else { "No approval_allowed=false direct gate was detected." })",
    "",
    "### Fail Checks"
)
$ReportLines += Format-CheckList -Checks $FailChecks
$ReportLines += @("", "### Warn Checks")
$ReportLines += Format-CheckList -Checks $WarnChecks

$ReportLines += @(
    "",
    "## Runtime Approval Gate",
    "",
    "- runtime_check_result status: $($RuntimeState.status)",
    "- runtime overall_status: $RuntimeOverallStatus",
    "- runtime result app_id: $(if ($RuntimeResultAppId) { $RuntimeResultAppId } else { "missing" })",
    "- runtime result output_dir: $(if ($RuntimeResultOutputDir) { $RuntimeResultOutputDir } else { "missing" })",
    "- runtime approval_blocking_warnings_count: $RuntimeBlockingWarningsCount",
    "- runtime_check_result path: $RuntimeJsonPath",
    "- last_write_time: $(Format-Time $RuntimeState.last_write_time)",
    "",
    "### Runtime Fail Checks"
)
$ReportLines += Format-CheckList -Checks $RuntimeFailChecks

$ReportLines += @(
    "",
    "## Secret Scan",
    "",
    "- secret_scan_report.md: $(if ($OutputSecretReportPath) { $OutputSecretReportPath } else { "missing" })",
    "- secret_scan_report.json status: $($SecretJsonState.status)",
    "- file_inventory.json status: $($FileInventoryState.status)",
    "- apply blocked by secret scan: $SecretApplyBlocked",
    "- AI blocked by secret scan: $SecretAiBlocked",
    "- blocking findings: $SecretBlockingCount",
    "- warning findings: $SecretWarningCount",
    "- manual check findings: $SecretManualCount",
    "",
    "### Top Blocking Secret Findings"
)
$ReportLines += Format-ArrayLines -Items $SecretTopBlocking

$ReportLines += @(
    "",
    "## Frozen Build",
    "",
    "- frozen_folder_build_report path: $(if ($FrozenReportPath) { $FrozenReportPath } else { "missing" })",
    "- build status: $FrozenStatus",
    "- exe in output mirror: $OutputExeExists",
    "- exe in apps: $AppsExeExists",
    "- pyinstaller command has --contents-directory .: $PyInstallerContentsDirectoryDot",
    "- detected error hints:"
)
$ReportLines += Format-ArrayLines -Items $FrozenHints
$ReportLines += @("", "### PyInstaller Command Lines")
$ReportLines += Format-ArrayLines -Items $PyInstallerCommandLines

$ReportLines += @(
    "",
    "## BUILD_REQUIRED",
    "",
    "- output mirror BUILD_REQUIRED: $OutputBuildRequiredExists",
    "- apps BUILD_REQUIRED: $AppsBuildRequiredExists",
    "- interpretation: $BuildRequiredInterpretation",
    "",
    "## Data Files / add-data",
    "",
    "- build_profile path: $(if ($BuildProfilePath) { $BuildProfilePath } else { "missing" })",
    "- build_profile status: $($BuildProfileState.status)",
    "- add_data count: $($AddData.Count)",
    "- required_files count: $($RequiredFiles.Count)",
    "",
    "### Missing Packaged Data"
)
$ReportLines += Format-MissingDataLines -Items $MissingPackagedData
$ReportLines += @("", "### Found Only Under _internal")
$ReportLines += Format-InternalOnlyDataLines -Items $InternalOnlyData
$ReportLines += @("", "### Placement Mismatch Signals")
$ReportLines += Format-ArrayLines -Items $PlacementMismatches
$ReportLines += @("", "### Included Assets Not In add_data")
$ReportLines += Format-ArrayLines -Items $IncludedAssetsNotInAddData
$ReportLines += @("", "### Important Files Found Under Registered bin")
$ReportLines += Format-ArrayLines -Items $ImportantFiles

$ReportLines += @(
    "",
    "## Stale / Old-Path Signals",
    "",
    "### Timestamp Comparison"
)
$ReportLines += Format-ArrayLines -Items $TimestampSignals
$ReportLines += @("", "### Runtime Timestamp Comparison")
$ReportLines += Format-ArrayLines -Items $RuntimeTimestampSignals
$ReportLines += @("", "### Old app_env / PyInstaller Signals")
$ReportLines += Format-ArrayLines -Items $OldSignals
$ReportLines += @(
    "",
    "### Current Import Plan Trace",
    "",
    "- app_studio_policy_id: $(if ($TracePolicyId) { $TracePolicyId } else { "missing" })",
    "- build_env_python: $(if ($TraceBuildEnvPython) { $TraceBuildEnvPython } else { "missing" })",
    "- pyinstaller_probe_python: $(if ($TraceProbePython) { $TraceProbePython } else { "missing" })",
    "- pyinstaller_build_python: $(if ($TraceBuildPython) { $TraceBuildPython } else { "missing" })"
)
$ReportLines += @(
    "",
    "## Registration / Manifest",
    "",
    "- app.yaml exists: $(Test-Path -LiteralPath $AppYamlPath -PathType Leaf)",
    "- release/app_manifest entry: $([bool]$ManifestEntry)",
    "- enabled state: $ManifestEnabled",
    "- version: $ManifestVersion",
    "- package: $ManifestPackage",
    "- sha256: $ManifestSha",
    "- app pack path: $(if ($AppPackPath) { $AppPackPath } else { "missing" })",
    "- app pack exists: $AppPackExists",
    "- approval_record path: $ApprovalRecordPath",
    "- approval_record status: $ApprovalRecordStatus",
    "- approval_record manifest_enabled_after: $ApprovalRecordManifestEnabledAfter",
    "- targeted_verification_status: $ApprovalRecordTargetedStatus",
    "- verify_release_before: $ApprovalRecordVerifyBefore",
    "- verify_release_after: $ApprovalRecordVerifyAfter",
    "- approval failures: $(if ($ApprovalRecordFailures.Count -gt 0) { $ApprovalRecordFailures -join ' | ' } else { 'none' })",
    "- catalog_visible: $CatalogVisible",
    "- catalog_enabled: $CatalogEnabled",
    "- catalog_disabled_reason: $CatalogDisabledReason",
    "",
    "## Output Mirror vs Registered App",
    "",
    "### Files only in output mirror"
)
$ReportLines += Format-ArrayLines -Items $MirrorOnly
$ReportLines += @("", "### Files only in apps")
$ReportLines += Format-ArrayLines -Items $AppsOnly
$ReportLines += @(
    "",
    "## Recommended Next Actions"
)
$ReportLines += Format-ArrayLines -Items $Actions
$ReportLines += @(
    "",
    "## Raw Evidence",
    "",
    "### Key Paths",
    "",
    "- apps dir: $AppDir",
    "- apps exe: $AppExePath",
    "- output exe: $(if ($OutputExePath) { $OutputExePath } else { "unknown" })",
    "- log dir: $LogDir",
    "",
    "### Parsed Snippets",
    "",
    "- execution JSON status: $($ExecutionState.status)",
    "- output execution JSON status: $($OutputExecutionState.status)",
    "- runtime JSON status: $($RuntimeState.status)",
    "- import_plan status: $($ImportPlanState.status)",
    "- manifest JSON status: $($ManifestState.status)",
    "",
    "### Parse Errors"
)
$ReportLines += Format-ArrayLines -Items $ParseErrors

if ($VerboseFiles) {
    $ReportLines += @("", "### Verbose File Evidence", "", "| Label | Exists | Kind | LastWriteTime | Size | Path |", "| --- | --- | --- | --- | --- | --- |")
    foreach ($Item in $Evidence) {
        $ReportLines += "| $($Item.label) | $($Item.exists) | $($Item.kind) | $(Format-Time $Item.last_write_time) | $($Item.size) | $($Item.path) |"
    }
}

$Report = ($ReportLines -join "`n") + "`n"
$ReportPath = Join-Path $LogDir ($AppId + "_diagnostic_report.md")
if (-not $NoWrite) {
    try {
        if (-not (Test-Path -LiteralPath $LogDir -PathType Container)) {
            New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
        }
        Set-Content -LiteralPath $ReportPath -Value $Report -Encoding UTF8
    } catch {
        Write-Warning "Diagnostic report could not be written: $($_.Exception.Message)"
    }
}

$Summary = [ordered]@{
    app_id = $AppId
    generated_at = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    repo_root = $Root
    entry = $Entry
    output_dir = $ResolvedOutputDir
    conclusion = $Conclusion
    classifications = @($Classifications)
    report_path = if ($NoWrite) { $null } else { $ReportPath }
    direct_approval_gate = [ordered]@{
        approval_allowed = $ApprovalAllowed
        overall_status = $OverallStatus
        result_app_id = $ExecutionResultAppId
        result_output_dir = $ExecutionResultOutputDir
        approval_blocking_warnings_count = $ExecutionBlockingWarningsCount
        fail_count = $FailChecks.Count
        warn_count = $WarnChecks.Count
        path = $ExecutionJsonPath
        last_write_time = $ExecutionState.last_write_time
    }
    runtime_approval_gate = [ordered]@{
        status = $RuntimeState.status
        overall_status = $RuntimeOverallStatus
        result_app_id = $RuntimeResultAppId
        result_output_dir = $RuntimeResultOutputDir
        approval_blocking_warnings_count = $RuntimeBlockingWarningsCount
        fail_count = $RuntimeFailChecks.Count
        path = $RuntimeJsonPath
        last_write_time = $RuntimeState.last_write_time
    }
    frozen_build = [ordered]@{
        status = $FrozenStatus
        report_path = $FrozenReportPath
        exe_in_output_mirror = $OutputExeExists
        exe_in_apps = $AppsExeExists
        pyinstaller_contents_directory_dot = $PyInstallerContentsDirectoryDot
        pyinstaller_command_lines = $PyInstallerCommandLines
        detected_error_hints = $FrozenHints
    }
    build_required = [ordered]@{
        output_mirror = $OutputBuildRequiredExists
        apps = $AppsBuildRequiredExists
        interpretation = $BuildRequiredInterpretation
    }
    add_data = [ordered]@{
        profile_path = $BuildProfilePath
        add_data_count = $AddData.Count
        missing_packaged_data_count = $MissingPackagedData.Count
        internal_only_data_count = $InternalOnlyData.Count
        included_assets_not_in_add_data_count = $IncludedAssetsNotInAddData.Count
    }
    secret_scan = [ordered]@{
        report_path = $OutputSecretReportPath
        json_status = $SecretJsonState.status
        file_inventory_status = $FileInventoryState.status
        apply_blocked = $SecretApplyBlocked
        ai_blocked = $SecretAiBlocked
        blocking_findings = $SecretBlockingCount
        warning_findings = $SecretWarningCount
        manual_check_findings = $SecretManualCount
        top_blocking = @($SecretTopBlocking)
    }
    import_plan_trace = [ordered]@{
        app_studio_policy_id = $TracePolicyId
        build_env_python = $TraceBuildEnvPython
        pyinstaller_probe_python = $TraceProbePython
        pyinstaller_build_python = $TraceBuildPython
    }
    stale_signals = [ordered]@{
        execution = @($TimestampSignals)
        runtime = @($RuntimeTimestampSignals)
        old_path = @($OldSignals)
    }
    manifest = [ordered]@{
        registered = [bool]$ManifestEntry
        enabled = $ManifestEnabled
        version = $ManifestVersion
        package = $ManifestPackage
        app_pack_exists = $AppPackExists
        approval_record_status = $ApprovalRecordStatus
        approval_record_path = $ApprovalRecordPath
        approval_record_manifest_enabled_after = $ApprovalRecordManifestEnabledAfter
        targeted_verification_status = $ApprovalRecordTargetedStatus
        verify_release_before = $ApprovalRecordVerifyBefore
        verify_release_after = $ApprovalRecordVerifyAfter
        approval_failures = @($ApprovalRecordFailures)
        catalog_visible = $CatalogVisible
        catalog_enabled = $CatalogEnabled
        catalog_disabled_reason = $CatalogDisabledReason
    }
}

if ($AsJson) {
    Write-Output ($Summary | ConvertTo-Json -Depth 8)
} else {
    Write-Output $Report
}

exit 0
