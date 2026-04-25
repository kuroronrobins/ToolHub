param(
    [string]$Python = "python",
    [switch]$Strict
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Failed = $false

function Pass($Message) { Write-Host "[OK] $Message" }
function Warn($Message) {
    if ($Strict) {
        Fail $Message
    } else {
        Write-Host "[WARN] $Message"
    }
}
function Fail($Message) {
    Write-Host "[NG] $Message"
    $script:Failed = $true
}
function Skip($Message) { Write-Host "[SKIP] $Message" }

function Run-Step {
    param(
        [string]$Name,
        [scriptblock]$Script,
        [switch]$Optional
    )
    Write-Host ""
    Write-Host "== $Name =="
    & $Script
    $ExitCode = $LASTEXITCODE
    if ($ExitCode -eq 0 -or $null -eq $ExitCode) {
        Pass $Name
        return
    }
    if ($Optional -or -not $Strict) {
        Warn "$Name failed with exit code $ExitCode"
    } else {
        Fail "$Name failed with exit code $ExitCode"
    }
}

function Test-JsonFile {
    param([string]$Path)
    try {
        Get-Content -Raw -Encoding UTF8 $Path | ConvertFrom-Json | Out-Null
        Pass "JSON valid: $Path"
    } catch {
        Fail "JSON invalid: $Path"
    }
}

function Require-Path {
    param(
        [string]$Path,
        [switch]$Optional
    )
    if (Test-Path -LiteralPath $Path) {
        Pass "Exists: $Path"
    } elseif ($Optional -or -not $Strict) {
        Warn "Missing: $Path"
    } else {
        Fail "Missing: $Path"
    }
}

function Test-TauriIconAssets {
    $IconPath = "launcher/src-tauri/icons/icon.ico"
    if (-not (Test-Path -LiteralPath $IconPath -PathType Leaf)) {
        Warn "Missing Tauri Windows icon: $IconPath. Tauri build requires this file; commit it so a fresh clone can build."
        return
    }

    Pass "Tauri Windows icon exists: $IconPath"

    try {
        $Bytes = [System.IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $IconPath).Path)
        if ($Bytes.Length -lt 6) {
            Warn "Tauri Windows icon is too small to be a valid ICO file: $IconPath"
            return
        }

        $Reserved = [BitConverter]::ToUInt16($Bytes, 0)
        $Type = [BitConverter]::ToUInt16($Bytes, 2)
        $Count = [BitConverter]::ToUInt16($Bytes, 4)
        if ($Reserved -eq 0 -and $Type -eq 1 -and $Count -gt 0) {
            Pass "Tauri Windows icon has a valid ICO header"
        } else {
            Warn "Tauri Windows icon is not a valid ICO file: $IconPath"
        }
    } catch {
        Warn "Tauri Windows icon could not be validated: $IconPath"
    }

    $PngPath = "launcher/src-tauri/icons/icon.png"
    if (Test-Path -LiteralPath $PngPath -PathType Leaf) {
        Pass "Tauri PNG icon exists: $PngPath"
    }
}

function Test-TauriBundleResources {
    param(
        [string]$ConfigPath,
        [object[]]$Resources,
        [string]$Label = "bundle resource"
    )

    $ConfigDir = Split-Path -Parent $ConfigPath
    if (-not $Resources -or $Resources.Count -eq 0) {
        Warn "Tauri $Label list is empty."
        return
    }

    foreach ($Resource in $Resources) {
        if (-not $Resource) {
            continue
        }

        $ResourceText = [string]$Resource
        if ([System.IO.Path]::IsPathRooted($ResourceText)) {
            $ResourcePath = $ResourceText
        } else {
            $ResourcePath = Join-Path $ConfigDir $ResourceText
        }

        if (Test-Path -LiteralPath $ResourcePath) {
            Pass "Tauri $Label exists: $ResourceText"
        } else {
            Warn "Tauri $Label missing: $ResourceText ($ResourcePath)"
        }
    }
}

