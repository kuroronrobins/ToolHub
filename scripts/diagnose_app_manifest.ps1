param(
    [switch]$Strict,
    [switch]$RequireAppPacks,
    [switch]$Json
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ReleaseDir = Join-Path $Root "release"
$AppManifestPath = Join-Path $ReleaseDir "app_manifest.json"
$AppsDir = Join-Path $Root "apps"
$Failed = $false

function New-Finding {
    param(
        [string]$AppId,
        [string]$Message,
        [string]$Path = "",
        [string]$Recommendation = ""
    )
    [ordered]@{
        app_id = $AppId
        message = $Message
        path = $Path
        recommendation = $Recommendation
    }
}

function Add-ListItem {
    param(
        [System.Collections.IDictionary]$Report,
        [string]$Name,
        [object]$Value
    )
    $Report[$Name] = @($Report[$Name]) + @($Value)
}

function Entry-Enabled {
    param([object]$Entry)
    if ($null -eq $Entry.PSObject.Properties["enabled"]) {
        return $true
    }
    return [bool]$Entry.enabled
}

function Write-Line {
    param([string]$Message)
    if (-not $Json) {
        Write-Host $Message
    }
}

function Mark-Fail {
    param([string]$Message)
    Write-Line "[NG] $Message"
    $script:Failed = $true
}

function Mark-Warn {
    param([string]$Message)
    if ($Strict) {
        Mark-Fail $Message
    } else {
        Write-Line "[WARN] $Message"
    }
}

function Mark-Ok {
    param([string]$Message)
    Write-Line "[OK] $Message"
}

$Report = [ordered]@{
    strict = [bool]$Strict
    require_app_packs = [bool]$RequireAppPacks
    manifest_path = $AppManifestPath
    apps_dir = $AppsDir
    manifest_entry_count = 0
    app_source_count = 0
    enabled_apps = @()
    disabled_apps_with_source = @()
    disabled_stale_entries = @()
    enabled_missing_source = @()
    apps_missing_from_manifest = @()
    missing_metadata = @()
    version_mismatch = @()
    package_path_missing = @()
    sha256_mismatch = @()
}

if (-not (Test-Path -LiteralPath $AppManifestPath -PathType Leaf)) {
    Mark-Fail "release/app_manifest.json is missing: $AppManifestPath"
    if ($Json) { $Report | ConvertTo-Json -Depth 12 }
    exit 1
}

try {
    $AppManifest = Get-Content -Raw -Encoding UTF8 $AppManifestPath | ConvertFrom-Json
} catch {
    Mark-Fail "release/app_manifest.json is invalid JSON: $AppManifestPath"
    if ($Json) { $Report | ConvertTo-Json -Depth 12 }
    exit 1
}

$ManifestProps = @($AppManifest.apps.PSObject.Properties)
$ManifestIds = @($ManifestProps | ForEach-Object { $_.Name })
$Report["manifest_entry_count"] = $ManifestIds.Count

$SourceIds = @()
if (Test-Path -LiteralPath $AppsDir -PathType Container) {
    $SourceIds = @(Get-ChildItem -LiteralPath $AppsDir -Directory | Where-Object {
        Test-Path -LiteralPath (Join-Path $_.FullName "app.yaml") -PathType Leaf
    } | ForEach-Object { $_.Name })
}
$Report["app_source_count"] = $SourceIds.Count

foreach ($Prop in $ManifestProps) {
    $Id = $Prop.Name
    $Entry = $Prop.Value
    $Enabled = Entry-Enabled $Entry
    $AppYamlPath = Join-Path (Join-Path $AppsDir $Id) "app.yaml"
    $HasSource = Test-Path -LiteralPath $AppYamlPath -PathType Leaf

    if ($Enabled) {
        Add-ListItem $Report "enabled_apps" $Id
        if (-not $HasSource) {
            $Finding = New-Finding -AppId $Id -Path $AppYamlPath -Message "enabled=true but apps/<app_id>/app.yaml is missing" -Recommendation "Restore the app source, or set enabled=false if this is a stale test/history entry; use a future full-delete flow for complete removal."
            Add-ListItem $Report "enabled_missing_source" $Finding
            Mark-Fail "$Id enabled=true app.yaml is missing: $AppYamlPath. Restore source or disable the manifest entry."
            continue
        }
    } elseif ($HasSource) {
        Add-ListItem $Report "disabled_apps_with_source" $Id
        Mark-Ok "$Id is disabled with app source present"
    } else {
        $Finding = New-Finding -AppId $Id -Path $AppYamlPath -Message "enabled=false stale manifest entry without app source" -Recommendation "Keep as disabled history for normal checks, restore source if needed, or remove later through a deliberate full-delete flow."
        Add-ListItem $Report "disabled_stale_entries" $Finding
        if ($Strict) {
            Mark-Fail "$Id enabled=false stale entry is missing app.yaml: $AppYamlPath"
        } else {
            Write-Line "[WARN] $Id enabled=false stale entry is missing app.yaml: $AppYamlPath"
        }
    }

    $ShouldCheckMetadata = $Enabled -or $HasSource
    if ($ShouldCheckMetadata) {
        foreach ($Field in @("version", "package", "required_core", "required_runner")) {
            if ([string]::IsNullOrWhiteSpace([string]$Entry.$Field)) {
                $Finding = New-Finding -AppId $Id -Message "Required app_manifest field is missing: $Field" -Recommendation "Fill $Field before enabling or packaging the app."
                Add-ListItem $Report "missing_metadata" $Finding
                if ($Enabled) {
                    Mark-Fail "$Id enabled=true required field is missing: $Field"
                } else {
                    Mark-Warn "$Id enabled=false with source has missing field: $Field"
                }
            }
        }

        if ($HasSource -and $Entry.version) {
            $AppYamlText = Get-Content -Raw -Encoding UTF8 $AppYamlPath
            $ExpectedVersion = [regex]::Escape([string]$Entry.version)
            if ($AppYamlText -notmatch "version:\s*['""]?$ExpectedVersion['""]?") {
                $Finding = New-Finding -AppId $Id -Path $AppYamlPath -Message "app.yaml version was not matched to app_manifest version" -Recommendation "Align app.yaml version and release/app_manifest.json before release."
                Add-ListItem $Report "version_mismatch" $Finding
                Mark-Warn "$Id app.yaml version was not matched to app_manifest version"
            }
        }
    }

    if ($Entry.package) {
        $PackagePath = Join-Path $ReleaseDir ([string]$Entry.package)
        if (-not (Test-Path -LiteralPath $PackagePath -PathType Leaf)) {
            $Finding = New-Finding -AppId $Id -Path $PackagePath -Message "App Pack package path is missing" -Recommendation "Generate the App Pack, or keep the entry disabled/stale until a later cleanup."
            Add-ListItem $Report "package_path_missing" $Finding
            if ($RequireAppPacks -and ($Enabled -or $HasSource)) {
                Mark-Fail "$Id app pack is missing: $PackagePath"
            } else {
                Mark-Warn "$Id app pack is missing: $PackagePath"
            }
        } elseif ($Entry.sha256) {
            $Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $PackagePath).Hash.ToLowerInvariant()
            if ($Hash -ne [string]$Entry.sha256) {
                $Finding = New-Finding -AppId $Id -Path $PackagePath -Message "App Pack sha256 mismatch" -Recommendation "Regenerate the App Pack or update sha256 through the packaging script."
                Add-ListItem $Report "sha256_mismatch" $Finding
                Mark-Fail "$Id app pack sha256 mismatch: $PackagePath"
            }
        }
    }
}

