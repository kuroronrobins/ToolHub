param(
    [string]$SourceArchive,
    [string]$SourceSha256,
    [switch]$SkipPython,
    [switch]$SkipWebRuntime,
    [switch]$AllowMissingRuntime
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RuntimeDir = Join-Path $Root "runtime"
$PythonDir = Join-Path $RuntimeDir "python"
$AppEnvsDir = Join-Path $RuntimeDir "app_envs"
$WebRuntimeDir = Join-Path $RuntimeDir "web_automation_runtime"
$AppsDir = Join-Path $Root "apps"

function Assert-InRoot {
    param([string]$Path)
    $Full = [System.IO.Path]::GetFullPath($Path)
    if (-not $Full.StartsWith($Root, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing path outside workspace: $Full"
    }
    return $Full
}

function Ensure-Directory {
    param([string]$Path)
    $Full = Assert-InRoot $Path
    New-Item -ItemType Directory -Force -Path $Full | Out-Null
    return $Full
}

function Touch-GitKeep {
    param([string]$Path)
    $GitKeep = Join-Path $Path ".gitkeep"
    if (-not (Test-Path -LiteralPath $GitKeep -PathType Leaf)) {
        New-Item -ItemType File -Path $GitKeep | Out-Null
    }
}

function Expand-ArchiveIfProvided {
    param(
        [string]$Archive,
        [string]$ExpectedSha256,
        [string]$Destination
    )
    if ([string]::IsNullOrWhiteSpace($Archive)) {
        return $false
    }
    if (-not (Test-Path -LiteralPath $Archive -PathType Leaf)) {
        throw "Runtime source archive was not found: $Archive"
    }
    if (-not [string]::IsNullOrWhiteSpace($ExpectedSha256)) {
        $Actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $Archive).Hash.ToLowerInvariant()
        if ($Actual -ne $ExpectedSha256.ToLowerInvariant()) {
            throw "Runtime source archive sha256 mismatch. expected=$ExpectedSha256 actual=$Actual"
        }
    }
    $Destination = Ensure-Directory $Destination
    Expand-Archive -LiteralPath $Archive -DestinationPath $Destination -Force
    return $true
}

Ensure-Directory $RuntimeDir | Out-Null
Ensure-Directory $PythonDir | Out-Null
Ensure-Directory $AppEnvsDir | Out-Null
Ensure-Directory $WebRuntimeDir | Out-Null
Touch-GitKeep $PythonDir
Touch-GitKeep $AppEnvsDir
Touch-GitKeep $WebRuntimeDir

$RuntimeReadme = @'
# ToolHub Runtime

This directory is prepared by `scripts/prepare_runtime.ps1`.

Planned release layout:

```text
runtime/
├─ python/
├─ app_envs/
└─ web_automation_runtime/
```

Large runtime artifacts are intentionally not tracked in Git. Place local runtime archives under `vendor/runtime/` or `tools/runtime_sources/` and pass them to `prepare_runtime.ps1 -SourceArchive <path>`.

Default behavior does not download anything from the internet.
'@
$RuntimeReadme | Set-Content -Encoding UTF8 (Join-Path $RuntimeDir "README.md")

if (-not $SkipPython) {
    $Expanded = Expand-ArchiveIfProvided -Archive $SourceArchive -ExpectedSha256 $SourceSha256 -Destination $PythonDir
    $PythonExe = Join-Path $PythonDir "python.exe"
    if (Test-Path -LiteralPath $PythonExe -PathType Leaf) {
        Write-Host "[OK] Python runtime found: $PythonExe"
    } elseif ($Expanded) {
        Write-Host "[WARN] Source archive was expanded, but runtime/python/python.exe was not found."
    } elseif ($AllowMissingRuntime) {
        Write-Host "[WARN] Python runtime is not bundled yet. This is allowed for skeleton packaging."
    } else {
        throw "Python runtime is missing. Pass -AllowMissingRuntime for skeleton packaging."
    }
}

if (Test-Path -LiteralPath $AppsDir -PathType Container) {
    Get-ChildItem -LiteralPath $AppsDir -Directory | ForEach-Object {
        $AppId = $_.Name
        $EnvDir = Ensure-Directory (Join-Path $AppEnvsDir $AppId)
        Touch-GitKeep $EnvDir
        $EnvReadme = @"
# $AppId app environment

This folder is reserved for the per-app runtime environment.

Preferred distribution mode A:
- Put the app-specific Python environment here.
- Use `requirements.lock` to make dependencies reproducible.

Allowed distribution mode B:
- Package the app as an exe and use `run.runner: exe`.
"@
        $EnvReadme | Set-Content -Encoding UTF8 (Join-Path $EnvDir "README.md")
        Write-Host "[OK] Prepared app env skeleton: runtime/app_envs/$AppId"
    }
}

if (-not $SkipWebRuntime) {
    $Marker = Join-Path $WebRuntimeDir "README.md"
    @"
# Web Automation Runtime

This folder is reserved for the runtime required by web-operation apps.

User-facing UI must call this "Web自動化用ランタイム". Internal implementation details may be documented only for administrators.
"@ | Set-Content -Encoding UTF8 $Marker

    $RuntimeFiles = Get-ChildItem -LiteralPath $WebRuntimeDir -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notin @(".gitkeep", "README.md") }
    if ($RuntimeFiles.Count -gt 0) {
        Write-Host "[OK] Web automation runtime files are present."
    } elseif ($AllowMissingRuntime) {
        Write-Host "[WARN] Web automation runtime is not bundled yet. This is allowed for skeleton packaging."
    } else {
        throw "Web automation runtime is missing. Pass -AllowMissingRuntime for skeleton packaging."
    }
}

Write-Host "Runtime preparation completed."
