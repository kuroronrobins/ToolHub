param(
    [switch]$RequireInstaller,
    [switch]$RequireAppPacks,
    [switch]$RequireRuntime,
    [switch]$RequireInstallerSignature,
    [switch]$Strict
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$AppPackContractHelperPath = Join-Path $PSScriptRoot "lib\app_pack_contract.ps1"
if (-not (Test-Path -LiteralPath $AppPackContractHelperPath -PathType Leaf)) {
    throw "App Pack contract helper is missing: $AppPackContractHelperPath"
}
. $AppPackContractHelperPath

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ReleaseDir = Join-Path $Root "release"
$ManifestPath = Join-Path $ReleaseDir "manifest.json"
$AppManifestPath = Join-Path $ReleaseDir "app_manifest.json"
$Failed = $false
Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction SilentlyContinue

function Pass($Message) { Write-Host "[OK] $Message" }
function Warn($Message) {
    if ($Strict) {
        Fail $Message
    } else {
        Write-Host "[WARN] $Message"
    }
}
function Fail($Message) { Write-Host "[NG] $Message"; $script:Failed = $true }

function Entry-Enabled {
    param([object]$Entry)
    if ($null -eq $Entry.PSObject.Properties["enabled"]) {
        return $true
    }
    return [bool]$Entry.enabled
}

function Read-Json($Path) {
    try {
        return Get-Content -Raw -Encoding UTF8 $Path | ConvertFrom-Json
    } catch {
        Fail "Invalid JSON: $Path"
        return $null
    }
}

function Require-Directory($Path) {
    if (Test-Path -LiteralPath $Path -PathType Container) { Pass "$Path exists" } else { Fail "$Path is missing" }
}

function Require-File($Path) {
    if (Test-Path -LiteralPath $Path -PathType Leaf) { Pass "$Path exists" } else { Fail "$Path is missing" }
}

function Test-InstallerSignature {
    param([string]$Path)

    $Signature = Get-AuthenticodeSignature -LiteralPath $Path
    if ($Signature.Status -eq "Valid") {
        $Subject = if ($Signature.SignerCertificate) { $Signature.SignerCertificate.Subject } else { "unknown signer" }
        Pass "installer Authenticode signature is valid: $Subject"
        return
    }

    $Message = "installer Authenticode signature is not valid: status=$($Signature.Status)"
    if ($RequireInstallerSignature) {
        Fail $Message
    } else {
        Write-Host "[WARN] $Message"
    }
}

function Test-AppYamlReferencedFile {
    param(
        [string]$AppDir,
        [string]$RelativePath,
        [string]$Label
    )
    try {
        $FullPath = Resolve-AppRelativeFile -AppDir $AppDir -RelativePath $RelativePath -Label $Label
        if (Test-Path -LiteralPath $FullPath -PathType Leaf) {
            Pass "$Label exists"
        } else {
            Fail "$Label is missing: $FullPath"
        }
    } catch {
        Fail $_.Exception.Message
    }
}

function Test-ZipContainsEntry {
    param(
        [string[]]$EntryNames,
        [string]$EntryName,
        [string]$Label
    )
    if ($EntryNames -contains $EntryName) {
        Pass "$Label"
    } else {
        Fail "$Label is missing: $EntryName"
    }
}

function Test-TauriResourceMapping {
    param(
        [object]$Resources,
        [string]$Source,
        [string]$Target
    )
    if ($null -eq $Resources) {
        Fail "Tauri bundle.resources is missing"
        return
    }
    $Property = $Resources.PSObject.Properties | Where-Object { $_.Name -eq $Source } | Select-Object -First 1
    if ($null -eq $Property) {
        Fail "Tauri bundle.resources is missing source: $Source"
        return
    }
    if ([string]$Property.Value -eq $Target) {
        Pass "Tauri resource maps $Source to $Target"
    } else {
        Fail "Tauri resource $Source maps to '$($Property.Value)', expected '$Target'"
    }
}

function Test-BuiltTauriAppStudioResources {
    $ResourceRootGroups = @(
        @{
            Mode = "release"
            Primary = Join-Path $Root "launcher\src-tauri\target\release"
            Legacy = Join-Path $Root "launcher\src-tauri\target\release\_up_\_up_"
        },
        @{
            Mode = "debug"
            Primary = Join-Path $Root "launcher\src-tauri\target\debug"
            Legacy = Join-Path $Root "launcher\src-tauri\target\debug\_up_\_up_"
        }
    )
    $ExistingGroups = @($ResourceRootGroups | Where-Object {
        (Test-Path -LiteralPath $_.Primary -PathType Container) -or
        (Test-Path -LiteralPath $_.Legacy -PathType Container)
    })
    if ($ExistingGroups.Count -eq 0) {
        Warn "Tauri resource output is not present; run a Tauri build to inspect App Studio resources"
        return
    }
    foreach ($Group in $ExistingGroups) {
        $PrimaryHasResources =
            (Test-Path -LiteralPath (Join-Path $Group.Primary "tools\app_studio\main.py") -PathType Leaf) -and
            (Test-Path -LiteralPath (Join-Path $Group.Primary "tools\app_studio\app_studio") -PathType Container) -and
            (Test-Path -LiteralPath (Join-Path $Group.Primary "tools\app_studio\assets") -PathType Container)
        if ($PrimaryHasResources) {
            Pass "$($Group.Mode) Tauri resource root includes App Studio CLI"
        } elseif (Test-Path -LiteralPath $Group.Primary -PathType Container) {
            Fail "$($Group.Mode) Tauri resource root is missing App Studio CLI: $($Group.Primary)"
        }

        if (Test-Path -LiteralPath $Group.Legacy -PathType Container) {
            $LegacyHasResources =
                (Test-Path -LiteralPath (Join-Path $Group.Legacy "tools\app_studio\main.py") -PathType Leaf) -and
                (Test-Path -LiteralPath (Join-Path $Group.Legacy "tools\app_studio\app_studio") -PathType Container) -and
                (Test-Path -LiteralPath (Join-Path $Group.Legacy "tools\app_studio\assets") -PathType Container)
            if ($LegacyHasResources) {
                Pass "$($Group.Mode) legacy Tauri resource root includes App Studio CLI"
            } elseif ($PrimaryHasResources) {
                Warn "$($Group.Mode) legacy _up_ resource root is stale; primary resource root includes App Studio CLI"
            } else {
                Fail "$($Group.Mode) legacy Tauri resource root is missing App Studio CLI: $($Group.Legacy)"
            }
        }
    }
}

Require-File $ManifestPath
Require-File $AppManifestPath

$Manifest = if (Test-Path -LiteralPath $ManifestPath -PathType Leaf) { Read-Json $ManifestPath } else { $null }
$AppManifest = if (Test-Path -LiteralPath $AppManifestPath -PathType Leaf) { Read-Json $AppManifestPath } else { $null }

foreach ($Path in @(
    "runner",
    "apps",
    "runtime",
    "runtime\app_envs",
    "runtime\web_automation_runtime",
    "config.default",
    "updater",
    "installer",
    "release\staging",
    "release\dist_installer",
    "release\app_packs"
)) {
    Require-Directory (Join-Path $Root $Path)
}
Require-File (Join-Path $Root "runtime\README.md")
Require-File (Join-Path $Root "tools\app_studio\main.py")
Require-Directory (Join-Path $Root "tools\app_studio\app_studio")
Require-Directory (Join-Path $Root "tools\app_studio\assets")

$TauriConfigPath = Join-Path $Root "launcher\src-tauri\tauri.conf.json"
$NsisHookPath = Join-Path $Root "launcher\src-tauri\nsis\toolhub_install_dir.nsh"
Require-File $TauriConfigPath
Require-File $NsisHookPath
if (Test-Path -LiteralPath $TauriConfigPath -PathType Leaf) {
    $TauriConfig = Read-Json $TauriConfigPath
    if ($TauriConfig -and $TauriConfig.bundle.windows.nsis.installerHooks -eq "nsis/toolhub_install_dir.nsh") {
        Pass "NSIS install-dir hook is configured"
    } else {
        Fail "NSIS install-dir hook is not configured in tauri.conf.json"
    }
    if ($TauriConfig) {
        Test-TauriResourceMapping $TauriConfig.bundle.resources "../../tools/app_studio/main.py" "tools/app_studio/main.py"
        Test-TauriResourceMapping $TauriConfig.bundle.resources "../../tools/app_studio/app_studio" "tools/app_studio/app_studio"
        Test-TauriResourceMapping $TauriConfig.bundle.resources "../../tools/app_studio/assets" "tools/app_studio/assets"
    }
}
if (Test-Path -LiteralPath $NsisHookPath -PathType Leaf) {
    $NsisHook = Get-Content -Raw -Encoding UTF8 -LiteralPath $NsisHookPath
    if ($NsisHook -like '*StrCpy $INSTDIR "$LOCALAPPDATA\Programs\ToolHub"*') {
        Pass "NSIS hook sets install dir to LOCALAPPDATA Programs ToolHub"
    } else {
        Fail "NSIS hook does not set install dir to LOCALAPPDATA Programs ToolHub"
    }
    if ($NsisHook -like '*SetOutPath $INSTDIR*') {
        Pass "NSIS hook resets SetOutPath after changing INSTDIR"
    } else {
        Fail "NSIS hook must reset SetOutPath after changing INSTDIR"
    }
}
$GeneratedNsisPath = Join-Path $Root "launcher\src-tauri\target\release\nsis\x64\installer.nsi"
if (Test-Path -LiteralPath $GeneratedNsisPath -PathType Leaf) {
    $GeneratedNsis = Get-Content -Raw -Encoding UTF8 -LiteralPath $GeneratedNsisPath
    if ($GeneratedNsis -like '*!insertmacro NSIS_HOOK_PREINSTALL*') {
        Pass "generated NSIS script inserts the preinstall hook"
    } else {
        Fail "generated NSIS script does not insert the preinstall hook"
    }
    if ($GeneratedNsis -like '*Call RestorePreviousInstallLocation*') {
        Pass "generated NSIS script can restore previous install location before hook"
    } else {
        Warn "generated NSIS script previous install location behavior was not found"
    }
} else {
    Warn "generated NSIS script is not present; run a Tauri release build to inspect final hook insertion"
}
Test-BuiltTauriAppStudioResources

$PythonExe = Join-Path $Root "runtime\python\python.exe"
$WebRuntimeDir = Join-Path $Root "runtime\web_automation_runtime"
$WebRuntimeFiles = @()
if (Test-Path -LiteralPath $WebRuntimeDir -PathType Container) {
    $WebRuntimeFiles = @(Get-ChildItem -LiteralPath $WebRuntimeDir -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notin @(".gitkeep", "README.md") })
}