foreach ($SourceId in $SourceIds) {
    if ($ManifestIds -notcontains $SourceId) {
        $AppYamlPath = Join-Path (Join-Path $AppsDir $SourceId) "app.yaml"
        $Finding = New-Finding -AppId $SourceId -Path $AppYamlPath -Message "apps/<app_id>/app.yaml exists but app_manifest entry is missing" -Recommendation "Add the app to release/app_manifest.json or remove it through a deliberate full-delete flow."
        Add-ListItem $Report "apps_missing_from_manifest" $Finding
        Mark-Warn "$SourceId exists in apps/ but is missing from release/app_manifest.json"
    }
}

Write-Line ""
Write-Line "== App manifest consistency summary =="
Write-Line "manifest entries: $($Report.manifest_entry_count)"
Write-Line "app sources: $($Report.app_source_count)"
Write-Line "enabled apps: $(@($Report.enabled_apps).Count)"
Write-Line "disabled apps with source: $(@($Report.disabled_apps_with_source).Count)"
Write-Line "disabled stale entries: $(@($Report.disabled_stale_entries).Count)"
Write-Line "enabled missing source: $(@($Report.enabled_missing_source).Count)"
Write-Line "apps missing from manifest: $(@($Report.apps_missing_from_manifest).Count)"
Write-Line "package path missing: $(@($Report.package_path_missing).Count)"
Write-Line "sha256 mismatch: $(@($Report.sha256_mismatch).Count)"

if ($Json) {
    $Report | ConvertTo-Json -Depth 12
}

if ($Failed) {
    exit 1
}
exit 0
