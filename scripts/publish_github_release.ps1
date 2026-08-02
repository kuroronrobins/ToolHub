param(
    [string]$Version,
    [string]$Owner,
    [string]$Repo,
    [string]$Remote = "origin",
    [string]$Tag,
    [string]$TargetCommitish,
    [string]$ReleaseTargetDir,
    [string]$RemoteVerifyManifestUrl,
    [string]$ReleaseTitle,
    [string]$ReleaseNotes,
    [string]$ReleaseNotesFile,
    [switch]$Draft,
    [switch]$Prerelease,
    [switch]$SkipBuild,
    [switch]$SkipInstall,
    [switch]$SkipVerify,
    [switch]$SkipTag,
    [switch]$AllowDirty,
    [switch]$AllowExistingRelease,
    [switch]$UpdateManifestInstallerUrl,
    [switch]$SkipRemoteVerify,
    [switch]$DownloadInstallerForRemoteVerify,
    [switch]$SignInstaller,
    [switch]$RequireInstallerSignature,
    [string]$CodeSignCertificateThumbprint,
    [string]$CodeSignCertificateSubject,
    [string]$CodeSignTimestampUrl,
    [string]$SignToolPath,
    [string[]]$SignToolExtraArgs = @(),
    [switch]$PrepareTargetOnly,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

. (Join-Path $PSScriptRoot "utf8_no_bom.ps1")

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ReleaseDir = Join-Path $Root "release"
$ManifestPath = Join-Path $ReleaseDir "manifest.json"
$AppManifestPath = Join-Path $ReleaseDir "app_manifest.json"
$DistInstallerDir = Join-Path $ReleaseDir "dist_installer"
$ReleaseTargetsRoot = Join-Path $ReleaseDir "github_release_targets"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "== $Message =="
}

function Fail {
    param([string]$Message)
    throw $Message
}

function Get-JsonProperty {
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

function Set-JsonProperty {
    param(
        [object]$Object,
        [string]$Name,
        [object]$Value
    )

    $Property = $Object.PSObject.Properties | Where-Object { $_.Name -eq $Name } | Select-Object -First 1
    if ($null -eq $Property) {
        $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value
    } else {
        $Property.Value = $Value
    }
}

function Get-FullPath {
    param(
        [string]$Path,
        [string]$BasePath = $Root
    )

    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $BasePath $Path))
}

