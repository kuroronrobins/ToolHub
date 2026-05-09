$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$FixtureRoot = Join-Path $Root "tools\app_studio\tests\fixtures\app_pack_contract"
$ContractPath = Join-Path $FixtureRoot "expected_contract.json"

if (-not (Test-Path -LiteralPath $ContractPath -PathType Leaf)) {
    throw "Contract fixture is missing: $ContractPath"
}

# package_app_pack.ps1 and verify_release.ps1 execute their main flow on load.
# This read-only test mirrors their shared scalar/path contract against the same
# golden fixture used by Python unit tests without touching apps/release/runtime.
function Normalize-YamlScalar {
    param([string]$Value)
    if ($null -eq $Value) { return $null }
    $Text = $Value.Trim()
    $CommentIndex = $Text.IndexOf(" #")
    if ($CommentIndex -ge 0) {
        $Text = $Text.Substring(0, $CommentIndex).Trim()
    }
    if (($Text.StartsWith('"') -and $Text.EndsWith('"')) -or ($Text.StartsWith("'") -and $Text.EndsWith("'"))) {
        $Text = $Text.Substring(1, $Text.Length - 2)
    }
    if ($Text -eq "" -or $Text -eq "null" -or $Text -eq "~") {
        return $null
    }
    return $Text
}

function Read-YamlSectionScalar {
    param(
        [string]$Text,
        [string]$Section,
        [string]$Key
    )
    $Lines = $Text -split "`r?`n"
    $InSection = $false
    $SectionIndent = -1
    foreach ($Line in $Lines) {
        if (-not $InSection) {
            $SectionPattern = "^(\s*)$([regex]::Escape($Section))\s*:\s*(?:#.*)?$"
            if ($Line -match $SectionPattern) {
                $InSection = $true
                $SectionIndent = $Matches[1].Length
            }
            continue
        }

        if ($Line.Trim() -eq "") { continue }
        if ($Line -match "^(\s*)\S") {
            $Indent = $Matches[1].Length
            if ($Indent -le $SectionIndent) { break }
        }
        $KeyPattern = "^\s*$([regex]::Escape($Key))\s*:\s*(.+?)\s*$"
        if ($Line -match $KeyPattern) {
            return Normalize-YamlScalar $Matches[1]
        }
    }
    return $null
}

function Normalize-AppRelativePath {
    param(
        [string]$Path,
        [string]$Label
    )
    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw "$Label is missing."
    }
    $Normalized = $Path.Trim().Replace("\", "/")
    if ([string]::IsNullOrWhiteSpace($Normalized)) {
        throw "$Label is missing."
    }
    if ([System.IO.Path]::IsPathRooted($Normalized) -or $Normalized -match "^[A-Za-z]:/") {
        throw "$Label must be a relative path inside the app directory: $Path"
    }
    $Parts = @()
    foreach ($Part in ($Normalized -split "/")) {
        if ($Part -eq "" -or $Part -eq ".") {
            continue
        }
        if ($Part -eq "..") {
            throw "$Label must stay inside the app directory: $Path"
        }
        $Parts += $Part
    }
    if ($Parts.Count -eq 0) {
        throw "$Label is missing."
    }
    return ($Parts -join "/")
}