if (Test-Path -LiteralPath $PythonExe -PathType Leaf) {
    Pass "Python runtime executable exists"
} elseif ($RequireRuntime) {
    Fail "Python runtime executable is missing: runtime/python/python.exe"
} else {
    Warn "Python runtime executable is not bundled yet"
}

if ($WebRuntimeFiles.Count -gt 0) {
    Pass "Web automation runtime files exist"
} elseif ($RequireRuntime) {
    Fail "Web automation runtime files are missing"
} else {
    Warn "Web automation runtime files are not bundled yet"
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
            $ActualSize = (Get-Item -LiteralPath $InstallerPath).Length
            if ($Manifest.toolhub.installer.size -and [int64]$Manifest.toolhub.installer.size -eq $ActualSize) {
                Pass "installer size matches"
            } elseif ($Manifest.toolhub.installer.size) {
                Fail "installer size mismatch"
            } else {
                Warn "installer size is empty"
            }
            Test-InstallerSignature -Path $InstallerPath
        } elseif ($RequireInstaller) {
            Fail "installer file is missing: $InstallerPath"
        } else {
            Warn "installer file is not present yet: $InstallerPath"
        }
    } else {
        Fail "installer file is missing in manifest"
    }
    if ($Manifest.toolhub.installer.type -in @("nsis", "msi")) {
        Pass "installer type is set"
    } else {
        Fail "installer type must be nsis or msi"
    }
}

