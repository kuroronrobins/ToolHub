param(
    [string[]]$AppId,
    [switch]$NoManifestUpdate
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ReleaseDir = Join-Path $Root "release"
$AppsDir = Join-Path $Root "apps"
$AppManifestPath = Join-Path $ReleaseDir "app_manifest.json"
$AppPacksDir = Join-Path $ReleaseDir "app_packs"
$StageRoot = Join-Path $ReleaseDir "staging\app_pack_build"
Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction SilentlyContinue

function Assert-InRoot {
    param([string]$Path)
    $Full = [System.IO.Path]::GetFullPath($Path)
    if (-not $Full.StartsWith($Root, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing path outside workspace: $Full"
    }
    return $Full
}

function Reset-Directory {
    param([string]$Path)
    $Full = Assert-InRoot $Path
    if (Test-Path -LiteralPath $Full) {
        Remove-Item -LiteralPath $Full -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $Full | Out-Null
}

function Require-File {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Required file is missing: $Path"
    }
}

function Entry-Enabled {
    param([object]$Entry)
    if ($null -eq $Entry.PSObject.Properties["enabled"]) {
        return $true
    }
    return [bool]$Entry.enabled
}

function Set-EntryProperty {
    param(
        [object]$Entry,
        [string]$Name,
        [object]$Value
    )
    $Property = $Entry.PSObject.Properties[$Name]
    if ($Property) {
        $Property.Value = $Value
    } else {
        $Entry | Add-Member -NotePropertyName $Name -NotePropertyValue $Value
    }
}

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

function Require-AppYamlReferencedFile {
    param(
        [string]$AppDir,
        [string]$RelativePath,
        [string]$Label
    )
    $FullPath = Resolve-AppRelativeFile -AppDir $AppDir -RelativePath $RelativePath -Label $Label
    if (-not (Test-Path -LiteralPath $FullPath -PathType Leaf)) {
        throw "$Label file is missing: $FullPath"
    }
    return $FullPath
}

function Assert-ZipContainsEntry {
    param(
        [string]$ZipPath,
        [string]$EntryName,
        [string]$Label
    )
    $Zip = $null
    try {
        $Zip = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
        $EntryNames = @($Zip.Entries | ForEach-Object { $_.FullName.Replace("\", "/") })
    } catch {
        throw "$Label could not be inspected in zip: $ZipPath. $($_.Exception.Message)"
    } finally {
        if ($Zip) {
            $Zip.Dispose()
        }
    }
    if ($EntryNames -notcontains $EntryName) {
        throw "$Label is missing from zip: $EntryName"
    }
}

function Get-SourceAppIds {
    if (-not (Test-Path -LiteralPath $AppsDir -PathType Container)) {
        return @()
    }
    return @(
        Get-ChildItem -LiteralPath $AppsDir -Directory |
            Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "app.yaml") -PathType Leaf } |
            ForEach-Object { $_.Name } |
            Sort-Object
    )
}

function New-AppManifestEntry {
    param(
        [string]$Id,
        [string]$Version,
        [string]$RequiredRuntime
    )
    return [pscustomobject]@{
        version = $Version
        package = "app_packs/$Id-$Version.zip"
        sha256 = ""
        required_core = ">=0.1.0"
        required_runner = ">=0.1.0"
        required_runtime = $RequiredRuntime
        enabled = $false
    }
}

if (-not (Test-Path -LiteralPath $AppManifestPath -PathType Leaf)) {
    throw "release/app_manifest.json was not found."
}

$AppManifest = Get-Content -Raw -Encoding UTF8 $AppManifestPath | ConvertFrom-Json
$KnownAppIds = @($AppManifest.apps.PSObject.Properties.Name)
$ExplicitTargets = $AppId -and $AppId.Count -gt 0
$SourceAppIds = Get-SourceAppIds
$TargetAppIds = if ($ExplicitTargets) { $AppId } else { $SourceAppIds }

New-Item -ItemType Directory -Force -Path $AppPacksDir | Out-Null
Reset-Directory $StageRoot

foreach ($Id in $TargetAppIds) {
    $AppDir = Join-Path (Join-Path $Root "apps") $Id
    $AppYaml = Join-Path $AppDir "app.yaml"
    if (-not (Test-Path -LiteralPath $AppYaml -PathType Leaf)) {
        throw "App source is missing for ${Id}: $AppYaml"
    }

    $YamlText = Get-Content -Raw -Encoding UTF8 $AppYaml
    $YamlVersion = Read-YamlSectionScalar -Text $YamlText -Section "admin" -Key "version"
    $YamlRequiredRuntime = Read-YamlSectionScalar -Text $YamlText -Section "runtime" -Key "required_runtime"
    $YamlRunEntry = Read-AppRelativeYamlFile -YamlText $YamlText -Section "run" -Key "entry" -Label "$Id run.entry"
    $YamlDisplayIcon = Read-AppRelativeYamlFile -YamlText $YamlText -Section "display" -Key "icon" -Label "$Id display.icon"

    if ($KnownAppIds -contains $Id) {
        $Entry = $AppManifest.apps.$Id
    } else {
        $VersionForNewEntry = if ([string]::IsNullOrWhiteSpace($YamlVersion)) { "0.1.0" } else { $YamlVersion }
        $Entry = New-AppManifestEntry -Id $Id -Version $VersionForNewEntry -RequiredRuntime $YamlRequiredRuntime
        $AppManifest.apps | Add-Member -NotePropertyName $Id -NotePropertyValue $Entry
        $KnownAppIds += $Id
        Write-Host "[INFO] $Id was found in apps/ but not in app_manifest; adding disabled manifest entry from app.yaml."
    }

    Require-File (Join-Path $AppDir "README.md")
    Require-File (Join-Path $AppDir "requirements.txt")
    Require-AppYamlReferencedFile -AppDir $AppDir -RelativePath $YamlRunEntry -Label "$Id run.entry" | Out-Null
    Require-AppYamlReferencedFile -AppDir $AppDir -RelativePath $YamlDisplayIcon -Label "$Id display.icon" | Out-Null
    if (-not (Test-Path -LiteralPath (Join-Path $AppDir "icon.svg") -PathType Leaf) -and
        -not (Test-Path -LiteralPath (Join-Path $AppDir "icon.png") -PathType Leaf)) {
        throw "Required app icon is missing: $AppDir\icon.svg or $AppDir\icon.png"
    }

    $Version = if ([string]::IsNullOrWhiteSpace($YamlVersion)) { [string]$Entry.version } else { $YamlVersion }
    if ([string]::IsNullOrWhiteSpace($Version)) {
        throw "Version is missing in app.yaml/admin.version and app_manifest.json for $Id"
    }
    Set-EntryProperty -Entry $Entry -Name "version" -Value $Version
    if (-not [string]::IsNullOrWhiteSpace($YamlRequiredRuntime)) {
        Set-EntryProperty -Entry $Entry -Name "required_runtime" -Value $YamlRequiredRuntime
    }

    $PackageRelative = "app_packs/$Id-$Version.zip"
    $PackagePath = Join-Path $ReleaseDir $PackageRelative
    $StageAppDir = Join-Path $StageRoot $Id

    Copy-Item -LiteralPath $AppDir -Destination $StageAppDir -Recurse -Force

    Get-ChildItem -Path $StageAppDir -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path $StageAppDir -Recurse -File -Include "*.pyc","*.pyo" -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction SilentlyContinue

    $PackMetadata = [ordered]@{
        schema_version = 1
        app_id = $Id
        version = $Version
        required_core = $Entry.required_core
        required_runner = $Entry.required_runner
        required_runtime = $Entry.required_runtime
        package_sha256 = ""
    }
    $PackMetadataPath = Join-Path $StageAppDir "pack_manifest.json"
    $PackMetadata | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 $PackMetadataPath

    if (Test-Path -LiteralPath $PackagePath) {
        Remove-Item -LiteralPath (Assert-InRoot $PackagePath) -Force
    }
    Compress-Archive -Path $StageAppDir -DestinationPath $PackagePath -Force
    Assert-ZipContainsEntry -ZipPath $PackagePath -EntryName "$Id/app.yaml" -Label "$Id app pack app.yaml"
    Assert-ZipContainsEntry -ZipPath $PackagePath -EntryName "$Id/pack_manifest.json" -Label "$Id app pack pack_manifest.json"
    Assert-ZipContainsEntry -ZipPath $PackagePath -EntryName "$Id/README.md" -Label "$Id app pack README"
    Assert-ZipContainsEntry -ZipPath $PackagePath -EntryName "$Id/requirements.txt" -Label "$Id app pack requirements.txt"
    Assert-ZipContainsEntry -ZipPath $PackagePath -EntryName "$Id/$YamlDisplayIcon" -Label "$Id app pack display.icon"
    Assert-ZipContainsEntry -ZipPath $PackagePath -EntryName "$Id/$YamlRunEntry" -Label "$Id app pack run.entry"

    $Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $PackagePath).Hash.ToLowerInvariant()
    $Size = (Get-Item -LiteralPath $PackagePath).Length

    Set-EntryProperty -Entry $Entry -Name "package" -Value $PackageRelative
    Set-EntryProperty -Entry $Entry -Name "sha256" -Value $Hash

    Write-Host "Packaged $Id $Version -> $PackageRelative"
    Write-Host "  sha256: $Hash"
    Write-Host "  size: $Size"
}

if (-not $NoManifestUpdate) {
    $AppManifest | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 $AppManifestPath
    Write-Host "Updated release/app_manifest.json"
}