function Assert-ChildPath {
    param(
        [string]$Path,
        [string]$BasePath,
        [string]$Label
    )

    $FullPath = [System.IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
    $FullBase = [System.IO.Path]::GetFullPath($BasePath).TrimEnd('\', '/')
    if ($FullPath.Equals($FullBase, [System.StringComparison]::OrdinalIgnoreCase)) {
        Fail "$Label must be a child of $FullBase, not the root folder itself."
    }
    if (-not $FullPath.StartsWith($FullBase + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
        Fail "$Label must be under $FullBase. actual=$FullPath"
    }
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

function Read-JsonFile {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Fail "JSON file not found: $Path"
    }
    return Get-Content -Raw -Encoding UTF8 $Path | ConvertFrom-Json
}

function Resolve-GitHubRepoFromRemote {
    param([string]$RemoteName)

    $Url = (& git remote get-url $RemoteName 2>$null)
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($Url)) {
        return $null
    }
    $Url = [string]$Url
    if ($Url -match "^https://github\.com/([^/]+)/([^/]+?)(\.git)?$") {
        return @{ Owner = $Matches[1]; Repo = $Matches[2] }
    }
    if ($Url -match "^git@github\.com:([^/]+)/([^/]+?)(\.git)?$") {
        return @{ Owner = $Matches[1]; Repo = $Matches[2] }
    }
    return $null
}

function Get-CargoPackageVersion {
    param([string]$Path)

    $InPackage = $false
    foreach ($Line in @(Get-Content -Encoding UTF8 $Path)) {
        if ($Line -match "^\s*\[package\]\s*$") {
            $InPackage = $true
            continue
        }
        if ($InPackage -and $Line -match "^\s*\[") {
            break
        }
        if ($InPackage -and $Line -match '^\s*version\s*=\s*"([^"]+)"') {
            return $Matches[1]
        }
    }
    return ""
}

function Invoke-External {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )

    Write-Host ("> " + $FilePath + " " + ($Arguments -join " "))
    if ($DryRun) {
        return
    }
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        Fail "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

function Assert-VersionMatch {
    param(
        [string]$Label,
        [string]$Actual,
        [string]$Expected
    )

    if ([string]::IsNullOrWhiteSpace($Actual)) {
        Fail "$Label version is missing."
    }
    if ($Actual -ne $Expected) {
        Fail "$Label version mismatch. expected=$Expected actual=$Actual"
    }
    Write-Host "[OK] $Label version: $Actual"
}

function Assert-CleanWorktree {
    $Status = @(& git status --porcelain)
    if ($LASTEXITCODE -ne 0) {
        Fail "git status failed."
    }
    if ($Status.Count -gt 0) {
        Write-Host "[WARN] Working tree has uncommitted changes:"
        $Status | ForEach-Object { Write-Host "  $_" }
        if (-not $AllowDirty) {
            Fail "Refusing to publish from a dirty working tree. Commit/stash changes or pass -AllowDirty deliberately."
        }
    } else {
        Write-Host "[OK] Working tree is clean."
    }
}

function Resolve-TargetCommitish {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        $Value = "HEAD"
    }
    $Commit = (& git rev-parse "$Value^{commit}" 2>$null)
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($Commit)) {
        Fail "Could not resolve release target commitish: $Value"
    }
    return $Commit.Trim()
}

function Assert-InstallerMatchesManifest {
    param(
        [object]$Manifest,
        [string]$ExpectedVersion
    )

    $Toolhub = Get-JsonProperty -Object $Manifest -Name "toolhub"
    $Installer = Get-JsonProperty -Object $Toolhub -Name "installer"
    $InstallerFile = [string](Get-JsonProperty -Object $Installer -Name "file")
    if ([string]::IsNullOrWhiteSpace($InstallerFile)) {
        Fail "release/manifest.json toolhub.installer.file is missing."
    }
    if ($InstallerFile -notmatch "^ToolHub_Setup_$([regex]::Escape($ExpectedVersion))\.(exe|msi)$") {
        Fail "Installer file name does not match release version. expected ToolHub_Setup_$ExpectedVersion.exe/.msi actual=$InstallerFile"
    }
    $InstallerPath = Join-Path $DistInstallerDir $InstallerFile
    if (-not (Test-Path -LiteralPath $InstallerPath -PathType Leaf)) {
        Fail "Installer artifact not found: $InstallerPath"
    }

    $ExpectedSha256 = ([string](Get-JsonProperty -Object $Installer -Name "sha256")).Trim().ToLowerInvariant()
    $ExpectedSize = Get-JsonProperty -Object $Installer -Name "size"
    $ActualSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $InstallerPath).Hash.ToLowerInvariant()
    $ActualSize = (Get-Item -LiteralPath $InstallerPath).Length

    if ($ExpectedSha256 -ne $ActualSha256) {
        Fail "Installer sha256 mismatch. expected=$ExpectedSha256 actual=$ActualSha256"
    }
    if ([int64]$ExpectedSize -ne $ActualSize) {
        Fail "Installer size mismatch. expected=$ExpectedSize actual=$ActualSize"
    }

    Write-Host "[OK] Installer artifact matches release manifest: $InstallerFile"
    return @{
        File = $InstallerFile
        Path = $InstallerPath
        Sha256 = $ActualSha256
        Size = $ActualSize
    }
}

