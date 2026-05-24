param(
    [string[]]$AppId,
    [switch]$NoManifestUpdate,
    [switch]$ForceRebuild
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

. (Join-Path $PSScriptRoot "utf8_no_bom.ps1")
$AppPackContractHelperPath = Join-Path $PSScriptRoot "lib\app_pack_contract.ps1"
if (-not (Test-Path -LiteralPath $AppPackContractHelperPath -PathType Leaf)) {
    throw "App Pack contract helper is missing: $AppPackContractHelperPath"
}
. $AppPackContractHelperPath

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ReleaseDir = Join-Path $Root "release"
$AppsDir = Join-Path $Root "apps"
$AppManifestPath = Join-Path $ReleaseDir "app_manifest.json"
$AppPacksDir = Join-Path $ReleaseDir "app_packs"
$AppPackCachePath = Join-Path $AppPacksDir ".pack_cache.json"
$StageRoot = Join-Path $ReleaseDir "staging\app_pack_build"
$AppPackCacheSchemaVersion = 2
$AppManifestChanged = $false
$AppPackCacheChanged = $false
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

function Get-FileSha256 {
    param([string]$Path)
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Get-StreamSha256 {
    param([System.IO.Stream]$Stream)
    $Hasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        $HashBytes = $Hasher.ComputeHash($Stream)
        return [System.BitConverter]::ToString($HashBytes).Replace("-", "").ToLowerInvariant()
    } finally {
        $Hasher.Dispose()
    }
}

function Get-TextSha256 {
    param([string]$Text)
    $Bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)
    $Stream = New-Object System.IO.MemoryStream(,$Bytes)
    try {
        return Get-StreamSha256 -Stream $Stream
    } finally {
        $Stream.Dispose()
    }
}

