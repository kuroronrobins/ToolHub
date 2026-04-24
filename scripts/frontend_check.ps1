param(
    [switch]$SkipTests,
    [switch]$SkipBuild,
    [switch]$Strict
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$LauncherDir = Join-Path $Root "launcher"
$Failed = $false

function Write-EpermAdvice {
    Write-Host "[WARN] esbuild or Vite failed with spawn EPERM."
    Write-Host "       Try these checks:"
    Write-Host "       - Run the terminal as administrator once"
    Write-Host "       - Check antivirus/security software quarantine or execution block"
    Write-Host "       - Delete launcher/node_modules and run npm ci"
    Write-Host "       - Move the project outside OneDrive or network-synced folders"
    Write-Host "       - Run npm cache clean --force, then install again"
    Write-Host "       - Reboot the PC and use a Node.js LTS release"
}

function Run-FrontendStep {
    param(
        [string]$Name,
        [string[]]$Command,
        [switch]$Optional
    )
    Write-Host ""
    Write-Host "== $Name =="
    $Executable = $Command[0]
    $Arguments = if ($Command.Length -gt 1) { $Command[1..($Command.Length - 1)] } else { @() }
    $Output = & $Executable @Arguments 2>&1
    $ExitCode = $LASTEXITCODE
    $Output | ForEach-Object { Write-Host $_ }
    if ($ExitCode -eq 0) {
        Write-Host "[OK] $Name"
        return
    }
    $Text = ($Output | Out-String)
    if ($Text -match "EPERM" -or $Text -match "spawn") {
        Write-EpermAdvice
    }
    if ($Optional -or -not $Strict) {
        Write-Host "[WARN] $Name failed with exit code $ExitCode"
    } else {
        Write-Host "[NG] $Name failed with exit code $ExitCode"
        $script:Failed = $true
    }
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Host "[WARN] npm was not found. Install Node.js LTS for frontend checks."
    exit 0
}
if (-not (Test-Path -LiteralPath (Join-Path $LauncherDir "package.json") -PathType Leaf)) {
    Write-Host "[NG] launcher/package.json was not found."
    exit 1
}
if (-not (Test-Path -LiteralPath (Join-Path $LauncherDir "node_modules") -PathType Container)) {
    Write-Host "[WARN] launcher/node_modules is missing. Run npm ci in launcher before frontend checks."
    exit 0
}

Push-Location $LauncherDir
try {
    Run-FrontendStep -Name "TypeScript typecheck" -Command @("npm", "run", "typecheck")
    if (-not $SkipTests) {
        Run-FrontendStep -Name "Vitest" -Command @("npm", "test") -Optional
    }
    if (-not $SkipBuild) {
        Run-FrontendStep -Name "Vite build" -Command @("npm", "run", "build") -Optional
    }
}
finally {
    Pop-Location
}

if ($Failed) {
    exit 1
}
exit 0