if ($AppManifest) {
    if ($AppManifest.schema_version -eq 1) { Pass "app_manifest schema_version is 1" } else { Fail "app_manifest schema_version must be 1" }
    foreach ($Prop in $AppManifest.apps.PSObject.Properties) {
        $Id = $Prop.Name
        $Entry = $Prop.Value
        $AppDir = Join-Path (Join-Path $Root "apps") $Id
        $AppYaml = Join-Path $AppDir "app.yaml"
        $Enabled = Entry-Enabled $Entry
        $HasAppYaml = Test-Path -LiteralPath $AppYaml -PathType Leaf
        $RunEntry = $null
        $DisplayIcon = $null
        $RequirementsLock = $null

        if ($HasAppYaml) {
            Pass "$Id app.yaml exists"
            try {
                $YamlText = Get-Content -Raw -Encoding UTF8 $AppYaml
                $RunEntry = Read-AppRelativeYamlFile -YamlText $YamlText -Section "run" -Key "entry" -Label "$Id run.entry"
                $DisplayIcon = Read-AppRelativeYamlFile -YamlText $YamlText -Section "display" -Key "icon" -Label "$Id display.icon"
                $RequirementsLock = Get-RequirementsLockPathForAppPack -YamlText $YamlText -Label "$Id runtime.requirements_lock"
                Pass "$Id run.entry is set"
                Pass "$Id display.icon is set"
                Test-AppYamlReferencedFile -AppDir $AppDir -RelativePath $RunEntry -Label "$Id run.entry"
                Test-AppYamlReferencedFile -AppDir $AppDir -RelativePath $DisplayIcon -Label "$Id display.icon"
                if (-not [string]::IsNullOrWhiteSpace($RequirementsLock)) {
                    Test-AppYamlReferencedFile -AppDir $AppDir -RelativePath $RequirementsLock -Label "$Id runtime.requirements_lock"
                }
            } catch {
                Fail $_.Exception.Message
            }
        } elseif ($Enabled) {
            Fail "$Id enabled=true app.yaml is missing: $AppYaml. Restore the app source, set enabled=false if this is stale history, or remove it later through a deliberate full-delete flow."
            continue
        } else {
            if ($Strict) {
                Fail "$Id enabled=false stale entry is missing app.yaml: $AppYaml. Restore source or clean it through the future full-delete flow before strict release."
            } else {
                Warn "$Id enabled=false stale entry is missing app.yaml: $AppYaml. Normal verification keeps this as disabled history; strict release should restore or clean it."
            }
            if ($RequireAppPacks) {
                if ($Entry.package) {
                    $StalePackPath = Join-Path $ReleaseDir ([string]$Entry.package)
                    if (Test-Path -LiteralPath $StalePackPath -PathType Leaf) {
                        Pass "$Id disabled stale app pack exists"
                    } else {
                        Fail "$Id disabled stale app pack is missing while -RequireAppPacks is set: $StalePackPath"
                    }
                } else {
                    Fail "$Id disabled stale package path is missing while -RequireAppPacks is set"
                }
            }
            continue
        }

        if ($Entry.version) { Pass "$Id version is set" } else { Fail "$Id version is missing" }
        if ($Entry.package) { Pass "$Id package path is set" } else { Fail "$Id package path is missing" }
        if ($Entry.required_core) { Pass "$Id required_core is set" } else { Fail "$Id required_core is missing" }
        if ($Entry.required_runner) { Pass "$Id required_runner is set" } else { Fail "$Id required_runner is missing" }
        $RequiredRuntime = [string]$Entry.required_runtime
        if ($RequiredRuntime.StartsWith("python-shared-env:", [System.StringComparison]::OrdinalIgnoreCase)) {
            $EnvId = $RequiredRuntime.Substring("python-shared-env:".Length)
            $SharedEnv = Join-Path (Join-Path $Root "runtime\envs") $EnvId
            $SharedEnvPython = Join-Path $SharedEnv "Scripts\python.exe"
            if (Test-Path -LiteralPath $SharedEnvPython -PathType Leaf) {
                Pass "$Id shared runtime exists: $EnvId"
            } else {
                Fail "$Id shared runtime is missing: runtime/envs/$EnvId"
            }
        } else {
            $AppEnv = Join-Path (Join-Path $Root "runtime\app_envs") $Id
            if (Test-Path -LiteralPath $AppEnv -PathType Container) { Pass "$Id app_env skeleton exists" } else { Warn "$Id app_env skeleton is missing" }
        }
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
                    Test-ZipContainsEntry -EntryNames $EntryNames -EntryName "$Id/app.yaml" -Label "$Id app pack contains app.yaml"
                    Test-ZipContainsEntry -EntryNames $EntryNames -EntryName "$Id/pack_manifest.json" -Label "$Id app pack contains pack_manifest.json"
                    Test-ZipContainsEntry -EntryNames $EntryNames -EntryName "$Id/README.md" -Label "$Id app pack contains README.md"
                    Test-ZipContainsEntry -EntryNames $EntryNames -EntryName "$Id/requirements.txt" -Label "$Id app pack contains requirements.txt"
                    if ($RequirementsLock) {
                        Test-ZipContainsEntry -EntryNames $EntryNames -EntryName "$Id/$RequirementsLock" -Label "$Id app pack contains runtime.requirements_lock"
                    }
                    if ($DisplayIcon) {
                        Test-ZipContainsEntry -EntryNames $EntryNames -EntryName "$Id/$DisplayIcon" -Label "$Id app pack contains display.icon"
                    }
                    if ($RunEntry) {
                        Test-ZipContainsEntry -EntryNames $EntryNames -EntryName "$Id/$RunEntry" -Label "$Id app pack contains run.entry"
                    }
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
            # Already reported above as a required app_manifest field.
        }
    }
}

$StageManifest = Join-Path $ReleaseDir "staging\installer_payload\staging_manifest.json"
if (Test-Path -LiteralPath $StageManifest -PathType Leaf) {
    Pass "installer staging manifest exists"
} else {
    Warn "installer staging manifest is not present yet"
}

if ($Failed) {
    exit 1
}
exit 0
