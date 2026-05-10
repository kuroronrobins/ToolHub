param(
    [Alias("SourceArchive")]
    [string]$PythonArchive,
    [Alias("SourceSha256")]
    [string]$PythonSha256,
    [string]$WebRuntimeArchive,
    [string]$WebRuntimeSha256,
    [switch]$SkipPython,
    [switch]$SkipWebRuntime,
    [switch]$CreateAppEnvSkeletons,
    [switch]$AllowMissingRuntime,
    [switch]$CleanDestination,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RuntimeDir = Join-Path $Root "runtime"
$PythonDir = Join-Path $RuntimeDir "python"
$SharedEnvsDir = Join-Path $RuntimeDir "envs"
$AppEnvsDir = Join-Path $RuntimeDir "app_envs"
$WebRuntimeDir = Join-Path $RuntimeDir "web_automation_runtime"
$AppsDir = Join-Path $Root "apps"

function Assert-InRoot {
    param([string]$Path)
    $Full = [System.IO.Path]::GetFullPath($Path)
    $TrimChars = [char[]]@([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)
    $RootWithSlash = $Root.TrimEnd($TrimChars) + [System.IO.Path]::DirectorySeparatorChar
    if (-not ($Full.Equals($Root, [System.StringComparison]::OrdinalIgnoreCase) -or $Full.StartsWith($RootWithSlash, [System.StringComparison]::OrdinalIgnoreCase))) {
        throw "Refusing path outside workspace: $Full"
    }
    return $Full
}

function Ensure-Directory {
    param([string]$Path)
    $Full = Assert-InRoot $Path
    if ($DryRun) {
        Write-Host "[DRYRUN] ensure directory: $Full"
    } else {
        New-Item -ItemType Directory -Force -Path $Full | Out-Null
    }
    return $Full
}

function Touch-GitKeep {
    param([string]$Path)
    $GitKeep = Join-Path $Path ".gitkeep"
    if ($DryRun) {
        Write-Host "[DRYRUN] ensure .gitkeep: $GitKeep"
        return
    }
    if (-not (Test-Path -LiteralPath $GitKeep -PathType Leaf)) {
        New-Item -ItemType File -Path $GitKeep | Out-Null
    }
}

function Set-TextFile {
    param(
        [string]$Path,
        [string]$Content
    )
    $Full = Assert-InRoot $Path
    if ($DryRun) {
        Write-Host "[DRYRUN] write text file: $Full"
        return
    }
    $Content | Set-Content -Encoding UTF8 $Full
}

function Resolve-ArchivePath {
    param([string]$Archive)
    if ([string]::IsNullOrWhiteSpace($Archive)) {
        return $null
    }
    if (-not (Test-Path -LiteralPath $Archive -PathType Leaf)) {
        throw "Runtime archive was not found: $Archive"
    }
    return (Resolve-Path -LiteralPath $Archive).Path
}

function Assert-ArchiveHash {
    param(
        [string]$Archive,
        [string]$ExpectedSha256
    )
    if ([string]::IsNullOrWhiteSpace($ExpectedSha256)) {
        Write-Host "[WARN] No sha256 was provided for archive: $Archive"
        return
    }
    $Actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $Archive).Hash.ToLowerInvariant()
    if ($Actual -ne $ExpectedSha256.ToLowerInvariant()) {
        throw "Runtime archive sha256 mismatch. archive=$Archive expected=$ExpectedSha256 actual=$Actual"
    }
    Write-Host "[OK] Archive sha256 matches: $Archive"
}

function Clear-Destination {
    param([string]$Destination)
    $Full = Assert-InRoot $Destination
    if (-not (Test-Path -LiteralPath $Full -PathType Container)) {
        return
    }
    $Children = @(Get-ChildItem -LiteralPath $Full -Force)
    if ($Children.Count -eq 0) {
        return
    }
    if ($DryRun) {
        foreach ($Child in $Children) {
            Write-Host "[DRYRUN] remove existing runtime item: $($Child.FullName)"
        }
        return
    }
    foreach ($Child in $Children) {
        Remove-Item -LiteralPath $Child.FullName -Recurse -Force
    }
}

function Expand-ZipSafe {
    param(
        [string]$Archive,
        [string]$ExpectedSha256,
        [string]$Destination,
        [string]$Label
    )
    $ArchivePath = Resolve-ArchivePath $Archive
    if ($null -eq $ArchivePath) {
        return $false
    }

    Assert-ArchiveHash -Archive $ArchivePath -ExpectedSha256 $ExpectedSha256
    $DestinationFull = Ensure-Directory $Destination
    $DestinationPrefix = $DestinationFull.TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $Zip = [System.IO.Compression.ZipFile]::OpenRead($ArchivePath)
    try {
        foreach ($Entry in $Zip.Entries) {
            if ([string]::IsNullOrWhiteSpace($Entry.FullName)) {
                continue
            }
            $TargetPath = [System.IO.Path]::GetFullPath((Join-Path $DestinationFull $Entry.FullName))
            if (-not ($TargetPath.Equals($DestinationFull, [System.StringComparison]::OrdinalIgnoreCase) -or $TargetPath.StartsWith($DestinationPrefix, [System.StringComparison]::OrdinalIgnoreCase))) {
                throw "Archive entry escapes runtime destination: $($Entry.FullName)"
            }
        }

        if ($CleanDestination) {
            Clear-Destination $DestinationFull
            Ensure-Directory $DestinationFull | Out-Null
        }

        foreach ($Entry in $Zip.Entries) {
            if ([string]::IsNullOrWhiteSpace($Entry.FullName)) {
                continue
            }
            $TargetPath = [System.IO.Path]::GetFullPath((Join-Path $DestinationFull $Entry.FullName))
            if ($Entry.FullName.EndsWith("/") -or $Entry.FullName.EndsWith("\")) {
                if ($DryRun) {
                    Write-Host "[DRYRUN] extract directory: $TargetPath"
                } else {
                    New-Item -ItemType Directory -Force -Path $TargetPath | Out-Null
                }
                continue
            }
            $TargetDir = Split-Path -Parent $TargetPath
            if ($DryRun) {
                Write-Host "[DRYRUN] extract file: $TargetPath"
                continue
            }
            New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null
            $InStream = $Entry.Open()
            try {
                $OutStream = [System.IO.File]::Create($TargetPath)
                try {
                    $InStream.CopyTo($OutStream)
                } finally {
                    $OutStream.Dispose()
                }
            } finally {
                $InStream.Dispose()
            }
        }
    } finally {
        $Zip.Dispose()
    }

    Write-Host "[OK] Expanded $Label archive to $(Split-Path -Leaf $DestinationFull)"
    return $true
}

function Get-NonPlaceholderItems {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        return @()
    }
    return @(Get-ChildItem -LiteralPath $Path -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notin @(".gitkeep", "README.md") })
}

