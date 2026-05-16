param(
    [string]$SourceRoot = ".",
    [string]$ActiveRoot,
    [string]$AppId,
    [switch]$Json
)

$ErrorActionPreference = "Stop"

function Resolve-ExistingPath {
    param([string]$PathValue)
    if ([string]::IsNullOrWhiteSpace($PathValue)) {
        return $null
    }
    $item = Get-Item -LiteralPath $PathValue -ErrorAction Stop
    return $item.FullName
}

function Get-RootType {
    param([string]$Root)
    $normalized = $Root.ToLowerInvariant() -replace "/", "\"
    if ($normalized -match "\\launcher\\src-tauri\\target\\(release|debug)$") {
        return "dev_build_artifact"
    }
    if (Test-Path -LiteralPath (Join-Path $Root "launcher") -PathType Container) {
        return "dev_source"
    }
    $leaf = Split-Path -Leaf $Root
    $dataLogs = Join-Path $Root "data\logs"
    $config = Join-Path $Root "config"
    if ($leaf -ieq "ToolHub" -and (Test-Path -LiteralPath $dataLogs -PathType Container) -and (Test-Path -LiteralPath $config -PathType Container)) {
        return "user_data"
    }
    $apps = Join-Path $Root "apps"
    $runner = Join-Path $Root "runner"
    $appManifest = Join-Path $Root "release\app_manifest.json"
    $releaseManifest = Join-Path $Root "release\manifest.json"
    if ((Test-Path -LiteralPath $apps -PathType Container) -and (Test-Path -LiteralPath $runner -PathType Container) -and ((Test-Path -LiteralPath $appManifest -PathType Leaf) -or (Test-Path -LiteralPath $releaseManifest -PathType Leaf))) {
        return "installed_resource"
    }
    return "unknown"
}