function Assert-InstallerSignature {
    param([string]$Path)

    $Signature = Get-AuthenticodeSignature -LiteralPath $Path
    if ($Signature.Status -ne "Valid") {
        Fail "Installer Authenticode signature is not valid. status=$($Signature.Status) path=$Path"
    }
    $Subject = if ($Signature.SignerCertificate) { $Signature.SignerCertificate.Subject } else { "unknown signer" }
    Write-Host "[OK] Installer Authenticode signature is valid: $Subject"
}

function Initialize-ReleaseTargetDirectory {
    param(
        [string]$TargetDir
    )

    Assert-ChildPath -Path $TargetDir -BasePath $ReleaseTargetsRoot -Label "Release target directory"
    if ($DryRun) {
        Write-Host "[DRY RUN] Would prepare release target folder: $TargetDir"
        return
    }
    New-Item -ItemType Directory -Force -Path $ReleaseTargetsRoot | Out-Null
    $TargetsRootItem = Get-Item -LiteralPath $ReleaseTargetsRoot -Force
    if (($TargetsRootItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        Fail "Release targets root must not be a reparse point: $ReleaseTargetsRoot"
    }
    if (Test-Path -LiteralPath $TargetDir) {
        $TargetItem = Get-Item -LiteralPath $TargetDir -Force
        if (($TargetItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            Fail "Release target directory must not be a reparse point: $TargetDir"
        }
        try {
            Remove-Item -LiteralPath $TargetDir -Recurse -Force -ErrorAction Stop
        } catch {
            Get-ChildItem -LiteralPath $TargetDir -Recurse -Force -File | ForEach-Object {
                [System.IO.File]::Delete($_.FullName)
            }
            Get-ChildItem -LiteralPath $TargetDir -Recurse -Force -Directory |
                Sort-Object FullName -Descending |
                ForEach-Object { [System.IO.Directory]::Delete($_.FullName, $false) }
            [System.IO.Directory]::Delete($TargetDir, $false)
        }
    }
    New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null
    Write-Host "[OK] Prepared release target folder: $TargetDir"
}

function Copy-ReleaseTargetAsset {
    param(
        [string]$SourcePath,
        [string]$TargetDir,
        [string]$Name
    )

    if (-not (Test-Path -LiteralPath $SourcePath -PathType Leaf)) {
        Fail "Release target source asset missing: $SourcePath"
    }
    $TargetPath = Join-Path $TargetDir $Name
    if ($DryRun) {
        Write-Host "[DRY RUN] Would stage asset: $Name"
        Write-Host "          source: $SourcePath"
        Write-Host "          target: $TargetPath"
        return $TargetPath
    }
    Copy-Item -LiteralPath $SourcePath -Destination $TargetPath -Force
    Write-Host "[OK] Staged asset: $Name"
    return $TargetPath
}

function Get-EnabledAppPackAssets {
    param([object]$AppManifest)

    $Apps = Get-JsonProperty -Object $AppManifest -Name "apps"
    if ($null -eq $Apps) {
        Fail "release/app_manifest.json does not contain an apps object."
    }

    $Assets = @()
    foreach ($Property in $Apps.PSObject.Properties) {
        $Entry = $Property.Value
        $Enabled = Get-JsonProperty -Object $Entry -Name "enabled"
        if ($Enabled -ne $true) {
            continue
        }
        $Package = [string](Get-JsonProperty -Object $Entry -Name "package")
        if ([string]::IsNullOrWhiteSpace($Package)) {
            Fail "Enabled app $($Property.Name) does not define package."
        }
        $SourcePath = Join-Path $ReleaseDir $Package
        $Name = [System.IO.Path]::GetFileName($Package.Replace("/", "\"))
        if ([string]::IsNullOrWhiteSpace($Name)) {
            Fail "Enabled app $($Property.Name) has an invalid package path: $Package"
        }
        $Assets += [ordered]@{
            AppId = $Property.Name
            Name = $Name
            SourcePath = $SourcePath
            ExpectedSha256 = ([string](Get-JsonProperty -Object $Entry -Name "sha256")).Trim().ToLowerInvariant()
        }
    }
    return @($Assets)
}

function Write-ChecksumsFile {
    param(
        [object[]]$AssetInfos,
        [string]$TargetDir
    )

    $ChecksumsPath = Join-Path $TargetDir "checksums.sha256.txt"
    $Rows = @()
    foreach ($Item in $AssetInfos) {
        $HashPath = $Item.Path
        if ($DryRun -and -not (Test-Path -LiteralPath $HashPath -PathType Leaf) -and $Item.SourcePath -and (Test-Path -LiteralPath $Item.SourcePath -PathType Leaf)) {
            $HashPath = $Item.SourcePath
        }
        if (-not (Test-Path -LiteralPath $HashPath -PathType Leaf)) {
            Fail "Checksum target missing: $($Item.Path)"
        }
        $Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $HashPath).Hash.ToLowerInvariant()
        $Rows += "$Hash  $($Item.Name)"
    }
    if ($DryRun) {
        Write-Host "[DRY RUN] Would write checksums: $ChecksumsPath"
        return $ChecksumsPath
    }
    Write-Utf8NoBomFile -Path $ChecksumsPath -Content (($Rows -join "`n") + "`n")
    Write-Host "[OK] Wrote checksums: $ChecksumsPath"
    return $ChecksumsPath
}

function Write-ReleaseTargetManifest {
    param(
        [string]$TargetDir,
        [string]$Repository,
        [string]$Version,
        [string]$Tag,
        [string]$TargetCommitish,
        [string]$ReleaseUrl,
        [string]$LatestManifestUrl,
        [string]$TagManifestUrl,
        [string]$RemoteVerifyManifestUrl,
        [object[]]$AssetInfos
    )

    $TargetManifestPath = Join-Path $TargetDir "release_target_manifest.json"
    $Assets = @()
    foreach ($Item in $AssetInfos) {
        $Size = $null
        $Hash = $null
        $HashPath = $Item.Path
        if ($DryRun -and -not (Test-Path -LiteralPath $HashPath -PathType Leaf) -and $Item.SourcePath -and (Test-Path -LiteralPath $Item.SourcePath -PathType Leaf)) {
            $HashPath = $Item.SourcePath
        }
        if (Test-Path -LiteralPath $HashPath -PathType Leaf) {
            $Size = (Get-Item -LiteralPath $HashPath).Length
            $Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $HashPath).Hash.ToLowerInvariant()
        }
        $Assets += [ordered]@{
            name = $Item.Name
            path = $Item.Path
            source_path = $Item.SourcePath
            sha256 = $Hash
            size = $Size
            upload = $true
        }
    }
    $Manifest = [ordered]@{
        schema_version = 1
        generated_at = (Get-Date).ToUniversalTime().ToString("o")
        repository = $Repository
        version = $Version
        tag = $Tag
        target_commitish = $TargetCommitish
        release_url = $ReleaseUrl
        latest_manifest_url = $LatestManifestUrl
        tag_manifest_url = $TagManifestUrl
        remote_verify_manifest_url = $RemoteVerifyManifestUrl
        release_target_dir = $TargetDir
        upload_assets = $Assets
        note = "Only upload_assets are passed to gh release upload/create. This file is for local human confirmation and is not uploaded by default."
    }
    if ($DryRun) {
        Write-Host "[DRY RUN] Would write release target manifest: $TargetManifestPath"
        return $TargetManifestPath
    }
    Write-JsonUtf8NoBomFile -Path $TargetManifestPath -InputObject $Manifest -Depth 12
    Write-Host "[OK] Wrote release target manifest: $TargetManifestPath"
    return $TargetManifestPath
}

function Invoke-GhReleasePublish {
    param(
        [string]$Repository,
        [string]$TagName,
        [string]$TargetCommitish,
        [string]$Title,
        [string]$NotesText,
        [string[]]$AssetPaths
    )

    if (-not (Get-Command "gh" -ErrorAction SilentlyContinue)) {
        Fail "GitHub CLI 'gh' was not found. Install gh or publish through a separate GitHub API fallback."
    }

    $Existing = $false
    if (-not $DryRun) {
        $PreviousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            & gh release view $TagName --repo $Repository 1>$null 2>$null
            $Existing = ($LASTEXITCODE -eq 0)
        } finally {
            $ErrorActionPreference = $PreviousErrorActionPreference
        }
    } else {
        Write-Host "> gh release view $TagName --repo $Repository"
    }

    $CommonFlags = @()
    if ($Draft) { $CommonFlags += "--draft" }
    if ($Prerelease) { $CommonFlags += "--prerelease" }

    if ($Existing) {
        if (-not $AllowExistingRelease) {
            Fail "GitHub Release already exists: $TagName. Pass -AllowExistingRelease to edit/upload with --clobber."
        }
        Invoke-External "gh" (@("release", "edit", $TagName, "--repo", $Repository, "--title", $Title, "--notes", $NotesText) + $CommonFlags)
        Invoke-External "gh" (@("release", "upload", $TagName, "--repo", $Repository, "--clobber") + $AssetPaths)
    } else {
        Invoke-External "gh" (@("release", "create", $TagName, "--repo", $Repository, "--target", $TargetCommitish, "--title", $Title, "--notes", $NotesText) + $CommonFlags + $AssetPaths)
    }
}

Write-Step "Resolve repository and release version"
$RepoInfo = Resolve-GitHubRepoFromRemote -RemoteName $Remote
if ([string]::IsNullOrWhiteSpace($Owner) -and $RepoInfo) { $Owner = $RepoInfo.Owner }
if ([string]::IsNullOrWhiteSpace($Repo) -and $RepoInfo) { $Repo = $RepoInfo.Repo }
if ([string]::IsNullOrWhiteSpace($Owner) -or [string]::IsNullOrWhiteSpace($Repo)) {
    Fail "Could not determine GitHub owner/repo. Pass -Owner and -Repo explicitly."
}
$Repository = "$Owner/$Repo"

$Manifest = Read-JsonFile $ManifestPath
$AppManifest = Read-JsonFile $AppManifestPath
$ManifestToolhub = Get-JsonProperty -Object $Manifest -Name "toolhub"
$ManifestCore = Get-JsonProperty -Object $Manifest -Name "core"
$ManifestVersion = [string](Get-JsonProperty -Object $ManifestToolhub -Name "version")
if ([string]::IsNullOrWhiteSpace($Version)) {
    $Version = $ManifestVersion
}
if ([string]::IsNullOrWhiteSpace($Version)) {
    Fail "Release version is missing. Pass -Version or set release/manifest.json toolhub.version."
}
if ([string]::IsNullOrWhiteSpace($Tag)) {
    $Tag = "v$Version"
}
if ([string]::IsNullOrWhiteSpace($ReleaseTargetDir)) {
    $ReleaseTargetDir = Join-Path $ReleaseTargetsRoot (Convert-ToTargetFolderName -Value $Tag)
} else {
    $ReleaseTargetDir = Get-FullPath -Path $ReleaseTargetDir
}
Assert-ChildPath -Path $ReleaseTargetDir -BasePath $ReleaseTargetsRoot -Label "Release target directory"
if ([string]::IsNullOrWhiteSpace($ReleaseTitle)) {
    $ReleaseTitle = "ToolHub $Version"
}
if ([string]::IsNullOrWhiteSpace($ReleaseNotes)) {
    if (-not [string]::IsNullOrWhiteSpace($ReleaseNotesFile)) {
        $ReleaseNotes = Get-Content -Raw -Encoding UTF8 $ReleaseNotesFile
    } else {
        $ReleaseNotes = "ToolHub $Version release."
    }
}

Write-Host "Repository: $Repository"
Write-Host "Version: $Version"
Write-Host "Tag: $Tag"
Write-Host "Release target folder: $ReleaseTargetDir"

if ($SkipBuild -and $SignInstaller -and -not $DryRun) {
    Fail "-SignInstaller cannot be applied when -SkipBuild is used. Run scripts/package_installer.ps1 -SignInstaller first, or omit -SkipBuild."
}

Assert-CleanWorktree
$ResolvedTargetCommitish = Resolve-TargetCommitish -Value $TargetCommitish
Write-Host "Target commitish: $ResolvedTargetCommitish"

Write-Step "Version consistency"
$Package = Read-JsonFile (Join-Path $Root "launcher\package.json")
$Tauri = Read-JsonFile (Join-Path $Root "launcher\src-tauri\tauri.conf.json")
$CargoVersion = Get-CargoPackageVersion -Path (Join-Path $Root "launcher\src-tauri\Cargo.toml")
Assert-VersionMatch -Label "launcher/package.json" -Actual ([string]$Package.version) -Expected $Version
Assert-VersionMatch -Label "launcher/src-tauri/Cargo.toml" -Actual $CargoVersion -Expected $Version
Assert-VersionMatch -Label "launcher/src-tauri/tauri.conf.json" -Actual ([string]$Tauri.version) -Expected $Version
Assert-VersionMatch -Label "release/manifest.json toolhub" -Actual $ManifestVersion -Expected $Version
Assert-VersionMatch -Label "release/manifest.json core" -Actual ([string](Get-JsonProperty -Object $ManifestCore -Name "version")) -Expected $Version

if (-not $SkipBuild) {
    Write-Step "Build release artifacts"
    $BuildArgs = @("-RequireRuntime", "-SkipVerify")
    if ($SkipInstall) { $BuildArgs += "-SkipInstall" }
    if ($SignInstaller) { $BuildArgs += "-SignInstaller" }
    if ($RequireInstallerSignature) { $BuildArgs += "-RequireInstallerSignature" }
    if (-not [string]::IsNullOrWhiteSpace($CodeSignCertificateThumbprint)) {
        $BuildArgs += @("-CodeSignCertificateThumbprint", $CodeSignCertificateThumbprint)
    }
    if (-not [string]::IsNullOrWhiteSpace($CodeSignCertificateSubject)) {
        $BuildArgs += @("-CodeSignCertificateSubject", $CodeSignCertificateSubject)
    }
    if (-not [string]::IsNullOrWhiteSpace($CodeSignTimestampUrl)) {
        $BuildArgs += @("-CodeSignTimestampUrl", $CodeSignTimestampUrl)
    }
    if (-not [string]::IsNullOrWhiteSpace($SignToolPath)) {
        $BuildArgs += @("-SignToolPath", $SignToolPath)
    }
    if (@($SignToolExtraArgs).Count -gt 0) {
        $BuildArgs += "-SignToolExtraArgs"
        $BuildArgs += $SignToolExtraArgs
    }
    Invoke-External (Join-Path $Root "scripts\build_release.ps1") $BuildArgs
} else {
    Write-Host "[SKIP] release build"
}

if (-not $SkipVerify) {
    Write-Step "Verify release artifacts"
    $VerifyArgs = @("-RequireInstaller", "-RequireAppPacks", "-RequireRuntime", "-Strict")
    if ($RequireInstallerSignature -or $SignInstaller) {
        $VerifyArgs += "-RequireInstallerSignature"
    }
    Invoke-External (Join-Path $Root "scripts\verify_release.ps1") $VerifyArgs
} else {
    Write-Host "[SKIP] release verification"
}

Write-Step "Validate publish assets"
$Manifest = Read-JsonFile $ManifestPath
$InstallerInfo = Assert-InstallerMatchesManifest -Manifest $Manifest -ExpectedVersion $Version
if ($RequireInstallerSignature -or $SignInstaller) {
    Assert-InstallerSignature -Path $InstallerInfo.Path
}

$ReleaseUrl = "https://github.com/$Repository/releases/tag/$Tag"
$LatestManifestUrl = "https://github.com/$Repository/releases/latest/download/manifest.json"
$TagManifestUrl = "https://github.com/$Repository/releases/download/$Tag/manifest.json"
$TagInstallerUrl = "https://github.com/$Repository/releases/download/$Tag/$($InstallerInfo.File)"
if ([string]::IsNullOrWhiteSpace($RemoteVerifyManifestUrl)) {
    if ($Prerelease) {
        $RemoteVerifyManifestUrl = $TagManifestUrl
    } else {
        $RemoteVerifyManifestUrl = $LatestManifestUrl
    }
}
Write-Host "Latest manifest: $LatestManifestUrl"
Write-Host "Tag manifest: $TagManifestUrl"
Write-Host "Remote verify manifest: $RemoteVerifyManifestUrl"

if ($UpdateManifestInstallerUrl) {
    $Toolhub = Get-JsonProperty -Object $Manifest -Name "toolhub"
    $Installer = Get-JsonProperty -Object $Toolhub -Name "installer"
    Set-JsonProperty -Object $Installer -Name "url" -Value $TagInstallerUrl
    Set-JsonProperty -Object $Manifest -Name "release_notes_url" -Value $ReleaseUrl
    if ($DryRun) {
        Write-Host "[DRY RUN] Would update release/manifest.json with GitHub installer URL."
    } else {
        Write-JsonUtf8NoBomFile -Path $ManifestPath -InputObject $Manifest -Depth 20
        Write-Host "[OK] Updated release/manifest.json with GitHub installer URL."
        $Manifest = Read-JsonFile $ManifestPath
    }
}

Write-Step "Prepare release target folder"
Initialize-ReleaseTargetDirectory -TargetDir $ReleaseTargetDir
$TargetInstallerPath = Copy-ReleaseTargetAsset -SourcePath $InstallerInfo.Path -TargetDir $ReleaseTargetDir -Name $InstallerInfo.File
$TargetManifestPath = Copy-ReleaseTargetAsset -SourcePath $ManifestPath -TargetDir $ReleaseTargetDir -Name "manifest.json"
$TargetAppManifestPath = Copy-ReleaseTargetAsset -SourcePath $AppManifestPath -TargetDir $ReleaseTargetDir -Name "app_manifest.json"
$StagedAssetInfos = @(
    [ordered]@{ Name = $InstallerInfo.File; Path = $TargetInstallerPath; SourcePath = $InstallerInfo.Path },
    [ordered]@{ Name = "manifest.json"; Path = $TargetManifestPath; SourcePath = $ManifestPath },
    [ordered]@{ Name = "app_manifest.json"; Path = $TargetAppManifestPath; SourcePath = $AppManifestPath }
)
$EnabledAppPackAssets = Get-EnabledAppPackAssets -AppManifest $AppManifest
foreach ($AppPack in $EnabledAppPackAssets) {
    $TargetAppPackPath = Copy-ReleaseTargetAsset -SourcePath $AppPack.SourcePath -TargetDir $ReleaseTargetDir -Name $AppPack.Name
    $ActualSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $AppPack.SourcePath).Hash.ToLowerInvariant()
    if ($ActualSha256 -ne $AppPack.ExpectedSha256) {
        Fail "Enabled app pack sha256 does not match app_manifest.json: $($AppPack.AppId) expected=$($AppPack.ExpectedSha256) actual=$ActualSha256"
    }
    $StagedAssetInfos += [ordered]@{ Name = $AppPack.Name; Path = $TargetAppPackPath; SourcePath = $AppPack.SourcePath }
}
$ChecksumsPath = Write-ChecksumsFile -AssetInfos $StagedAssetInfos -TargetDir $ReleaseTargetDir
$UploadAssetInfos = @($StagedAssetInfos + [ordered]@{ Name = "checksums.sha256.txt"; Path = $ChecksumsPath; SourcePath = $null })
$TargetManifestReportPath = Write-ReleaseTargetManifest `
    -TargetDir $ReleaseTargetDir `
    -Repository $Repository `
    -Version $Version `
    -Tag $Tag `
    -TargetCommitish $ResolvedTargetCommitish `
    -ReleaseUrl $ReleaseUrl `
    -LatestManifestUrl $LatestManifestUrl `
    -TagManifestUrl $TagManifestUrl `
    -RemoteVerifyManifestUrl $RemoteVerifyManifestUrl `
    -AssetInfos $UploadAssetInfos
