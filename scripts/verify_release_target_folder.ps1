param(
    [string]$TargetDir,
    [string]$Version,
    [string]$Tag,
    [switch]$Json
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ReleaseDir = Join-Path $Root "release"
$ReleaseTargetsRoot = Join-Path $ReleaseDir "github_release_targets"
$SourceManifestPath = Join-Path $ReleaseDir "manifest.json"
$TagWasProvided = $PSBoundParameters.ContainsKey("Tag")

function Write-Line {
    param([string]$Message)
    if (-not $Json) {
        Write-Host $Message
    }
}

function Get-PropertyValue {
    param(
        [object]$Object,
        [string]$Name
    )

    if ($null -eq $Object) {
        return $null
    }
    $Property = $Object.PSObject.Properties | Where-Object { $_.Name -eq $Name } | Select-Object -First 1
    if ($null -eq $Property) {
        return $null
    }
    return $Property.Value
}

function Convert-ToTargetFolderName {
    param([string]$Value)

    $Safe = ($Value.ToCharArray() | ForEach-Object {
        $Char = [char]$_
        if ([char]::IsLetterOrDigit($Char) -or $Char -eq "." -or $Char -eq "-" -or $Char -eq "_") {
            [string]$Char
        } else {
            "_"
        }
    }) -join ""
    if ([string]::IsNullOrWhiteSpace($Safe)) {
        return "unresolved"
    }
    return $Safe
}

function Add-Check {
    param(
        [System.Collections.ArrayList]$Checks,
        [string]$Id,
        [string]$Status,
        [string]$Message,
        [object]$Details = $null
    )

    [void]$Checks.Add([ordered]@{
        id = $Id
        status = $Status
        message = $Message
        details = $Details
    })
    if ($Status -eq "pass") {
        Write-Line "[OK] $Message"
    } elseif ($Status -eq "warning") {
        Write-Line "[WARN] $Message"
    } else {
        Write-Line "[NG] $Message"
    }
}

function Resolve-DefaultVersionAndTag {
    if ([string]::IsNullOrWhiteSpace($Version) -or [string]::IsNullOrWhiteSpace($Tag)) {
        if (-not (Test-Path -LiteralPath $SourceManifestPath -PathType Leaf)) {
            throw "release/manifest.json was not found and version/tag were not provided."
        }
        $SourceManifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $SourceManifestPath | ConvertFrom-Json
        $ManifestVersion = [string](Get-PropertyValue -Object (Get-PropertyValue -Object $SourceManifest -Name "toolhub") -Name "version")
        if ([string]::IsNullOrWhiteSpace($Version)) {
            $script:Version = $ManifestVersion
        }
    }
    if ([string]::IsNullOrWhiteSpace($Tag) -and -not [string]::IsNullOrWhiteSpace($Version)) {
        $script:Tag = "v$Version"
    }
}

function Resolve-TargetDir {
    Resolve-DefaultVersionAndTag
    if ([string]::IsNullOrWhiteSpace($TargetDir)) {
        if ([string]::IsNullOrWhiteSpace($Tag)) {
            throw "TargetDir could not be resolved. Pass -TargetDir or provide -Version/-Tag."
        }
        return [System.IO.Path]::GetFullPath((Join-Path $ReleaseTargetsRoot (Convert-ToTargetFolderName -Value $Tag)))
    }
    if ([System.IO.Path]::IsPathRooted($TargetDir)) {
        return [System.IO.Path]::GetFullPath($TargetDir)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $Root $TargetDir))
}

