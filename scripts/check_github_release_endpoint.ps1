param(
    [string]$Owner,
    [string]$Repo,
    [string]$Remote = "origin",
    [string]$Version,
    [string]$Tag,
    [string]$ManifestUrl,
    [switch]$DownloadInstaller,
    [string]$OutputDir,
    [switch]$Json
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ReleaseManifestPath = Join-Path $Root "release\manifest.json"
$AppManifestPath = Join-Path $Root "release\app_manifest.json"
$VerifyScript = Join-Path $PSScriptRoot "verify_github_release_assets.ps1"

function Write-Line {
    param([string]$Message)
    if (-not $Json) {
        Write-Host $Message
    }
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

function Invoke-ChildPowerShell {
    param([string[]]$Arguments)

    $Output = & powershell "-NoProfile" "-ExecutionPolicy" "Bypass" @Arguments 2>&1
    return @{
        ExitCode = $LASTEXITCODE
        Text = ($Output -join "`n")
    }
}

function Invoke-GhJson {
    param([string[]]$Arguments)

    $Output = & gh @Arguments 2>&1
    return @{
        ExitCode = $LASTEXITCODE
        Text = ($Output -join "`n")
    }
}

function Read-ReleaseManifest {
    if (-not (Test-Path -LiteralPath $ReleaseManifestPath -PathType Leaf)) {
        return $null
    }
    try {
        return Get-Content -Raw -Encoding UTF8 -LiteralPath $ReleaseManifestPath | ConvertFrom-Json
    } catch {
        return $null
    }
}

$Checks = New-Object System.Collections.ArrayList
$Manifest = Read-ReleaseManifest
$ManifestVersion = if ($Manifest) { [string](Get-JsonProperty -Object (Get-JsonProperty -Object $Manifest -Name "toolhub") -Name "version") } else { "" }
if ([string]::IsNullOrWhiteSpace($Version)) {
    $Version = $ManifestVersion
}
if ([string]::IsNullOrWhiteSpace($Tag) -and -not [string]::IsNullOrWhiteSpace($Version)) {
    $Tag = "v$Version"
}

$RepoInfo = Resolve-GitHubRepoFromRemote -RemoteName $Remote
if ([string]::IsNullOrWhiteSpace($Owner) -and $RepoInfo) {
    $Owner = $RepoInfo.Owner
}
if ([string]::IsNullOrWhiteSpace($Repo) -and $RepoInfo) {
    $Repo = $RepoInfo.Repo
}

$Repository = if (-not [string]::IsNullOrWhiteSpace($Owner) -and -not [string]::IsNullOrWhiteSpace($Repo)) { "$Owner/$Repo" } else { "" }
if ([string]::IsNullOrWhiteSpace($ManifestUrl) -and -not [string]::IsNullOrWhiteSpace($Repository)) {
    $ManifestUrl = "https://github.com/$Repository/releases/latest/download/manifest.json"
}

$InstallerFile = ""
if ($Manifest) {
    $Toolhub = Get-JsonProperty -Object $Manifest -Name "toolhub"
    $Installer = Get-JsonProperty -Object $Toolhub -Name "installer"
    $InstallerFile = [string](Get-JsonProperty -Object $Installer -Name "file")
}
$RequiredAppPacks = @()
if (Test-Path -LiteralPath $AppManifestPath -PathType Leaf) {
    try {
        $AppManifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $AppManifestPath | ConvertFrom-Json
        foreach ($Property in $AppManifest.apps.PSObject.Properties) {
            if ($Property.Value.enabled -eq $true -and -not [string]::IsNullOrWhiteSpace([string]$Property.Value.package)) {
                $RequiredAppPacks += [System.IO.Path]::GetFileName(([string]$Property.Value.package).Replace("/", "\"))
            }
        }
    } catch {
        Add-Check -Checks $Checks -Id "app_manifest_read" -Status "fail" -Message "release/app_manifest.json could not be read: $($_.Exception.Message)"
    }
}
$RequiredAssets = @($InstallerFile, "manifest.json", "app_manifest.json") + @($RequiredAppPacks) + @("checksums.sha256.txt") | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }

$Report = [ordered]@{
    generated_at = (Get-Date).ToString("s")
    project_root = $Root
    repository = $Repository
    tag = $Tag
    expected_version = $Version
    latest_manifest_url = $ManifestUrl
    required_assets = @($RequiredAssets)
    release = $null
    remote_manifest = $null
    checks = @()
    ok = $false
}

if ([string]::IsNullOrWhiteSpace($Repository)) {
    Add-Check -Checks $Checks -Id "github_repository" -Status "fail" -Message "GitHub owner/repo could not be resolved. Pass -Owner and -Repo."
} else {
    Add-Check -Checks $Checks -Id "github_repository" -Status "pass" -Message "GitHub repository resolved: $Repository"
}

if ([string]::IsNullOrWhiteSpace($Tag)) {
    Add-Check -Checks $Checks -Id "release_tag" -Status "fail" -Message "Release tag could not be resolved. Pass -Tag or set release/manifest.json toolhub.version."
} else {
    Add-Check -Checks $Checks -Id "release_tag" -Status "pass" -Message "Release tag resolved: $Tag"
}

if (-not (Get-Command "gh" -ErrorAction SilentlyContinue)) {
    Add-Check -Checks $Checks -Id "gh_available" -Status "warning" -Message "GitHub CLI gh was not found; release existence and asset list could not be checked."
} elseif (-not [string]::IsNullOrWhiteSpace($Repository) -and -not [string]::IsNullOrWhiteSpace($Tag)) {
    $GhResult = Invoke-GhJson -Arguments @("release", "view", $Tag, "--repo", $Repository, "--json", "tagName,isDraft,isPrerelease,url,assets")
    if ($GhResult.ExitCode -ne 0) {
        Add-Check -Checks $Checks -Id "release_exists" -Status "fail" -Message "GitHub Release was not found or could not be read: $Tag" -Details @{ exit_code = $GhResult.ExitCode; output = $GhResult.Text }
    } else {
        try {
            $Release = $GhResult.Text | ConvertFrom-Json
            $Report.release = $Release
            Add-Check -Checks $Checks -Id "release_exists" -Status "pass" -Message "GitHub Release exists: $Tag"

            $AssetNames = @($Release.assets | ForEach-Object { [string]$_.name })
            $MissingAssets = @($RequiredAssets | Where-Object { $AssetNames -notcontains $_ })
            if ($MissingAssets.Count -eq 0) {
                Add-Check -Checks $Checks -Id "release_assets" -Status "pass" -Message "Required release assets are present." -Details @{ asset_names = @($AssetNames) }
            } else {
                Add-Check -Checks $Checks -Id "release_assets" -Status "fail" -Message "Required release assets are missing: $($MissingAssets -join ', ')" -Details @{ asset_names = @($AssetNames); missing = @($MissingAssets) }
            }
        } catch {
            Add-Check -Checks $Checks -Id "release_parse" -Status "fail" -Message "gh release JSON could not be parsed: $($_.Exception.Message)" -Details @{ output = $GhResult.Text }
        }
    }
}

if ([string]::IsNullOrWhiteSpace($ManifestUrl)) {
    Add-Check -Checks $Checks -Id "latest_manifest_url" -Status "fail" -Message "Latest manifest URL could not be resolved."
} elseif (-not (Test-Path -LiteralPath $VerifyScript -PathType Leaf)) {
    Add-Check -Checks $Checks -Id "remote_manifest_verify_script" -Status "fail" -Message "verify_github_release_assets.ps1 was not found."
} else {
    $VerifyArgs = @("-File", $VerifyScript, "-ManifestUrl", $ManifestUrl, "-Json")
    if (-not [string]::IsNullOrWhiteSpace($Version)) {
        $VerifyArgs += @("-ExpectedVersion", $Version)
    }
    if ($DownloadInstaller) {
        $VerifyArgs += "-DownloadInstaller"
    }
    if (-not [string]::IsNullOrWhiteSpace($OutputDir)) {
        $VerifyArgs += @("-OutputDir", $OutputDir)
    }
    $VerifyResult = Invoke-ChildPowerShell -Arguments $VerifyArgs
    try {
        $VerifyReport = $VerifyResult.Text | ConvertFrom-Json
        $Report.remote_manifest = $VerifyReport
        if ($VerifyResult.ExitCode -eq 0 -and $VerifyReport.ok -eq $true) {
            Add-Check -Checks $Checks -Id "latest_manifest_verify" -Status "pass" -Message "Latest manifest URL is readable and valid."
        } else {
            $FailureMessages = @($VerifyReport.checks | Where-Object { $_.status -eq "fail" } | ForEach-Object { $_.message })
            Add-Check -Checks $Checks -Id "latest_manifest_verify" -Status "fail" -Message "Latest manifest verification failed: $($FailureMessages -join '; ')" -Details $VerifyReport.checks
        }
    } catch {
        Add-Check -Checks $Checks -Id "latest_manifest_verify" -Status "fail" -Message "Latest manifest verification output could not be parsed: $($_.Exception.Message)" -Details @{ exit_code = $VerifyResult.ExitCode; output = $VerifyResult.Text }
    }
}

$Report.checks = @($Checks)
$Failed = @($Checks | Where-Object { $_.status -eq "fail" }).Count -gt 0
$Report.ok = -not $Failed

if ($Json) {
    $Report | ConvertTo-Json -Depth 12
} else {
    Write-Line ""
    if ($Report.ok) {
        Write-Line "GitHub Release endpoint check completed."
    } else {
        Write-Line "GitHub Release endpoint check found missing or invalid release state."
    }
}

if ($Failed) {
    exit 1
}
exit 0