$Assets = @($StagedAssetInfos | ForEach-Object { $_.Path }) + @($ChecksumsPath)
Write-Host "Release target manifest: $TargetManifestReportPath"
Write-Host "Upload assets:"
$Assets | ForEach-Object { Write-Host "  $_" }

Write-Step "Verify release target folder"
$VerifyTargetScript = Join-Path $Root "scripts\verify_release_target_folder.ps1"
Invoke-External "powershell" @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $VerifyTargetScript, "-TargetDir", $ReleaseTargetDir, "-Version", $Version)

if ($PrepareTargetOnly) {
    Write-Host ""
    Write-Host "Release target folder preparation completed."
    Write-Host "No git tag, GitHub Release, upload, or remote verification was executed."
    exit 0
}

Write-Step "Git tag"
if ($SkipTag) {
    Write-Host "[SKIP] git tag management"
} else {
    & git rev-parse -q --verify "refs/tags/$Tag" *> $null
    $TagExists = ($LASTEXITCODE -eq 0)
    if ($TagExists) {
        $ExistingTagCommit = (& git rev-list -n 1 $Tag 2>$null)
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($ExistingTagCommit)) {
            Fail "Could not resolve existing local tag: $Tag"
        }
        $ExistingTagCommit = $ExistingTagCommit.Trim()
        if ($ExistingTagCommit -ne $ResolvedTargetCommitish) {
            Fail "Local tag $Tag points to $ExistingTagCommit, not target commitish $ResolvedTargetCommitish. Choose a new tag or move the tag deliberately outside this script."
        }
        Write-Host "[OK] tag exists at target commitish: $Tag"
    } else {
        Invoke-External "git" @("tag", $Tag, $ResolvedTargetCommitish)
    }
}

