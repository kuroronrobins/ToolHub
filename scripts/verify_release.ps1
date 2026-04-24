param(
    [switch]$RequireInstaller,
    [switch]$RequireAppPacks
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ReleaseDir = Join-Path $Root "release"
$ManifestPath = Join-Path $ReleaseDir "manifest.json"
$AppManifestPath = Join-Path $ReleaseDir "app_manifest.json"
$Failed = $false
Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction SilentlyContinue

function Pass($Message) { Write-Host "[OK] $Message" }
function Warn($Message) { Write-Host "[WARN] $Message" }
function Fail($Message) { Write-Host "[NG] $Message"; $script:Failed = $true }

function Read-Json($Path) {
    try {
        return Get-Content -Raw -Encoding UTF8 $Path | ConvertFrom-Json
    } catch {
        Fail "Invalid JSON: $Path"
        return $null
    }
}

if (Test-Path -LiteralPath $ManifestPath -PathType Leaf) { Pass "release/manifest.json exists" } else { Fail "release/manifest.json is missing" }
if (Test-Path -LiteralPath $AppManifestPath -PathType Leaf) { Pass "release/app_manifest.json exists" } else { Fail "release/app_manifest.json is missing" }

$Manifest = if (Test-Path -LiteralPath $ManifestPath -PathType Leaf) { Read-Json $ManifestPath } else { $null }
$AppManifest = if (Test-Path -LiteralPath $AppManifestPath -PathType Leaf) { Read-Json $AppManifestPath } else { $null }

foreach ($Path in @("runner", "apps", "runtime", "config.default", "updater", "installer")) {
    $Full = Join-Path $Root $Path
    if (Test-Path -LiteralPath $Full -PathType Container) { Pass "$Path exists" } else { Fail "$Path is missing" }
}

if ($Manifest) {
    if ($Manifest.schema_version -eq 1) { Pass "manifest schema_version is 1" } else { Fail "manifest schema_version must be 1" }
    if ($Manifest.apps_manifest -eq "app_manifest.json") { Pass "apps_manifest points to app_manifest.json" } else { Fail "apps_manifest is invalid" }
    if ($Manifest.toolhub.installer.file) {
        $InstallerPath = Join-Path (Join-Path $ReleaseDir "dist_installer") ([string]$Manifest.toolhub.installer.file)
        if (Test-Path -LiteralPath $InstallerPath -PathType Leaf) {
            Pass "installer file exists"
            $Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $InstallerPath).Hash.ToLowerInvariant()
            if ($Manifest.toolhub.installer.sha256 -and $Hash -eq $Manifest.toolhub.installer.sha256) {
                Pass "installer sha256 matches"
            } elseif ($Manifest.toolhub.installer.sha256) {
                Fail "installer sha256 mismatch"
            } else {
                Warn "installer sha256 is empty"
            }
        } elseif ($RequireInstaller) {
            Fail "installer file is missing: $InstallerPath"
        } else {
            Warn "installer file is not present yet: $InstallerPath"
        }
    } else {
        Fail "installer file is missing in manifest"
    }
}

if ($AppManifest) {
    if ($AppManifest.schema_version -eq 1) { Pass "app_manifest schema_version is 1" } else { Fail "app_manifest schema_version must be 1" }
    foreach ($Prop in $AppManifest.apps.PSObject.Properties) {
        $Id = $Prop.Name
        $Entry = $Prop.Value
        $AppDir = Join-Path (Join-Path $Root "apps") $Id
        if (Test-Path -LiteralPath (Join-Path $AppDir "app.yaml") -PathType Leaf) { Pass "$Id app.yaml exists" } else { Fail "$Id app.yaml is missing" }
        if ($Entry.version) { Pass "$Id version is set" } else { Fail "$Id version is missing" }
        if ($Entry.required_core) { Pass "$Id required_core is set" } else { Fail "$Id required_core is missing" }
        if ($Entry.required_runner) { Pass "$Id required_runner is set" } else { Fail "$Id required_runner is missing" }
        if ($Entry.package) {
            $PackPath = Join-Path $ReleaseDir ([string]$Entry.package)
            if (Test-Path -LiteralPath $PackPath -PathType Leaf) {
                Pass "$Id app pack exists"
                $Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $PackPath).Hash.ToLowerInvariant()
                if ($Entry.sha256 -and $Hash -eq $Entry.sha256) {
                    Pass "$Id app pack sha256 matches"
                } elseif ($Entry.sha256) {
                    Fail "$Id app pack sha256 mismatch"
                } else {
                    Warn "$Id app pack sha256 is empty"
                }
                try {
                    $Zip = [System.IO.Compression.ZipFile]::OpenRead($PackPath)
                    $EntryNames = @($Zip.Entries | ForEach-Object { $_.FullName.Replace("\", "/") })
                    if ($EntryNames -contains "$Id/app.yaml") { Pass "$Id app pack contains app.yaml" } else { Fail "$Id app pack does not contain $Id/app.yaml" }
                    if ($EntryNames -contains "$Id/pack_manifest.json") { Pass "$Id app pack contains pack_manifest.json" } else { Fail "$Id app pack does not contain $Id/pack_manifest.json" }
                    $Zip.Dispose()
                } catch {
                    Fail "$Id app pack could not be inspected"
                }
            } elseif ($RequireAppPacks) {
                Fail "$Id app pack is missing: $PackPath"
            } else {
                Warn "$Id app pack is not present yet: $PackPath"
            }
        } else {
            Fail "$Id package path is missing"
        }
    }
}

if ($Failed) {
    exit 1
}
exit 0