function Resolve-AppRelativeFile {
    param(
        [string]$AppDir,
        [string]$RelativePath,
        [string]$Label
    )
    $NativeRelative = (($RelativePath -split "/") -join [System.IO.Path]::DirectorySeparatorChar)
    $Full = [System.IO.Path]::GetFullPath((Join-Path $AppDir $NativeRelative))
    $AppRoot = [System.IO.Path]::GetFullPath($AppDir).TrimEnd([char[]]@("\", "/")) + [System.IO.Path]::DirectorySeparatorChar
    if (-not $Full.StartsWith($AppRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "$Label must stay inside the app directory: $RelativePath"
    }
    return $Full
}

function Read-AppRelativeYamlFile {
    param(
        [string]$YamlText,
        [string]$Section,
        [string]$Key,
        [string]$Label
    )
    $Value = Read-YamlSectionScalar -Text $YamlText -Section $Section -Key $Key
    return Normalize-AppRelativePath -Path $Value -Label $Label
}

function Test-AppStudioFrozenFolderYaml {
    param([string]$YamlText)
    $DistributionMode = [string](Read-YamlSectionScalar -Text $YamlText -Section "runtime" -Key "distribution_mode")
    $BuildMode = [string](Read-YamlSectionScalar -Text $YamlText -Section "build" -Key "build_mode")
    $DistributionMode = $DistributionMode.Trim().ToLowerInvariant()
    $BuildMode = $BuildMode.Trim().ToLowerInvariant()
    return $DistributionMode -in @("frozen_folder", "frozen-folder") -or $BuildMode -in @("frozen_folder", "frozen-folder")
}

function Get-RequirementsLockPathForAppPack {
    param(
        [string]$YamlText,
        [string]$Label
    )
    $Value = Read-YamlSectionScalar -Text $YamlText -Section "runtime" -Key "requirements_lock"
    if (-not [string]::IsNullOrWhiteSpace($Value)) {
        return Normalize-AppRelativePath -Path $Value -Label $Label
    }
    if (Test-AppStudioFrozenFolderYaml -YamlText $YamlText) {
        return "requirements.lock"
    }
    return $null
}

function Get-AppPackRequiredEntries {
    param(
        [string]$AppId,
        [string]$RunEntry,
        [string]$DisplayIcon,
        [AllowNull()][string]$RequirementsLock
    )
    $Entries = @(
        "$AppId/app.yaml",
        "$AppId/pack_manifest.json",
        "$AppId/README.md",
        "$AppId/requirements.txt",
        "$AppId/$DisplayIcon",
        "$AppId/$RunEntry"
    )
    if (-not [string]::IsNullOrWhiteSpace($RequirementsLock)) {
        $Entries += "$AppId/$RequirementsLock"
    }
    return $Entries
}

function Assert-Equal {
    param(
        [AllowNull()]$Actual,
        [AllowNull()]$Expected,
        [string]$Message
    )
    if ($null -eq $Expected) {
        if ($null -ne $Actual) {
            throw "$Message expected <null>, got <$Actual>"
        }
        return
    }
    if ($Actual -ne $Expected) {
        throw "$Message expected <$Expected>, got <$Actual>"
    }
}

function Assert-SequenceEqual {
    param(
        [string[]]$Actual,
        [string[]]$Expected,
        [string]$Message
    )
    $ActualSorted = @($Actual | Sort-Object)
    $ExpectedSorted = @($Expected | Sort-Object)
    $Diff = Compare-Object -ReferenceObject $ExpectedSorted -DifferenceObject $ActualSorted
    if ($Diff) {
        $Formatted = ($Diff | ForEach-Object { "$($_.SideIndicator) $($_.InputObject)" }) -join "; "
        throw "$Message mismatch: $Formatted"
    }
}

$Contract = Get-Content -LiteralPath $ContractPath -Raw | ConvertFrom-Json

foreach ($Case in $Contract.cases) {
    $AppDir = Join-Path $FixtureRoot $Case.app_dir
    $YamlPath = Join-Path $AppDir "app.yaml"
    if (-not (Test-Path -LiteralPath $YamlPath -PathType Leaf)) {
        throw "Fixture app.yaml is missing for $($Case.id): $YamlPath"
    }
    $YamlText = Get-Content -LiteralPath $YamlPath -Raw
    $RunEntry = Read-AppRelativeYamlFile -YamlText $YamlText -Section "run" -Key "entry" -Label "$($Case.id) run.entry"
    $DisplayIcon = Read-AppRelativeYamlFile -YamlText $YamlText -Section "display" -Key "icon" -Label "$($Case.id) display.icon"
    $RequirementsLock = Get-RequirementsLockPathForAppPack -YamlText $YamlText -Label "$($Case.id) runtime.requirements_lock"

    Assert-Equal -Actual $RunEntry -Expected $Case.expected_run_entry -Message "$($Case.id) run.entry"
    Assert-Equal -Actual $DisplayIcon -Expected $Case.expected_display_icon -Message "$($Case.id) display.icon"
    Assert-Equal -Actual $RequirementsLock -Expected $Case.expected_requirements_lock -Message "$($Case.id) runtime.requirements_lock"

    foreach ($RelativePath in @("README.md", "requirements.txt", $RunEntry, $DisplayIcon)) {
        $FullPath = Resolve-AppRelativeFile -AppDir $AppDir -RelativePath $RelativePath -Label "$($Case.id) $RelativePath"
        if (-not (Test-Path -LiteralPath $FullPath -PathType Leaf)) {
            throw "$($Case.id) fixture file is missing: $FullPath"
        }
    }
    if ($RequirementsLock) {
        $LockPath = Resolve-AppRelativeFile -AppDir $AppDir -RelativePath $RequirementsLock -Label "$($Case.id) runtime.requirements_lock"
        if (-not (Test-Path -LiteralPath $LockPath -PathType Leaf)) {
            throw "$($Case.id) lock fixture file is missing: $LockPath"
        }
    }

    $RequiredEntries = Get-AppPackRequiredEntries -AppId $Case.app_id -RunEntry $RunEntry -DisplayIcon $DisplayIcon -RequirementsLock $RequirementsLock
    Assert-SequenceEqual -Actual $RequiredEntries -Expected @($Case.expected_required_entries) -Message "$($Case.id) required entries"
}

foreach ($Case in $Contract.path_normalization_cases) {
    $HasExpected = $null -ne $Case.PSObject.Properties["expected"]
    $HasError = $null -ne $Case.PSObject.Properties["error_contains"]
    try {
        $Actual = Normalize-AppRelativePath -Path $Case.input -Label "fixture path"
        if ($HasError) {
            throw "$($Case.id) expected an error containing <$($Case.error_contains)>"
        }
        Assert-Equal -Actual $Actual -Expected $Case.expected -Message "$($Case.id) normalized path"
    } catch {
        if ($HasExpected) {
            throw
        }
        if (-not ($_.Exception.Message -like "*$($Case.error_contains)*")) {
            throw "$($Case.id) expected error containing <$($Case.error_contains)>, got <$($_.Exception.Message)>"
        }
    }
}

Write-Host "[OK] App Pack contract parity fixture matches PowerShell read-only helper expectations."