Write-Step "Publish GitHub Release"
Invoke-GhReleasePublish -Repository $Repository -TagName $Tag -TargetCommitish $ResolvedTargetCommitish -Title $ReleaseTitle -NotesText $ReleaseNotes -AssetPaths $Assets

if (-not $SkipRemoteVerify) {
    if ($Draft) {
        Write-Host "[SKIP] remote manifest verification for draft release assets. Draft assets are not public update endpoints."
    } else {
        Write-Step "Verify remote manifest"
        $VerifyScript = Join-Path $Root "scripts\verify_github_release_assets.ps1"
        $VerifyArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $VerifyScript, "-ManifestUrl", $RemoteVerifyManifestUrl, "-ExpectedVersion", $Version)
        if ($DownloadInstallerForRemoteVerify) {
            $VerifyArgs += "-DownloadInstaller"
        }
        Invoke-External "powershell" $VerifyArgs
    }
} else {
    Write-Host "[SKIP] remote manifest verification"
}

Write-Host ""
Write-Host "GitHub Release publish flow completed."
Write-Host "Release: $ReleaseUrl"
Write-Host "Latest manifest: $LatestManifestUrl"
Write-Host "Tag manifest: $TagManifestUrl"
Write-Host "Remote verify manifest: $RemoteVerifyManifestUrl"
if ($DryRun) {
    Write-Host "Dry run only. No build, tag, release, or upload commands were executed."
}