function Test-Tool {
    param(
        [string]$Name,
        [string]$InstallHint
    )
    $Command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($Command) {
        Pass "$Name found: $($Command.Source)"
        return $true
    }
    Warn "$Name was not found. $InstallHint"
    return $false
}

function Test-MsvcToolchain {
    $Link = Get-Command "link.exe" -ErrorAction SilentlyContinue
    $Cl = Get-Command "cl.exe" -ErrorAction SilentlyContinue
    if ($Link) { Pass "link.exe found: $($Link.Source)" } else {
        Warn "Visual Studio C++ linker link.exe was not found. Tauri/Rust Windows builds require Visual Studio Build Tools, Desktop development with C++, MSVC v143 or later, and Windows SDK."
    }
    if ($Cl) { Pass "cl.exe found: $($Cl.Source)" } else {
        Warn "Visual Studio C++ compiler cl.exe was not found. Open a Developer PowerShell or install Visual Studio Build Tools with C++ tools."
    }

    $ProgramFilesX86 = ${env:ProgramFiles(x86)}
    $VsWhere = if ($ProgramFilesX86) { Join-Path $ProgramFilesX86 "Microsoft Visual Studio\Installer\vswhere.exe" } else { $null }
    if ($VsWhere -and (Test-Path -LiteralPath $VsWhere -PathType Leaf)) {
        $VsInfo = & $VsWhere -latest -requires Microsoft.VisualStudio.Workload.VCTools -property installationPath 2>$null
        if ($LASTEXITCODE -eq 0 -and $VsInfo) {
            Pass "Visual Studio Build Tools with C++ workload detected: $VsInfo"
        } else {
            Warn "Visual Studio Build Tools was found, but the C++ workload was not detected."
        }
    } else {
        Warn "vswhere.exe was not found. Visual Studio Build Tools may be missing."
    }
}

function Test-TauriBundleConfig {
    $ConfigPath = "launcher/src-tauri/tauri.conf.json"
    if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
        Fail "Tauri config is missing: $ConfigPath"
        return
    }
    try {
        $Config = Get-Content -Raw -Encoding UTF8 $ConfigPath | ConvertFrom-Json
        if ($Config.productName -eq "ToolHub") { Pass "Tauri productName is ToolHub" } else { Warn "Tauri productName is not ToolHub" }
        if ($Config.bundle.active -eq $true) { Pass "Tauri bundle is active" } else { Fail "Tauri bundle.active must be true" }
        $Targets = @($Config.bundle.targets)
        if ($Targets -contains "nsis" -or $Targets -contains "msi") {
            Pass "Tauri bundle target includes NSIS or MSI"
        } else {
            Fail "Tauri bundle targets should include nsis or msi"
        }
        Test-TauriBundleResources -ConfigPath $ConfigPath -Resources @($Config.bundle.icon) -Label "bundle icon"
        Test-TauriBundleResources -ConfigPath $ConfigPath -Resources @($Config.bundle.resources) -Label "bundle resource"
    } catch {
        Fail "Tauri config could not be parsed"
    }
}

