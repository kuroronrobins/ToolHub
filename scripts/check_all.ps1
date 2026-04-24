param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Failed = $false

function Run-Step {
    param(
        [string]$Name,
        [scriptblock]$Script,
        [string]$Level = "Required"
    )
    Write-Host ""
    Write-Host "== $Name =="
    & $Script
    if ($LASTEXITCODE -ne 0) {
        if ($Level -eq "Required") {
            Write-Host "[NG] $Name failed with exit code $LASTEXITCODE"
            $script:Failed = $true
        } else {
            Write-Host "[WARN] $Name finished with exit code $LASTEXITCODE"
        }
    } else {
        Write-Host "[OK] $Name"
    }
}

function Test-JsonFile {
    param([string]$Path)
    try {
        Get-Content -Raw -Encoding UTF8 $Path | ConvertFrom-Json | Out-Null
        Write-Host "[OK] JSON valid: $Path"
    } catch {
        Write-Host "[NG] JSON invalid: $Path"
        $script:Failed = $true
    }
}

function Require-Path {
    param([string]$Path)
    if (Test-Path $Path) {
        Write-Host "[OK] Exists: $Path"
    } else {
        Write-Host "[NG] Missing: $Path"
        $script:Failed = $true
    }
}

Push-Location $Root
try {
    Run-Step "Bootstrap environment check" {
        & $Python "main.py" "--check"
    } "Optional"

    Run-Step "Python runner tests" {
        & $Python "-m" "unittest" "discover" "-s" "runner/tests"
    }

    Write-Host ""
    Write-Host "== Release structure checks =="
    Test-JsonFile "release/manifest.json"
    Test-JsonFile "release/app_manifest.json"
    Require-Path "scripts/package_installer.ps1"
    Require-Path "scripts/package_app_pack.ps1"
    Require-Path "scripts/verify_release.ps1"
    Require-Path "docs/07_installer_distribution.md"
    Require-Path "docs/08_update_design.md"
    Require-Path "docs/09_app_pack_spec.md"
    Require-Path "docs/10_runtime_packaging.md"
    Require-Path "runtime/README.md"
    Require-Path "config.default/launcher.yaml"

    Run-Step "Release manifest verification" {
        & ".\scripts\verify_release.ps1"
    } "Optional"

    Write-Host ""
    Write-Host "== App manifest version checks =="
    $AppManifest = Get-Content -Raw -Encoding UTF8 "release/app_manifest.json" | ConvertFrom-Json
    foreach ($Prop in $AppManifest.apps.PSObject.Properties) {
        $Id = $Prop.Name
        $AppYaml = Join-Path "apps" (Join-Path $Id "app.yaml")
        if (-not (Test-Path $AppYaml)) {
            Write-Host "[NG] Missing app.yaml for $Id"
            $Failed = $true
            continue
        }
        $Text = Get-Content -Raw -Encoding UTF8 $AppYaml
        if ($Text -match "version:\s*['""]?$([regex]::Escape([string]$Prop.Value.version))['""]?") {
            Write-Host "[OK] $Id app.yaml version matches app_manifest"
        } else {
            Write-Host "[WARN] $Id app.yaml admin.version was not matched to app_manifest version"
        }
        if ($Prop.Value.package) {
            Write-Host "[OK] $Id app pack target: $($Prop.Value.package)"
        } else {
            Write-Host "[NG] $Id app pack target is missing"
            $Failed = $true
        }
    }

    Write-Host ""
    Write-Host "== main.py static boundary check =="
    $MainText = Get-Content -Raw -Encoding UTF8 "main.py"
    $Forbidden = @("playwright", "app_pack", "package_installer", "browser_profiles", "app.yaml")
    foreach ($Pattern in $Forbidden) {
        if ($MainText.ToLowerInvariant().Contains($Pattern)) {
            Write-Host "[WARN] main.py contains '$Pattern'. Review whether bootstrap boundary is still clean."
        } else {
            Write-Host "[OK] main.py does not contain '$Pattern'"
        }
    }

    if (Get-Command npm -ErrorAction SilentlyContinue) {
        if (Test-Path "launcher/node_modules") {
            Run-Step "TypeScript tests" {
                Push-Location "launcher"
                try { & npm "test" } finally { Pop-Location }
            } "Optional"
            Run-Step "TypeScript build" {
                Push-Location "launcher"
                try { & npm "run" "build" } finally { Pop-Location }
            } "Optional"
        } else {
            Write-Host ""
            Write-Host "[SKIP] TypeScript checks: launcher/node_modules is missing. Run npm install in launcher first."
        }
    } else {
        Write-Host ""
        Write-Host "[SKIP] TypeScript checks: npm was not found."
    }

    if (Get-Command cargo -ErrorAction SilentlyContinue) {
        Run-Step "Rust check" {
            Push-Location "launcher/src-tauri"
            try { & cargo "check" } finally { Pop-Location }
        } "Optional"
    } else {
        Write-Host ""
        Write-Host "[SKIP] Rust check: cargo was not found."
    }
}
finally {
    Pop-Location
}

if ($Failed) {
    exit 1
}
exit 0
