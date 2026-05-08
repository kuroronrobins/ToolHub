param(
    [switch]$DryRun,
    [switch]$Apply,
    [switch]$KeepStale,
    [switch]$Json
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

. (Join-Path $PSScriptRoot "utf8_no_bom.ps1")

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ReleaseDir = Join-Path $Root "release"
$AppsDir = Join-Path $Root "apps"
$AppManifestPath = Join-Path $ReleaseDir "app_manifest.json"

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

function Read-YamlScalar {
    param(
        [string]$Text,
        [string]$Key
    )
    $Pattern = "(?m)^\s*$([regex]::Escape($Key))\s*:\s*(.+?)\s*$"
    $Match = [regex]::Match($Text, $Pattern)
    if (-not $Match.Success) { return $null }
    return Normalize-YamlScalar $Match.Groups[1].Value
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

function Get-PropertyValue {
    param(
        [object]$Object,
        [string]$Name,
        [object]$DefaultValue = $null
    )
    if ($null -eq $Object) { return $DefaultValue }
    $Property = $Object.PSObject.Properties[$Name]
    if ($null -eq $Property) { return $DefaultValue }
    if ($null -eq $Property.Value) { return $DefaultValue }
    return $Property.Value
}

function Entry-Enabled {
    param([object]$Entry)
    $Value = Get-PropertyValue -Object $Entry -Name "enabled" -DefaultValue $true
    return [bool]$Value
}

function Get-Sha256OrEmpty {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return ""
    }
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Entry-From-AppYaml {
    param(
        [string]$AppId,
        [string]$AppYamlPath,
        [object]$ExistingEntry
    )
    $Text = Get-Content -Raw -Encoding UTF8 $AppYamlPath
    $YamlId = Read-YamlScalar -Text $Text -Key "id"
    if ([string]::IsNullOrWhiteSpace($YamlId)) {
        $YamlId = $AppId
    }
    $Version = Read-YamlSectionScalar -Text $Text -Section "admin" -Key "version"
    if ([string]::IsNullOrWhiteSpace($Version)) {
        $Version = [string](Get-PropertyValue -Object $ExistingEntry -Name "version" -DefaultValue "0.1.0")
    }
    $RequiredRuntime = Read-YamlSectionScalar -Text $Text -Section "runtime" -Key "required_runtime"
    if ([string]::IsNullOrWhiteSpace($RequiredRuntime)) {
        $RequiredRuntime = Get-PropertyValue -Object $ExistingEntry -Name "required_runtime" -DefaultValue $null
    }
    $Package = "app_packs/$YamlId-$Version.zip"
    $PackagePath = Join-Path $ReleaseDir $Package

    return [ordered]@{
        version = $Version
        package = $Package
        sha256 = Get-Sha256OrEmpty $PackagePath
        required_core = Get-PropertyValue -Object $ExistingEntry -Name "required_core" -DefaultValue ">=0.1.0"
        required_runner = Get-PropertyValue -Object $ExistingEntry -Name "required_runner" -DefaultValue ">=0.1.0"
        required_runtime = $RequiredRuntime
        enabled = if ($ExistingEntry) { Entry-Enabled $ExistingEntry } else { $false }
    }
}

if (-not (Test-Path -LiteralPath $AppManifestPath -PathType Leaf)) {
    throw "release/app_manifest.json was not found."
}
if (-not (Test-Path -LiteralPath $AppsDir -PathType Container)) {
    throw "apps directory was not found."
}

$ExistingManifest = Get-Content -Raw -Encoding UTF8 $AppManifestPath | ConvertFrom-Json
$ExistingApps = $ExistingManifest.apps
$ExistingAppIds = @()
if ($ExistingApps) {
    $ExistingAppIds = @($ExistingApps.PSObject.Properties.Name)
}

$SourceAppIds = @(
    Get-ChildItem -LiteralPath $AppsDir -Directory |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "app.yaml") -PathType Leaf } |
        ForEach-Object { $_.Name } |
        Sort-Object
)