function Assert-ChildPath {
    param(
        [string]$Path,
        [string]$BasePath
    )

    $FullPath = [System.IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
    $FullBase = [System.IO.Path]::GetFullPath($BasePath).TrimEnd('\', '/')
    if (-not $FullPath.StartsWith($FullBase + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "TargetDir must be under $FullBase. actual=$FullPath"
    }
}

function Read-JsonFile {
    param([string]$Path)
    return Get-Content -Raw -Encoding UTF8 -LiteralPath $Path | ConvertFrom-Json
}

function Read-ChecksumMap {
    param([string]$Path)

    $Map = @{}
    foreach ($Line in @(Get-Content -Encoding UTF8 -LiteralPath $Path)) {
        $Trimmed = $Line.Trim()
        if ([string]::IsNullOrWhiteSpace($Trimmed)) {
            continue
        }
        if ($Trimmed -notmatch "^([0-9a-fA-F]{64})\s+(.+)$") {
            throw "Invalid checksum row: $Line"
        }
        $Map[$Matches[2].Trim()] = $Matches[1].ToLowerInvariant()
    }
    return $Map
}

function New-AssetRecord {
    param(
        [string]$Name,
        [string]$Path
    )

    $Exists = Test-Path -LiteralPath $Path -PathType Leaf
    $Sha256 = $null
    $Size = $null
    if ($Exists) {
        $Sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
        $Size = (Get-Item -LiteralPath $Path).Length
    }
    return [ordered]@{
        name = $Name
        path = $Path
        exists = $Exists
        sha256 = $Sha256
        size = $Size
    }
}

$Checks = New-Object System.Collections.ArrayList
$Report = [ordered]@{
    generated_at = (Get-Date).ToString("s")
    project_root = $Root
    target_dir = $null
    expected_version = $Version
    tag = $Tag
    target_commitish = $null
    upload_assets = @()
    checks = @()
    ok = $false
}

try {
    $ResolvedTargetDir = Resolve-TargetDir
    Assert-ChildPath -Path $ResolvedTargetDir -BasePath $ReleaseTargetsRoot
    $Report.target_dir = $ResolvedTargetDir
    $Report.expected_version = $Version
    $Report.tag = $Tag

    if (Test-Path -LiteralPath $ResolvedTargetDir -PathType Container) {
        Add-Check -Checks $Checks -Id "target_dir_exists" -Status "pass" -Message "release target folder exists: $ResolvedTargetDir"
    } else {
        Add-Check -Checks $Checks -Id "target_dir_exists" -Status "fail" -Message "release target folder is missing: $ResolvedTargetDir"
        throw "Release target folder is missing."
    }

    $TargetManifestPath = Join-Path $ResolvedTargetDir "manifest.json"
    $TargetAppManifestPath = Join-Path $ResolvedTargetDir "app_manifest.json"
    $ChecksumsPath = Join-Path $ResolvedTargetDir "checksums.sha256.txt"
    $ReleaseTargetManifestPath = Join-Path $ResolvedTargetDir "release_target_manifest.json"

    foreach ($Required in @($TargetManifestPath, $TargetAppManifestPath, $ChecksumsPath, $ReleaseTargetManifestPath)) {
        if (Test-Path -LiteralPath $Required -PathType Leaf) {
            Add-Check -Checks $Checks -Id ("file_exists_" + [System.IO.Path]::GetFileNameWithoutExtension($Required)) -Status "pass" -Message "required file exists: $Required"
        } else {
            Add-Check -Checks $Checks -Id ("file_exists_" + [System.IO.Path]::GetFileNameWithoutExtension($Required)) -Status "fail" -Message "required file is missing: $Required"
        }
    }

    $Manifest = Read-JsonFile -Path $TargetManifestPath
    Add-Check -Checks $Checks -Id "manifest_json_valid" -Status "pass" -Message "target manifest JSON is valid"
    $AppManifest = Read-JsonFile -Path $TargetAppManifestPath
    if ([int](Get-PropertyValue -Object $AppManifest -Name "schema_version") -eq 1) {
        Add-Check -Checks $Checks -Id "app_manifest_json_valid" -Status "pass" -Message "target app manifest JSON is valid"
    } else {
        Add-Check -Checks $Checks -Id "app_manifest_json_valid" -Status "fail" -Message "target app manifest schema_version is not 1"
    }
    $ReleaseTargetManifest = Read-JsonFile -Path $ReleaseTargetManifestPath
    Add-Check -Checks $Checks -Id "release_target_manifest_json_valid" -Status "pass" -Message "release target manifest JSON is valid"
    $ManifestTag = [string](Get-PropertyValue -Object $ReleaseTargetManifest -Name "tag")
    if (-not [string]::IsNullOrWhiteSpace($ManifestTag)) {
        $Report.tag = $ManifestTag
        if ($TagWasProvided -and $ManifestTag -ne $Tag) {
            Add-Check -Checks $Checks -Id "release_target_tag" -Status "fail" -Message "release_target_manifest tag $ManifestTag does not match expected $Tag"
        } else {
            Add-Check -Checks $Checks -Id "release_target_tag" -Status "pass" -Message "release_target_manifest tag is $ManifestTag"
        }
    }
    $ManifestTargetCommitish = [string](Get-PropertyValue -Object $ReleaseTargetManifest -Name "target_commitish")
    if (-not [string]::IsNullOrWhiteSpace($ManifestTargetCommitish)) {
        $Report.target_commitish = $ManifestTargetCommitish
        Add-Check -Checks $Checks -Id "release_target_commitish" -Status "pass" -Message "release_target_manifest target commitish is $ManifestTargetCommitish"
    }

    $Toolhub = Get-PropertyValue -Object $Manifest -Name "toolhub"
    $RemoteVersion = [string](Get-PropertyValue -Object $Toolhub -Name "version")
    if ([string]::IsNullOrWhiteSpace($Version) -or $RemoteVersion -eq $Version) {
        Add-Check -Checks $Checks -Id "toolhub_version" -Status "pass" -Message "target manifest version is $RemoteVersion"
    } else {
        Add-Check -Checks $Checks -Id "toolhub_version" -Status "fail" -Message "target manifest version $RemoteVersion does not match expected $Version"
    }

    $Installer = Get-PropertyValue -Object $Toolhub -Name "installer"
    $InstallerFile = [string](Get-PropertyValue -Object $Installer -Name "file")
    $InstallerPath = Join-Path $ResolvedTargetDir $InstallerFile
    $UploadAssetNames = @($InstallerFile, "manifest.json", "app_manifest.json", "checksums.sha256.txt")
    $Assets = @()
    foreach ($Name in $UploadAssetNames) {
        $Assets += New-AssetRecord -Name $Name -Path (Join-Path $ResolvedTargetDir $Name)
    }
    $Report.upload_assets = $Assets

    foreach ($Asset in $Assets) {
        if ($Asset.exists) {
            Add-Check -Checks $Checks -Id "asset_exists_$($Asset.name)" -Status "pass" -Message "upload asset exists: $($Asset.name)"
        } else {
            Add-Check -Checks $Checks -Id "asset_exists_$($Asset.name)" -Status "fail" -Message "upload asset is missing: $($Asset.name)"
        }
    }

    $ManifestInstallerSha256 = ([string](Get-PropertyValue -Object $Installer -Name "sha256")).Trim().ToLowerInvariant()
    $ManifestInstallerSize = Get-PropertyValue -Object $Installer -Name "size"
    $InstallerAsset = $Assets | Where-Object { $_.name -eq $InstallerFile } | Select-Object -First 1
    if ($InstallerAsset.sha256 -eq $ManifestInstallerSha256) {
        Add-Check -Checks $Checks -Id "installer_sha256" -Status "pass" -Message "installer sha256 matches target manifest"
    } else {
        Add-Check -Checks $Checks -Id "installer_sha256" -Status "fail" -Message "installer sha256 does not match target manifest"
    }
    if ([int64]$InstallerAsset.size -eq [int64]$ManifestInstallerSize) {
        Add-Check -Checks $Checks -Id "installer_size" -Status "pass" -Message "installer size matches target manifest"
    } else {
        Add-Check -Checks $Checks -Id "installer_size" -Status "fail" -Message "installer size does not match target manifest"
    }

    $ChecksumMap = Read-ChecksumMap -Path $ChecksumsPath
    foreach ($Name in @($InstallerFile, "manifest.json", "app_manifest.json")) {
        $Asset = $Assets | Where-Object { $_.name -eq $Name } | Select-Object -First 1
        $ExpectedHash = $ChecksumMap[$Name]
        if ($ExpectedHash -and $ExpectedHash -eq $Asset.sha256) {
            Add-Check -Checks $Checks -Id "checksums_file_$Name" -Status "pass" -Message "checksums.sha256.txt matches $Name"
        } else {
            Add-Check -Checks $Checks -Id "checksums_file_$Name" -Status "fail" -Message "checksums.sha256.txt does not match $Name"
        }
    }

    $ReleaseTargetAssets = @(Get-PropertyValue -Object $ReleaseTargetManifest -Name "upload_assets")
    foreach ($Asset in $Assets) {
        $Entry = $ReleaseTargetAssets | Where-Object { [string](Get-PropertyValue -Object $_ -Name "name") -eq $Asset.name } | Select-Object -First 1
        if ($null -eq $Entry) {
            Add-Check -Checks $Checks -Id "release_target_manifest_$($Asset.name)" -Status "fail" -Message "release_target_manifest.json is missing $($Asset.name)"
            continue
        }
        $EntrySha256 = ([string](Get-PropertyValue -Object $Entry -Name "sha256")).Trim().ToLowerInvariant()
        $EntrySize = Get-PropertyValue -Object $Entry -Name "size"
        if ($EntrySha256 -eq $Asset.sha256 -and [int64]$EntrySize -eq [int64]$Asset.size) {
            Add-Check -Checks $Checks -Id "release_target_manifest_$($Asset.name)" -Status "pass" -Message "release_target_manifest.json matches $($Asset.name)"
        } else {
            Add-Check -Checks $Checks -Id "release_target_manifest_$($Asset.name)" -Status "fail" -Message "release_target_manifest.json does not match $($Asset.name)"
        }
    }
} catch {
    Add-Check -Checks $Checks -Id "verification_exception" -Status "fail" -Message $_.Exception.Message
}

$Report.checks = @($Checks)
$Failed = @($Checks | Where-Object { $_.status -eq "fail" }).Count -gt 0
$Report.ok = -not $Failed

if ($Json) {
    $Report | ConvertTo-Json -Depth 12
} else {
    Write-Line ""
    if ($Report.ok) {
        Write-Line "Release target folder verification completed."
    } else {
        Write-Line "Release target folder verification failed."
    }
}

if ($Failed) {
    exit 1
}
exit 0