Ensure-Directory $RuntimeDir | Out-Null
Ensure-Directory $PythonDir | Out-Null
Ensure-Directory $SharedEnvsDir | Out-Null
Ensure-Directory $AppEnvsDir | Out-Null
Ensure-Directory $WebRuntimeDir | Out-Null
Touch-GitKeep $PythonDir
Touch-GitKeep $SharedEnvsDir
Touch-GitKeep $AppEnvsDir
Touch-GitKeep $WebRuntimeDir

$RuntimeReadme = @'
# ToolHub Runtime

This directory is prepared by `scripts/prepare_runtime.ps1`.

Planned release layout:

```text
runtime/
|- python/
|- envs/
|- app_envs/
`- web_automation_runtime/
```

Large runtime artifacts are intentionally not tracked in Git. Place approved local runtime archives under
`vendor/runtime/`, `tools/runtime_sources/`, or another internal location and pass them explicitly:

```powershell
.\scripts\prepare_runtime.ps1 -PythonArchive <python.zip> -PythonSha256 <sha256>
.\scripts\prepare_runtime.ps1 -WebRuntimeArchive <web-runtime.zip> -WebRuntimeSha256 <sha256>
```

Default behavior does not download anything from the internet. Normal shared-env apps store versioned
runtime environments under `runtime/envs/<env_id>` and do not require
`runtime/app_envs/<app_id>`; create compatibility skeletons only with `-CreateAppEnvSkeletons`.
'@
Set-TextFile -Path (Join-Path $RuntimeDir "README.md") -Content $RuntimeReadme

if (-not [string]::IsNullOrWhiteSpace($PythonSha256) -and [string]::IsNullOrWhiteSpace($PythonArchive)) {
    throw "-PythonSha256 requires -PythonArchive."
}
if (-not [string]::IsNullOrWhiteSpace($WebRuntimeSha256) -and [string]::IsNullOrWhiteSpace($WebRuntimeArchive)) {
    throw "-WebRuntimeSha256 requires -WebRuntimeArchive."
}

if (-not $SkipPython) {
    $Expanded = Expand-ZipSafe -Archive $PythonArchive -ExpectedSha256 $PythonSha256 -Destination $PythonDir -Label "Python runtime"
    Touch-GitKeep $PythonDir
    $PythonExe = Join-Path $PythonDir "python.exe"
    if (Test-Path -LiteralPath $PythonExe -PathType Leaf) {
        Write-Host "[OK] Python runtime found: $PythonExe"
    } elseif ($Expanded) {
        Write-Host "[WARN] Python archive was expanded, but runtime/python/python.exe was not found."
    } elseif ($AllowMissingRuntime) {
        Write-Host "[WARN] Python runtime is not bundled yet. Provide -PythonArchive and -PythonSha256 when an approved archive is available."
    } else {
        throw "Python runtime is missing. Pass -AllowMissingRuntime for skeleton packaging or provide -PythonArchive."
    }
}

if ($CreateAppEnvSkeletons) {
    if (Test-Path -LiteralPath $AppsDir -PathType Container) {
        Get-ChildItem -LiteralPath $AppsDir -Directory | Sort-Object Name | ForEach-Object {
            $AppId = $_.Name
            $AppYaml = Join-Path $_.FullName "app.yaml"
            if (Test-Path -LiteralPath $AppYaml -PathType Leaf) {
                $EnvDir = Ensure-Directory (Join-Path $AppEnvsDir $AppId)
                Touch-GitKeep $EnvDir
                $EnvReadme = @"
# $AppId app environment

This folder is reserved for a legacy per-app runtime environment.

Normal App Studio registration uses runtime/envs/<env_id> and does not use this directory at runtime.
"@
                Set-TextFile -Path (Join-Path $EnvDir "README.md") -Content $EnvReadme
                Write-Host "[OK] Prepared app env skeleton: runtime/app_envs/$AppId"
            }
        }
    }
} else {
    Write-Host "[INFO] App env skeleton creation skipped. Normal shared-env apps do not require runtime/app_envs/<app_id>."
}

if (-not $SkipWebRuntime) {
    $WebExpanded = Expand-ZipSafe -Archive $WebRuntimeArchive -ExpectedSha256 $WebRuntimeSha256 -Destination $WebRuntimeDir -Label "Web automation runtime"
    Touch-GitKeep $WebRuntimeDir
    $WebRuntimeReadme = @'
# Web Automation Runtime

This folder is reserved for approved web automation runtime files. Runtime files are intentionally not tracked in Git.
'@
    Set-TextFile -Path (Join-Path $WebRuntimeDir "README.md") -Content $WebRuntimeReadme

    $RuntimeFiles = Get-NonPlaceholderItems $WebRuntimeDir
    if ($RuntimeFiles.Count -gt 0) {
        Write-Host "[OK] Web automation runtime files are present."
    } elseif ($WebExpanded) {
        Write-Host "[WARN] Web runtime archive was expanded, but no non-placeholder runtime files were found."
    } elseif ($AllowMissingRuntime) {
        Write-Host "[WARN] Web automation runtime is not bundled yet. Provide -WebRuntimeArchive and -WebRuntimeSha256 when an approved archive is available."
    } else {
        throw "Web automation runtime is missing. Pass -AllowMissingRuntime for skeleton packaging or provide -WebRuntimeArchive."
    }
}

Write-Host "Runtime preparation completed."