$NewApps = [ordered]@{}
$PackageMissing = @()
$Sha256Empty = @()
foreach ($AppId in $SourceAppIds) {
    $ExistingEntry = if ($ExistingApps) { Get-PropertyValue -Object $ExistingApps -Name $AppId -DefaultValue $null } else { $null }
    $AppYamlPath = Join-Path (Join-Path $AppsDir $AppId) "app.yaml"
    $NewApps[$AppId] = Entry-From-AppYaml -AppId $AppId -AppYamlPath $AppYamlPath -ExistingEntry $ExistingEntry
    $PackagePath = Join-Path $ReleaseDir ([string]$NewApps[$AppId].package)
    if (-not (Test-Path -LiteralPath $PackagePath -PathType Leaf)) {
        $PackageMissing += $AppId
    }
    if ([string]::IsNullOrWhiteSpace([string]$NewApps[$AppId].sha256)) {
        $Sha256Empty += $AppId
    }
}

if ($KeepStale) {
    foreach ($AppId in $ExistingAppIds) {
        if ($NewApps.Contains($AppId)) { continue }
        $NewApps[$AppId] = Get-PropertyValue -Object $ExistingApps -Name $AppId
    }
}

$NewManifest = [ordered]@{
    schema_version = Get-PropertyValue -Object $ExistingManifest -Name "schema_version" -DefaultValue 1
    channel = Get-PropertyValue -Object $ExistingManifest -Name "channel" -DefaultValue "stable"
    apps = $NewApps
}

$OldJson = ($ExistingManifest | ConvertTo-Json -Depth 20)
$NewJson = ($NewManifest | ConvertTo-Json -Depth 20)
$Added = @($SourceAppIds | Where-Object { $ExistingAppIds -notcontains $_ })
$Removed = @($ExistingAppIds | Where-Object { $NewApps.Keys -notcontains $_ })
$Changed = @()
foreach ($AppId in $NewApps.Keys) {
    if ($ExistingAppIds -notcontains $AppId) { continue }
    $OldEntryJson = (Get-PropertyValue -Object $ExistingApps -Name $AppId | ConvertTo-Json -Depth 20 -Compress)
    $NewEntryJson = ($NewApps[$AppId] | ConvertTo-Json -Depth 20 -Compress)
    if ($OldEntryJson -ne $NewEntryJson) {
        $Changed += $AppId
    }
}

$Summary = [ordered]@{
    mode = if ($Apply -and -not $DryRun) { "apply" } else { "dry_run" }
    keep_stale = [bool]$KeepStale
    source_app_count = $SourceAppIds.Count
    existing_manifest_count = $ExistingAppIds.Count
    rebuilt_manifest_count = $NewApps.Count
    added = $Added
    removed = $Removed
    changed = $Changed
    package_missing = $PackageMissing
    sha256_empty = $Sha256Empty
    would_write = ($Apply -and -not $DryRun -and $OldJson -ne $NewJson)
}

if ($Json) {
    $Summary | ConvertTo-Json -Depth 20
} else {
    Write-Host "App manifest rebuild plan"
    Write-Host "  mode: $($Summary.mode)"
    Write-Host "  source apps: $($Summary.source_app_count)"
    Write-Host "  existing manifest entries: $($Summary.existing_manifest_count)"
    Write-Host "  rebuilt entries: $($Summary.rebuilt_manifest_count)"
    Write-Host "  added: $($Added.Count)"
    foreach ($Item in $Added) { Write-Host "    + $Item" }
    Write-Host "  removed stale entries: $($Removed.Count)"
    foreach ($Item in $Removed) { Write-Host "    - $Item" }
    Write-Host "  changed: $($Changed.Count)"
    foreach ($Item in $Changed) { Write-Host "    * $Item" }
    Write-Host "  package missing: $($PackageMissing.Count)"
    foreach ($Item in $PackageMissing) { Write-Host "    ! $Item" }
    Write-Host "  sha256 empty: $($Sha256Empty.Count)"
    foreach ($Item in $Sha256Empty) { Write-Host "    ! $Item" }
}

if ($Apply -and -not $DryRun) {
    Write-Utf8NoBomFile -Path $AppManifestPath -Content ($NewJson + "`n")
    Write-Host "Updated release/app_manifest.json"
}