function Get-RelativePathUnder {
    param(
        [string]$BasePath,
        [string]$ChildPath
    )
    $BaseFull = [System.IO.Path]::GetFullPath($BasePath).TrimEnd([char[]]"\/")
    $ChildFull = [System.IO.Path]::GetFullPath($ChildPath)
    $Prefix = $BaseFull + [System.IO.Path]::DirectorySeparatorChar
    if (-not $ChildFull.StartsWith($Prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Path is not under base path. base=$BaseFull child=$ChildFull"
    }
    return $ChildFull.Substring($Prefix.Length).Replace("\", "/")
}

function Test-PackableSourceFile {
    param(
        [string]$AppDir,
        [System.IO.FileInfo]$File
    )
    $Relative = Get-RelativePathUnder -BasePath $AppDir -ChildPath $File.FullName
    $Segments = @($Relative -split "/")
    if ($Segments -contains "__pycache__") {
        return $false
    }
    if ($File.Extension -in @(".pyc", ".pyo")) {
        return $false
    }
    return $true
}

function Get-AppSourceSnapshot {
    param(
        [string]$AppDir,
        [object]$PackMetadata
    )
    $Records = @(
        Get-ChildItem -LiteralPath $AppDir -Recurse -File -Force |
            Where-Object { Test-PackableSourceFile -AppDir $AppDir -File $_ } |
            ForEach-Object {
                $Relative = Get-RelativePathUnder -BasePath $AppDir -ChildPath $_.FullName
                [pscustomobject]@{
                    relative = $Relative
                    size = [int64]$_.Length
                    sha256 = Get-FileSha256 -Path $_.FullName
                }
            } |
            Sort-Object -Property relative
    )
    $MetadataJson = $PackMetadata | ConvertTo-Json -Depth 10 -Compress
    $FingerprintInput = @("pack_metadata=$MetadataJson")
    foreach ($Record in $Records) {
        $FingerprintInput += ("file={0}|size={1}|sha256={2}" -f $Record.relative, $Record.size, $Record.sha256)
    }
    $TotalSize = 0L
    foreach ($Record in $Records) {
        $TotalSize += [int64]$Record.size
    }
    return [pscustomobject]@{
        fingerprint = Get-TextSha256 -Text ($FingerprintInput -join "`n")
        files = $Records
        file_count = @($Records).Count
        total_size = $TotalSize
    }
}

function Read-ZipEntryText {
    param([System.IO.Compression.ZipArchiveEntry]$Entry)
    $Stream = $Entry.Open()
    $Reader = $null
    try {
        $Reader = New-Object System.IO.StreamReader($Stream, [System.Text.Encoding]::UTF8, $true)
        return $Reader.ReadToEnd()
    } finally {
        if ($Reader) {
            $Reader.Dispose()
        } else {
            $Stream.Dispose()
        }
    }
}

function Get-ObjectPropertyString {
    param(
        [object]$Object,
        [string]$Name
    )
    $Property = $Object.PSObject.Properties[$Name]
    if ($null -eq $Property -or $null -eq $Property.Value) {
        return ""
    }
    return [string]$Property.Value
}

function Test-PackManifestMatches {
    param(
        [object]$PackManifest,
        [object]$ExpectedMetadata
    )
    foreach ($Name in @("schema_version", "app_id", "version", "required_core", "required_runner", "required_runtime", "package_sha256")) {
        if ((Get-ObjectPropertyString -Object $PackManifest -Name $Name) -ne (Get-ObjectPropertyString -Object $ExpectedMetadata -Name $Name)) {
            return $false
        }
    }
    return $true
}

function Test-AppPackMatchesSource {
    param(
        [string]$Id,
        [string]$PackagePath,
        [object]$Snapshot,
        [object]$PackMetadata
    )
    if (-not (Test-Path -LiteralPath $PackagePath -PathType Leaf)) {
        return $false
    }

    $Zip = $null
    try {
        $Zip = [System.IO.Compression.ZipFile]::OpenRead($PackagePath)
        $Entries = @{}
        foreach ($Entry in $Zip.Entries) {
            if ([string]::IsNullOrWhiteSpace($Entry.Name)) {
                continue
            }
            $EntryName = $Entry.FullName.Replace("\", "/")
            $Entries[$EntryName] = $Entry
        }

        $ExpectedEntries = @{}
        foreach ($Record in @($Snapshot.files)) {
            $EntryName = "$Id/$($Record.relative)"
            if (-not $Entries.ContainsKey($EntryName)) {
                return $false
            }
            $Stream = $Entries[$EntryName].Open()
            try {
                $EntrySha256 = Get-StreamSha256 -Stream $Stream
            } finally {
                $Stream.Dispose()
            }
            if ($EntrySha256 -ne $Record.sha256) {
                return $false
            }
            $ExpectedEntries[$EntryName] = $true
        }

        $PackManifestEntryName = "$Id/pack_manifest.json"
        if (-not $Entries.ContainsKey($PackManifestEntryName)) {
            return $false
        }
        $ExpectedEntries[$PackManifestEntryName] = $true
        try {
            $ExistingPackManifest = Read-ZipEntryText -Entry $Entries[$PackManifestEntryName] | ConvertFrom-Json
        } catch {
            return $false
        }
        if (-not (Test-PackManifestMatches -PackManifest $ExistingPackManifest -ExpectedMetadata $PackMetadata)) {
            return $false
        }

        foreach ($EntryName in $Entries.Keys) {
            if (-not $ExpectedEntries.ContainsKey($EntryName)) {
                return $false
            }
        }
        return $true
    } catch {
        return $false
    } finally {
        if ($Zip) {
            $Zip.Dispose()
        }
    }
}

function New-EmptyAppPackCache {
    return [pscustomobject]@{
        schema_version = $AppPackCacheSchemaVersion
        apps = [pscustomobject]@{}
    }
}

function Read-AppPackCache {
    if (-not (Test-Path -LiteralPath $AppPackCachePath -PathType Leaf)) {
        return New-EmptyAppPackCache
    }
    try {
        $Cache = Get-Content -Raw -Encoding UTF8 $AppPackCachePath | ConvertFrom-Json
        if ($Cache.schema_version -ne $AppPackCacheSchemaVersion -or $null -eq $Cache.apps) {
            return New-EmptyAppPackCache
        }
        return $Cache
    } catch {
        Write-Host "[WARN] App Pack cache could not be read; rebuilding cache."
        return New-EmptyAppPackCache
    }
}

function Get-AppPackCacheEntry {
    param(
        [object]$Cache,
        [string]$Id
    )
    $Property = $Cache.apps.PSObject.Properties[$Id]
    if ($Property) {
        return $Property.Value
    }
    return $null
}

function Test-AppPackCacheEntryMatches {
    param(
        [object]$Current,
        [object]$Expected
    )
    if ($null -eq $Current) {
        return $false
    }
    foreach ($Name in @("source_fingerprint", "package", "version", "package_sha256", "package_size", "file_count", "source_size")) {
        if ((Get-ObjectPropertyString -Object $Current -Name $Name) -ne (Get-ObjectPropertyString -Object $Expected -Name $Name)) {
            return $false
        }
    }
    return $true
}

function Set-AppPackCacheEntry {
    param(
        [object]$Cache,
        [string]$Id,
        [object]$Entry
    )
    $Property = $Cache.apps.PSObject.Properties[$Id]
    if ($Property) {
        if (-not (Test-AppPackCacheEntryMatches -Current $Property.Value -Expected $Entry)) {
            $Property.Value = $Entry
            $script:AppPackCacheChanged = $true
        }
    } else {
        $Cache.apps | Add-Member -NotePropertyName $Id -NotePropertyValue $Entry
        $script:AppPackCacheChanged = $true
    }
}

function Write-AppPackCache {
    param([object]$Cache)
    Write-JsonUtf8NoBomFile -Path $AppPackCachePath -InputObject $Cache -Depth 20
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
        if ([string]$Property.Value -ne [string]$Value) {
            $Property.Value = $Value
            $script:AppManifestChanged = $true
        }
    } else {
        $Entry | Add-Member -NotePropertyName $Name -NotePropertyValue $Value
        $script:AppManifestChanged = $true
    }
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
New-Item -ItemType Directory -Force -Path $StageRoot | Out-Null
$AppPackCache = Read-AppPackCache

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
    $YamlRequirementsLock = Get-RequirementsLockPathForAppPack -YamlText $YamlText -Label "$Id runtime.requirements_lock"

    if ($KnownAppIds -contains $Id) {
        $Entry = $AppManifest.apps.$Id
    } else {
        $VersionForNewEntry = if ([string]::IsNullOrWhiteSpace($YamlVersion)) { "0.1.0" } else { $YamlVersion }
        $Entry = New-AppManifestEntry -Id $Id -Version $VersionForNewEntry -RequiredRuntime $YamlRequiredRuntime
        $AppManifest.apps | Add-Member -NotePropertyName $Id -NotePropertyValue $Entry
        $AppManifestChanged = $true
        $KnownAppIds += $Id
        Write-Host "[INFO] $Id was found in apps/ but not in app_manifest; adding disabled manifest entry from app.yaml."
    }

    Require-File (Join-Path $AppDir "README.md")
    Require-File (Join-Path $AppDir "requirements.txt")
    Require-AppYamlReferencedFile -AppDir $AppDir -RelativePath $YamlRunEntry -Label "$Id run.entry" | Out-Null
    Require-AppYamlReferencedFile -AppDir $AppDir -RelativePath $YamlDisplayIcon -Label "$Id display.icon" | Out-Null
    if (-not [string]::IsNullOrWhiteSpace($YamlRequirementsLock)) {
        Require-AppYamlReferencedFile -AppDir $AppDir -RelativePath $YamlRequirementsLock -Label "$Id runtime.requirements_lock" | Out-Null
    }
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

    $Snapshot = Get-AppSourceSnapshot -AppDir $AppDir -PackMetadata $PackMetadata
    $CacheEntry = Get-AppPackCacheEntry -Cache $AppPackCache -Id $Id
    $Reused = $false
    $ReuseMode = ""

    if (-not $ForceRebuild -and (Test-Path -LiteralPath $PackagePath -PathType Leaf)) {
        $CachedPackageHash = if ($CacheEntry) { [string](Get-ObjectPropertyString -Object $CacheEntry -Name "package_sha256") } else { "" }
        $CachedPackageSize = if ($CacheEntry) { [int64](Get-ObjectPropertyString -Object $CacheEntry -Name "package_size") } else { 0L }
        $ActualPackageSize = (Get-Item -LiteralPath $PackagePath).Length
        $ActualPackageHash = Get-FileSha256 -Path $PackagePath
        $CacheMatches =
            $CacheEntry -and
            (Get-ObjectPropertyString -Object $CacheEntry -Name "source_fingerprint") -eq $Snapshot.fingerprint -and
            (Get-ObjectPropertyString -Object $CacheEntry -Name "package") -eq $PackageRelative -and
            (Get-ObjectPropertyString -Object $CacheEntry -Name "version") -eq $Version -and
            $CachedPackageHash -eq $ActualPackageHash -and
            $CachedPackageSize -eq $ActualPackageSize

        if ($CacheMatches) {
            $Hash = $ActualPackageHash
            $Size = $ActualPackageSize
            $Reused = $true
            $ReuseMode = "cache"
        } elseif (Test-AppPackMatchesSource -Id $Id -PackagePath $PackagePath -Snapshot $Snapshot -PackMetadata $PackMetadata) {
            $Hash = $ActualPackageHash
            $Size = $ActualPackageSize
            $Reused = $true
            $ReuseMode = "validated"
        }
    }

    if (-not $Reused) {
        Reset-Directory $StageAppDir
        Get-ChildItem -LiteralPath $AppDir -Force |
            Copy-Item -Destination $StageAppDir -Recurse -Force

        Get-ChildItem -Path $StageAppDir -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        Get-ChildItem -Path $StageAppDir -Recurse -File -Include "*.pyc","*.pyo" -ErrorAction SilentlyContinue |
            Remove-Item -Force -ErrorAction SilentlyContinue

        Write-JsonUtf8NoBomFile -Path $PackMetadataPath -InputObject $PackMetadata -Depth 10

        if (Test-Path -LiteralPath $PackagePath) {
            Remove-Item -LiteralPath (Assert-InRoot $PackagePath) -Force
        }
        Compress-Archive -Path $StageAppDir -DestinationPath $PackagePath -Force
        Assert-ZipContainsEntry -ZipPath $PackagePath -EntryName "$Id/app.yaml" -Label "$Id app pack app.yaml"
        Assert-ZipContainsEntry -ZipPath $PackagePath -EntryName "$Id/pack_manifest.json" -Label "$Id app pack pack_manifest.json"
        Assert-ZipContainsEntry -ZipPath $PackagePath -EntryName "$Id/README.md" -Label "$Id app pack README"
        Assert-ZipContainsEntry -ZipPath $PackagePath -EntryName "$Id/requirements.txt" -Label "$Id app pack requirements.txt"
        if (-not [string]::IsNullOrWhiteSpace($YamlRequirementsLock)) {
            Assert-ZipContainsEntry -ZipPath $PackagePath -EntryName "$Id/$YamlRequirementsLock" -Label "$Id app pack runtime.requirements_lock"
        }
        Assert-ZipContainsEntry -ZipPath $PackagePath -EntryName "$Id/$YamlDisplayIcon" -Label "$Id app pack display.icon"
        Assert-ZipContainsEntry -ZipPath $PackagePath -EntryName "$Id/$YamlRunEntry" -Label "$Id app pack run.entry"

        $Hash = Get-FileSha256 -Path $PackagePath
        $Size = (Get-Item -LiteralPath $PackagePath).Length
    }

    $Size = (Get-Item -LiteralPath $PackagePath).Length

    Set-EntryProperty -Entry $Entry -Name "package" -Value $PackageRelative
    Set-EntryProperty -Entry $Entry -Name "sha256" -Value $Hash

    Set-AppPackCacheEntry -Cache $AppPackCache -Id $Id -Entry ([pscustomobject]@{
        source_fingerprint = $Snapshot.fingerprint
        package = $PackageRelative
        version = $Version
        package_sha256 = $Hash
        package_size = [int64]$Size
        file_count = [int]$Snapshot.file_count
        source_size = [int64]$Snapshot.total_size
    })

    if ($Reused) {
        Write-Host "Reused $Id $Version -> $PackageRelative ($ReuseMode)"
    } else {
        Write-Host "Packaged $Id $Version -> $PackageRelative"
    }
    Write-Host "  sha256: $Hash"
    Write-Host "  size: $Size"
}

if ($AppPackCacheChanged) {
    Write-AppPackCache -Cache $AppPackCache
} else {
    Write-Host "[SKIP] App Pack cache unchanged"
}

if (-not $NoManifestUpdate) {
    if ($AppManifestChanged) {
        Write-JsonUtf8NoBomFile -Path $AppManifestPath -InputObject $AppManifest -Depth 20
        Write-Host "Updated release/app_manifest.json"
    } else {
        Write-Host "[SKIP] release/app_manifest.json unchanged"
    }
}