function Get-FileSha256 {
    param([string]$PathValue)
    if (-not (Test-Path -LiteralPath $PathValue -PathType Leaf)) {
        return $null
    }
    return (Get-FileHash -LiteralPath $PathValue -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Read-RunFields {
    param([string]$ManifestPath)
    $result = [ordered]@{
        runner = $null
        entry = $null
        mode = $null
    }
    if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
        return [pscustomobject]$result
    }

    $inRun = $false
    foreach ($line in Get-Content -LiteralPath $ManifestPath -Encoding UTF8) {
        if ($line -match "^\s*run\s*:\s*$") {
            $inRun = $true
            continue
        }
        if ($inRun -and $line -match "^\S") {
            break
        }
        if (-not $inRun) {
            continue
        }
        if ($line -match "^\s+runner\s*:\s*(.+?)\s*$") {
            $result.runner = $Matches[1].Trim().Trim('"').Trim("'")
            continue
        }
        if ($line -match "^\s+entry\s*:\s*(.+?)\s*$") {
            $result.entry = $Matches[1].Trim().Trim('"').Trim("'")
            continue
        }
        if ($line -match "^\s+mode\s*:\s*(.+?)\s*$") {
            $result.mode = $Matches[1].Trim().Trim('"').Trim("'")
            continue
        }
    }
    return [pscustomobject]$result
}

function Get-AppIds {
    param([string[]]$Roots)
    $ids = New-Object System.Collections.Generic.HashSet[string]
    foreach ($root in $Roots) {
        if ([string]::IsNullOrWhiteSpace($root)) {
            continue
        }
        $appsDir = Join-Path $root "apps"
        if (-not (Test-Path -LiteralPath $appsDir -PathType Container)) {
            continue
        }
        foreach ($dir in Get-ChildItem -LiteralPath $appsDir -Directory) {
            if (Test-Path -LiteralPath (Join-Path $dir.FullName "app.yaml") -PathType Leaf) {
                [void]$ids.Add($dir.Name)
            }
        }
    }
    return @($ids | Sort-Object)
}

function Compare-NullableValue {
    param(
        [string]$Name,
        [object]$Source,
        [object]$Active
    )
    if ($Source -eq $Active) {
        return [pscustomobject]@{ name = $Name; status = "pass"; source = $Source; active = $Active; message = "$Name matches" }
    }
    return [pscustomobject]@{ name = $Name; status = "diff"; source = $Source; active = $Active; message = "$Name differs" }
}

$sourceFull = Resolve-ExistingPath $SourceRoot
if (-not $ActiveRoot) {
    $ActiveRoot = Join-Path $sourceFull "launcher\src-tauri\target\release"
}
$activeFull = Resolve-ExistingPath $ActiveRoot

$sourceType = Get-RootType $sourceFull
$activeType = Get-RootType $activeFull

if ($AppId) {
    $appIds = @($AppId)
} else {
    $appIds = Get-AppIds -Roots @($sourceFull, $activeFull)
}

$sourceRunner = Join-Path $sourceFull "runner\toolhub_runner\main.py"
$activeRunner = Join-Path $activeFull "runner\toolhub_runner\main.py"
$sourceStudio = Join-Path $sourceFull "tools\app_studio\main.py"
$activeStudio = Join-Path $activeFull "tools\app_studio\main.py"

$results = New-Object System.Collections.Generic.List[object]
$results.Add([pscustomobject]@{
    scope = "root"
    name = "source_root_type"
    status = if ($sourceType -eq "dev_source") { "pass" } else { "warning" }
    source = $sourceType
    active = $sourceFull
    message = "source root classified as $sourceType"
}) | Out-Null
$results.Add([pscustomobject]@{
    scope = "root"
    name = "active_root_type"
    status = if ($activeType -eq "dev_build_artifact") { "warning" } else { "pass" }
    source = $activeType
    active = $activeFull
    message = "active root classified as $activeType"
}) | Out-Null

foreach ($comparison in @(
    (Compare-NullableValue "runner_main_sha256" (Get-FileSha256 $sourceRunner) (Get-FileSha256 $activeRunner)),
    (Compare-NullableValue "app_studio_main_sha256" (Get-FileSha256 $sourceStudio) (Get-FileSha256 $activeStudio))
)) {
    $status = $comparison.status
    if ($status -eq "diff") {
        if (($comparison.name -eq "runner_main_sha256") -and ($activeType -eq "dev_build_artifact")) {
            $status = "fail"
        } else {
            $status = "warning"
        }
    }
    $results.Add([pscustomobject]@{
        scope = "toolhub"
        name = $comparison.name
        status = $status
        source = $comparison.source
        active = $comparison.active
        message = $comparison.message
    }) | Out-Null
}

foreach ($id in $appIds) {
    $sourceManifest = Join-Path $sourceFull "apps\$id\app.yaml"
    $activeManifest = Join-Path $activeFull "apps\$id\app.yaml"
    $sourceRun = Read-RunFields $sourceManifest
    $activeRun = Read-RunFields $activeManifest

    foreach ($comparison in @(
        (Compare-NullableValue "app_yaml_sha256" (Get-FileSha256 $sourceManifest) (Get-FileSha256 $activeManifest)),
        (Compare-NullableValue "run.runner" $sourceRun.runner $activeRun.runner),
        (Compare-NullableValue "run.entry" $sourceRun.entry $activeRun.entry),
        (Compare-NullableValue "run.mode" $sourceRun.mode $activeRun.mode)
    )) {
        $status = $comparison.status
        if ($status -eq "diff") {
            $status = if ($activeType -eq "dev_build_artifact") { "fail" } else { "warning" }
        }
        if (($comparison.name -eq "app_yaml_sha256") -and (-not $comparison.source -or -not $comparison.active)) {
            $status = "fail"
        }
        $results.Add([pscustomobject]@{
            scope = "app"
            appId = $id
            name = $comparison.name
            status = $status
            source = $comparison.source
            active = $comparison.active
            message = $comparison.message
        }) | Out-Null
    }
}

$summary = [ordered]@{
    sourceRoot = $sourceFull
    sourceRootType = $sourceType
    activeRoot = $activeFull
    activeRootType = $activeType
    appIds = @($appIds)
    results = @($results.ToArray())
}

if ($Json) {
    $summary | ConvertTo-Json -Depth 6
} else {
    Write-Host "ToolHub active root staleness diagnostics"
    Write-Host "Source: $sourceFull [$sourceType]"
    Write-Host "Active: $activeFull [$activeType]"
    foreach ($result in $results) {
        $prefix = switch ($result.status) {
            "pass" { "[OK]" }
            "warning" { "[WARN]" }
            "fail" { "[NG]" }
            default { "[INFO]" }
        }
        $subject = $result.name
        if ($result.appId) {
            $subject = "$($result.appId) $subject"
        }
        Write-Host "$prefix $subject - $($result.message)"
        if ($result.status -ne "pass") {
            Write-Host "      source: $($result.source)"
            Write-Host "      active: $($result.active)"
        }
    }
}

$hasFail = @($results | Where-Object { $_.status -eq "fail" }).Count -gt 0
if ($hasFail) {
    exit 1
}
exit 0