Push-Location $Root
try {
    Write-Host "== Build environment =="
    Test-Tool -Name "node" -InstallHint "Install Node.js LTS." | Out-Null
    Test-Tool -Name "npm" -InstallHint "Install Node.js LTS with npm." | Out-Null
    Test-Tool -Name "cargo" -InstallHint "Install Rust with rustup." | Out-Null
    Test-Tool -Name "rustc" -InstallHint "Install Rust with rustup." | Out-Null
    Test-MsvcToolchain

    Write-Host ""
    Write-Host "== Project structure =="
    Require-Path "launcher/package.json"
    Require-Path "launcher/node_modules" -Optional
    Require-Path "launcher/package-lock.json"
    Require-Path "launcher/src-tauri/Cargo.toml"
    Require-Path "launcher/src-tauri/Cargo.lock"
    Test-TauriIconAssets
    Require-Path "scripts/package_installer.ps1"
    Require-Path "scripts/package_app_pack.ps1"
    Require-Path "scripts/prepare_runtime.ps1"
    Require-Path "scripts/verify_release.ps1"
    Require-Path "docs/07_installer_distribution.md"
    Require-Path "docs/08_update_design.md"
    Require-Path "docs/09_app_pack_spec.md"
    Require-Path "docs/10_runtime_packaging.md"
    Require-Path "runtime/README.md" -Optional
    Require-Path "config.default/launcher.yaml"
    Test-TauriBundleConfig

    Write-Host ""
    Write-Host "== npm script checks =="
    try {
        $Package = Get-Content -Raw -Encoding UTF8 "launcher/package.json" | ConvertFrom-Json
        if ($Package.scripts.tauri) { Pass "npm run tauri is configured" } else { Fail "npm run tauri is not configured" }
        if ($Package.scripts.typecheck) { Pass "npm run typecheck is configured" } else { Warn "npm run typecheck is not configured" }
    } catch {
        Fail "launcher/package.json could not be parsed"
    }

    Write-Host ""
    Write-Host "== Release JSON =="
    Test-JsonFile "release/manifest.json"
    Test-JsonFile "release/app_manifest.json"

    Run-Step "Bootstrap environment check" {
        & $Python "main.py" "--check"
    } -Optional

    Run-Step "main.py py_compile" {
        & $Python "-m" "py_compile" "main.py"
    }

    Run-Step "Python runner tests" {
        & $Python "-m" "unittest" "discover" "-s" "runner/tests"
    }

    Run-Step "Release manifest verification" {
        & ".\scripts\verify_release.ps1"
    } -Optional

    Write-Host ""
    Write-Host "== App manifest version checks =="
    $AppManifest = Get-Content -Raw -Encoding UTF8 "release/app_manifest.json" | ConvertFrom-Json
    foreach ($Prop in $AppManifest.apps.PSObject.Properties) {
        $Id = $Prop.Name
        $AppYaml = Join-Path "apps" (Join-Path $Id "app.yaml")
        if (-not (Test-Path -LiteralPath $AppYaml -PathType Leaf)) {
            Fail "Missing app.yaml for $Id"
            continue
        }
        $Text = Get-Content -Raw -Encoding UTF8 $AppYaml
        if ($Text -match "version:\s*['""]?$([regex]::Escape([string]$Prop.Value.version))['""]?") {
            Pass "$Id app.yaml version matches app_manifest"
        } else {
            Warn "$Id app.yaml admin.version was not matched to app_manifest version"
        }
        if ($Prop.Value.package) { Pass "$Id app pack target: $($Prop.Value.package)" } else { Fail "$Id app pack target is missing" }
    }

    Write-Host ""
    Write-Host "== main.py static boundary check =="
    $MainText = (Get-Content -Raw -Encoding UTF8 "main.py").ToLowerInvariant()
    foreach ($Pattern in @("playwright", "app_pack", "package_installer", "browser_profiles", "app.yaml")) {
        if ($MainText.Contains($Pattern)) {
            Warn "main.py contains '$Pattern'. Review whether bootstrap boundary is still clean."
        } else {
            Pass "main.py does not contain '$Pattern'"
        }
    }

    Run-Step "Frontend checks" {
        & ".\scripts\frontend_check.ps1"
    } -Optional

    if (Get-Command cargo -ErrorAction SilentlyContinue) {
        Run-Step "Rust check" {
            Push-Location "launcher/src-tauri"
            try { & cargo "check" } finally { Pop-Location }
        } -Optional
    } else {
        Skip "Rust check: cargo was not found."
    }
}
finally {
    Pop-Location
}

if ($Failed) {
    exit 1
}
exit 0
