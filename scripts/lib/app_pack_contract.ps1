# Read-only App Pack contract helpers used by parity tests, packaging, and verification scripts.
# This file intentionally defines functions only. It does not read or write
# apps/, release/, runtime/, fixtures, manifests, or App Pack artifacts on load.

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

function Get-AppPackContractSummary {
    param(
        [string]$AppId,
        [string]$YamlText
    )
    $RunEntry = Read-AppRelativeYamlFile -YamlText $YamlText -Section "run" -Key "entry" -Label "$AppId run.entry"
    $DisplayIcon = Read-AppRelativeYamlFile -YamlText $YamlText -Section "display" -Key "icon" -Label "$AppId display.icon"
    $RequirementsLock = Get-RequirementsLockPathForAppPack -YamlText $YamlText -Label "$AppId runtime.requirements_lock"
    $RequiredEntries = Get-AppPackRequiredEntries -AppId $AppId -RunEntry $RunEntry -DisplayIcon $DisplayIcon -RequirementsLock $RequirementsLock
    return [pscustomobject]@{
        app_id = $AppId
        run_entry = $RunEntry
        display_icon = $DisplayIcon
        requirements_lock = $RequirementsLock
        is_frozen_folder = Test-AppStudioFrozenFolderYaml -YamlText $YamlText
        required_entries = @($RequiredEntries | Sort-Object)
    }
}
