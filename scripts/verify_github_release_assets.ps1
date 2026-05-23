param(
    [string]$ManifestUrl,
    [string]$ManifestPath,
    [string]$Owner,
    [string]$Repo,
    [string]$Tag = "latest",
    [string]$ExpectedVersion,
    [switch]$DownloadInstaller,
    [string]$OutputDir,
    [switch]$AllowHttp,
    [switch]$Json
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Write-Line {
    param([string]$Message)
    if (-not $Json) {
        Write-Host $Message
    }
}

function New-Check {
    param(
        [string]$Id,
        [string]$Status,
        [string]$Message,
        [object]$Details = $null
    )

    [ordered]@{
        id = $Id
        status = $Status
        message = $Message
        details = $Details
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

    [void]$Checks.Add((New-Check -Id $Id -Status $Status -Message $Message -Details $Details))
    if ($Status -eq "pass") {
        Write-Line "[OK] $Message"
    } elseif ($Status -eq "warning") {
        Write-Line "[WARN] $Message"
    } else {
        Write-Line "[NG] $Message"
    }
}

function Is-HttpUrl {
    param([string]$Value)
    return ($Value -match "^https?://")
}

function Is-HttpsUrl {
    param([string]$Value)
    return ($Value -match "^https://")
}

function Assert-AllowedUrl {
    param(
        [string]$Url,
        [string]$Label
    )

    if ([string]::IsNullOrWhiteSpace($Url)) {
        throw "$Label URL is empty."
    }
    if (-not (Is-HttpUrl $Url)) {
        throw "$Label must be an HTTP(S) URL: $Url"
    }
    if ((-not $AllowHttp) -and -not (Is-HttpsUrl $Url)) {
        throw "$Label must use https://. Use -AllowHttp only for local test endpoints."
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

function Resolve-ManifestUrl {
    if (-not [string]::IsNullOrWhiteSpace($ManifestUrl)) {
        return $ManifestUrl
    }
    if ([string]::IsNullOrWhiteSpace($Owner) -or [string]::IsNullOrWhiteSpace($Repo)) {
        throw "Specify -ManifestUrl or both -Owner and -Repo."
    }
    if ($Tag -eq "latest") {
        return "https://github.com/$Owner/$Repo/releases/latest/download/manifest.json"
    }
    return "https://github.com/$Owner/$Repo/releases/download/$Tag/manifest.json"
}

function Resolve-ManifestSource {
    if (-not [string]::IsNullOrWhiteSpace($ManifestPath)) {
        if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
            throw "Manifest file was not found: $ManifestPath"
        }
        return @{
            Kind = "file"
            Value = (Resolve-Path -LiteralPath $ManifestPath).Path
        }
    }
    return @{
        Kind = "url"
        Value = (Resolve-ManifestUrl)
    }
}

function Resolve-InstallerUrl {
    param(
        [object]$ManifestSource,
        [object]$Installer
    )

    $InstallerUrl = [string](Get-PropertyValue -Object $Installer -Name "url")
    if (-not [string]::IsNullOrWhiteSpace($InstallerUrl)) {
        return $InstallerUrl
    }

    $InstallerFile = [string](Get-PropertyValue -Object $Installer -Name "file")
    if ([string]::IsNullOrWhiteSpace($InstallerFile)) {
        return ""
    }
    if (Is-HttpUrl $InstallerFile) {
        return $InstallerFile
    }

    if ($ManifestSource.Kind -eq "file") {
        if ([System.IO.Path]::IsPathRooted($InstallerFile)) {
            return $InstallerFile
        }
        $ManifestDir = Split-Path -Parent ([string]$ManifestSource.Value)
        return (Join-Path $ManifestDir $InstallerFile)
    }

    $Base = [string]$ManifestSource.Value
    $Slash = $Base.LastIndexOf("/")
    if ($Slash -lt 0) {
        return ""
    }
    return ($Base.Substring(0, $Slash) + "/" + $InstallerFile.Replace("\", "/"))
}

function Invoke-DownloadText {
    param([string]$Url)

    $Response = Invoke-WebRequest -UseBasicParsing -TimeoutSec 30 -Uri $Url
    if ($null -ne $Response.Content) {
        return [string]$Response.Content
    }
    if ($null -ne $Response.RawContent) {
        return [string]$Response.RawContent
    }
    throw "Response content was empty."
}

function Ensure-OutputDir {
    if (-not [string]::IsNullOrWhiteSpace($OutputDir)) {
        New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
        return (Resolve-Path $OutputDir).Path
    }
    $TempRoot = Join-Path ([System.IO.Path]::GetTempPath()) "ToolHubReleaseVerify"
    New-Item -ItemType Directory -Force -Path $TempRoot | Out-Null
    return $TempRoot
}

function Assert-AllowedInstallerSource {
    param(
        [object]$ManifestSource,
        [string]$InstallerSource
    )

    if ([string]::IsNullOrWhiteSpace($InstallerSource)) {
        throw "Installer URL could not be resolved."
    }
    if (Is-HttpUrl $InstallerSource) {
        Assert-AllowedUrl -Url $InstallerSource -Label "Installer"
        return
    }
    if ($ManifestSource.Kind -eq "file") {
        if (-not (Test-Path -LiteralPath $InstallerSource -PathType Leaf)) {
            throw "Local fixture installer was not found: $InstallerSource"
        }
        return
    }
    throw "Remote manifest installer must resolve to an HTTP(S) URL: $InstallerSource"
}

function Copy-Or-DownloadInstaller {
    param(
        [object]$ManifestSource,
        [string]$InstallerSource,
        [string]$DownloadPath
    )

    if (Is-HttpUrl $InstallerSource) {
        Invoke-WebRequest -UseBasicParsing -TimeoutSec 120 -Uri $InstallerSource -OutFile $DownloadPath
        return
    }
    if ($ManifestSource.Kind -eq "file") {
        Copy-Item -LiteralPath $InstallerSource -Destination $DownloadPath -Force
        return
    }
    throw "Installer source is not downloadable: $InstallerSource"
}

$Checks = New-Object System.Collections.ArrayList
$Report = [ordered]@{
    generated_at = (Get-Date).ToString("s")
    project_root = $Root
    manifest_url = $null
    installer_url = $null
    expected_version = $ExpectedVersion
    remote_version = $null
    installer_file = $null
    installer_sha256 = $null
    installer_size = $null
    downloaded_installer = $null
    checks = @()
    ok = $false
}

try {
    $ManifestSource = Resolve-ManifestSource
    $ResolvedManifestUrl = [string]$ManifestSource.Value
    $Report.manifest_url = $ResolvedManifestUrl
    if ($ManifestSource.Kind -eq "url") {
        Assert-AllowedUrl -Url $ResolvedManifestUrl -Label "Manifest"
        Add-Check -Checks $Checks -Id "manifest_url_allowed" -Status "pass" -Message "manifest URL is allowed: $ResolvedManifestUrl"
    } else {
        Add-Check -Checks $Checks -Id "manifest_file_readable" -Status "pass" -Message "manifest file is readable: $ResolvedManifestUrl"
    }

    $ManifestText = if ($ManifestSource.Kind -eq "url") {
        Invoke-DownloadText -Url $ResolvedManifestUrl
    } else {
        Get-Content -Raw -Encoding UTF8 -LiteralPath $ResolvedManifestUrl
    }
    Add-Check -Checks $Checks -Id "manifest_loaded" -Status "pass" -Message "manifest was loaded"

    $Manifest = $ManifestText | ConvertFrom-Json
    Add-Check -Checks $Checks -Id "manifest_json_valid" -Status "pass" -Message "remote manifest JSON is valid"

    $SchemaVersion = Get-PropertyValue -Object $Manifest -Name "schema_version"
    if ([int]$SchemaVersion -eq 1) {
        Add-Check -Checks $Checks -Id "schema_version" -Status "pass" -Message "remote manifest schema_version is 1"
    } else {
        Add-Check -Checks $Checks -Id "schema_version" -Status "fail" -Message "remote manifest schema_version is not 1"
    }

    $Toolhub = Get-PropertyValue -Object $Manifest -Name "toolhub"
    $RemoteVersion = [string](Get-PropertyValue -Object $Toolhub -Name "version")
    $Report.remote_version = $RemoteVersion
    if ([string]::IsNullOrWhiteSpace($RemoteVersion)) {
        Add-Check -Checks $Checks -Id "toolhub_version" -Status "fail" -Message "remote manifest toolhub.version is missing"
    } elseif ([string]::IsNullOrWhiteSpace($ExpectedVersion) -or $RemoteVersion -eq $ExpectedVersion) {
        Add-Check -Checks $Checks -Id "toolhub_version" -Status "pass" -Message "remote manifest version is $RemoteVersion"
    } else {
        Add-Check -Checks $Checks -Id "toolhub_version" -Status "fail" -Message "remote manifest version $RemoteVersion does not match expected $ExpectedVersion"
    }

    $Installer = Get-PropertyValue -Object $Toolhub -Name "installer"
    $InstallerFile = [string](Get-PropertyValue -Object $Installer -Name "file")
    $InstallerSha256 = ([string](Get-PropertyValue -Object $Installer -Name "sha256")).Trim().ToLowerInvariant()
    $InstallerSize = Get-PropertyValue -Object $Installer -Name "size"
    $ResolvedInstallerUrl = Resolve-InstallerUrl -ManifestSource $ManifestSource -Installer $Installer
    $Report.installer_url = $ResolvedInstallerUrl
    $Report.installer_file = $InstallerFile
    $Report.installer_sha256 = $InstallerSha256
    $Report.installer_size = $InstallerSize

    if ([string]::IsNullOrWhiteSpace($InstallerFile)) {
        Add-Check -Checks $Checks -Id "installer_file" -Status "fail" -Message "remote manifest toolhub.installer.file is missing"
    } elseif ($InstallerFile -match "^ToolHub_Setup_.+\.(exe|msi)$") {
        Add-Check -Checks $Checks -Id "installer_file" -Status "pass" -Message "installer file name is publishable: $InstallerFile"
    } else {
        Add-Check -Checks $Checks -Id "installer_file" -Status "fail" -Message "installer file must look like ToolHub_Setup_<version>.exe or .msi"
    }

    if ([string]::IsNullOrWhiteSpace($ResolvedInstallerUrl)) {
        Add-Check -Checks $Checks -Id "installer_url" -Status "fail" -Message "installer URL could not be resolved"
    } else {
        Assert-AllowedInstallerSource -ManifestSource $ManifestSource -InstallerSource $ResolvedInstallerUrl
        Add-Check -Checks $Checks -Id "installer_url" -Status "pass" -Message "installer source is allowed: $ResolvedInstallerUrl"
    }

    if ($InstallerSha256 -match "^[0-9a-f]{64}$") {
        Add-Check -Checks $Checks -Id "installer_sha256" -Status "pass" -Message "installer sha256 is present"
    } else {
        Add-Check -Checks $Checks -Id "installer_sha256" -Status "fail" -Message "installer sha256 is missing or invalid"
    }

    if ($null -ne $InstallerSize -and [int64]$InstallerSize -gt 0) {
        Add-Check -Checks $Checks -Id "installer_size" -Status "pass" -Message "installer size is present: $InstallerSize"
    } else {
        Add-Check -Checks $Checks -Id "installer_size" -Status "warning" -Message "installer size is missing"
    }

    if ($DownloadInstaller) {
        if ([string]::IsNullOrWhiteSpace($ResolvedInstallerUrl)) {
            throw "Cannot download installer because installer URL is missing."
        }
        $DownloadDir = Ensure-OutputDir
        $InstallerName = if ([string]::IsNullOrWhiteSpace($InstallerFile)) { "ToolHub_Setup_download.exe" } else { $InstallerFile }
        $DownloadPath = Join-Path $DownloadDir $InstallerName
        Copy-Or-DownloadInstaller -ManifestSource $ManifestSource -InstallerSource $ResolvedInstallerUrl -DownloadPath $DownloadPath
        $Report.downloaded_installer = $DownloadPath
        Add-Check -Checks $Checks -Id "installer_downloaded" -Status "pass" -Message "installer was copied or downloaded: $DownloadPath"

        $ActualSize = (Get-Item -LiteralPath $DownloadPath).Length
        if ($null -ne $InstallerSize -and [int64]$InstallerSize -gt 0 -and [int64]$InstallerSize -ne $ActualSize) {
            Add-Check -Checks $Checks -Id "downloaded_installer_size" -Status "fail" -Message "downloaded installer size mismatch. expected=$InstallerSize actual=$ActualSize"
        } else {
            Add-Check -Checks $Checks -Id "downloaded_installer_size" -Status "pass" -Message "downloaded installer size verified: $ActualSize"
        }

        $ActualSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $DownloadPath).Hash.ToLowerInvariant()
        if ($ActualSha256 -eq $InstallerSha256) {
            Add-Check -Checks $Checks -Id "downloaded_installer_sha256" -Status "pass" -Message "downloaded installer sha256 matches remote manifest"
        } else {
            Add-Check -Checks $Checks -Id "downloaded_installer_sha256" -Status "fail" -Message "downloaded installer sha256 mismatch. expected=$InstallerSha256 actual=$ActualSha256"
        }
    } else {
        Add-Check -Checks $Checks -Id "installer_download" -Status "warning" -Message "installer was not downloaded; sha256 was not proven against the remote asset"
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
        Write-Line "GitHub release asset verification completed."
    } else {
        Write-Line "GitHub release asset verification failed."
    }
}

if ($Failed) {
    exit 1
}
exit 0
