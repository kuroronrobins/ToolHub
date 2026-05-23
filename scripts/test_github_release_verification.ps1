param()

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

. (Join-Path $PSScriptRoot "utf8_no_bom.ps1")

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VerifyScript = Join-Path $PSScriptRoot "verify_github_release_assets.ps1"

function Fail {
    param([string]$Message)
    throw $Message
}

function Pass {
    param([string]$Message)
    Write-Host "[OK] $Message"
}

function Invoke-VerifyScript {
    param([string[]]$Arguments)

    $Output = & powershell "-NoProfile" "-ExecutionPolicy" "Bypass" "-File" $VerifyScript @Arguments 2>&1
    return @{
        ExitCode = $LASTEXITCODE
        Text = ($Output -join "`n")
    }
}

function New-TestManifest {
    param(
        [string]$Path,
        [string]$Version,
        [string]$InstallerUrl = "",
        [string]$Sha256 = ("a" * 64),
        [int64]$Size = 12345
    )

    $Manifest = [ordered]@{
        schema_version = 1
        toolhub = [ordered]@{
            version = $Version
            installer = [ordered]@{
                file = "ToolHub_Setup_$Version.exe"
                url = $InstallerUrl
                sha256 = $Sha256
                size = $Size
            }
        }
    }
    Write-JsonUtf8NoBomFile -Path $Path -InputObject $Manifest -Depth 10
}

$WorkDir = Join-Path ([System.IO.Path]::GetTempPath()) ("toolhub_github_release_verify_test_" + [System.Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null

try {
    $Version = "9.9.9"
    $ManifestPath = Join-Path $WorkDir "manifest.json"
    New-TestManifest -Path $ManifestPath -Version $Version -InstallerUrl "https://example.com/releases/download/v$Version/ToolHub_Setup_$Version.exe"

    $Good = Invoke-VerifyScript -Arguments @("-ManifestPath", $ManifestPath, "-ExpectedVersion", $Version, "-Json")
    if ($Good.ExitCode -ne 0) {
        Fail "Expected local manifest verification to pass. exit=$($Good.ExitCode) output=$($Good.Text)"
    }
    $GoodReport = $Good.Text | ConvertFrom-Json
    if ($GoodReport.ok -ne $true) {
        Fail "Expected local manifest report ok=true."
    }
    if ($GoodReport.remote_version -ne $Version) {
        Fail "Expected remote_version=$Version but got $($GoodReport.remote_version)."
    }
    Pass "local fixture manifest verification passes"

    $InstallerFixture = Join-Path $WorkDir "ToolHub_Setup_$Version.exe"
    [System.IO.File]::WriteAllBytes($InstallerFixture, [System.Text.Encoding]::UTF8.GetBytes("toolhub installer fixture"))
    $InstallerFixtureSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $InstallerFixture).Hash.ToLowerInvariant()
    $InstallerFixtureSize = (Get-Item -LiteralPath $InstallerFixture).Length
    $LocalAssetManifestPath = Join-Path $WorkDir "manifest_local_asset.json"
    New-TestManifest -Path $LocalAssetManifestPath -Version $Version -Sha256 $InstallerFixtureSha256 -Size $InstallerFixtureSize
    $DownloadDir = Join-Path $WorkDir "downloaded"
    $LocalAsset = Invoke-VerifyScript -Arguments @("-ManifestPath", $LocalAssetManifestPath, "-ExpectedVersion", $Version, "-DownloadInstaller", "-OutputDir", $DownloadDir, "-Json")
    if ($LocalAsset.ExitCode -ne 0) {
        Fail "Expected local installer fixture verification to pass. exit=$($LocalAsset.ExitCode) output=$($LocalAsset.Text)"
    }
    $LocalAssetReport = $LocalAsset.Text | ConvertFrom-Json
    if ($LocalAssetReport.ok -ne $true) {
        Fail "Expected local installer fixture report ok=true."
    }
    Pass "local installer fixture sha256 verification passes"

    $LocalAssetMismatchManifestPath = Join-Path $WorkDir "manifest_local_asset_mismatch.json"
    New-TestManifest -Path $LocalAssetMismatchManifestPath -Version $Version -Sha256 ("b" * 64) -Size $InstallerFixtureSize
    $LocalAssetMismatch = Invoke-VerifyScript -Arguments @("-ManifestPath", $LocalAssetMismatchManifestPath, "-ExpectedVersion", $Version, "-DownloadInstaller", "-OutputDir", $DownloadDir, "-Json")
    if ($LocalAssetMismatch.ExitCode -eq 0) {
        Fail "Expected local installer fixture sha256 mismatch to fail."
    }
    $LocalAssetMismatchReport = $LocalAssetMismatch.Text | ConvertFrom-Json
    if ($LocalAssetMismatchReport.ok -eq $true) {
        Fail "Expected local installer fixture mismatch report ok=false."
    }
    Pass "local installer fixture sha256 mismatch is rejected"

    $Mismatch = Invoke-VerifyScript -Arguments @("-ManifestPath", $ManifestPath, "-ExpectedVersion", "0.0.0", "-Json")
    if ($Mismatch.ExitCode -eq 0) {
        Fail "Expected version mismatch verification to fail."
    }
    $MismatchReport = $Mismatch.Text | ConvertFrom-Json
    if ($MismatchReport.ok -eq $true) {
        Fail "Expected version mismatch report ok=false."
    }
    Pass "version mismatch is rejected"

    $HttpManifestPath = Join-Path $WorkDir "manifest_http.json"
    New-TestManifest -Path $HttpManifestPath -Version $Version -InstallerUrl "http://example.com/ToolHub_Setup_$Version.exe"
    $HttpBlocked = Invoke-VerifyScript -Arguments @("-ManifestPath", $HttpManifestPath, "-ExpectedVersion", $Version, "-Json")
    if ($HttpBlocked.ExitCode -eq 0) {
        Fail "Expected http installer URL to be rejected without -AllowHttp."
    }
    Pass "http installer URL is rejected by default"

    $HttpManifestBlocked = Invoke-VerifyScript -Arguments @("-ManifestUrl", "http://example.com/manifest.json", "-Json")
    if ($HttpManifestBlocked.ExitCode -eq 0) {
        Fail "Expected http manifest URL to be rejected without -AllowHttp."
    }
    $HttpManifestReport = $HttpManifestBlocked.Text | ConvertFrom-Json
    if ($HttpManifestReport.ok -eq $true) {
        Fail "Expected http manifest URL report ok=false."
    }
    Pass "http manifest URL is rejected by default"
} finally {
    if (Test-Path -LiteralPath $WorkDir) {
        Remove-Item -LiteralPath $WorkDir -Recurse -Force
    }
}

Write-Host "GitHub release verification tests completed."
