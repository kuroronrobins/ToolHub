param(
    [string]$ResultJsonPath = "",
    [string]$PackageRoot = ""
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($PackageRoot)) {
    $PackageRoot = Join-Path $ScriptDir "package\ToolHub_Beta_VM_Test"
}
if ([string]::IsNullOrWhiteSpace($ResultJsonPath)) {
    $Candidates = @(
        (Join-Path $PackageRoot "results\latest_vm_install_result.json"),
        (Join-Path $ScriptDir "results\latest_vm_install_result.json")
    )
    foreach ($Candidate in $Candidates) {
        if (Test-Path -LiteralPath $Candidate -PathType Leaf) {
            $ResultJsonPath = $Candidate
            break
        }
    }
}

if ([string]::IsNullOrWhiteSpace($ResultJsonPath) -or -not (Test-Path -LiteralPath $ResultJsonPath -PathType Leaf)) {
    Write-Host "VM result JSON was not found."
    Write-Host "Copy latest_vm_install_result.json from the VM package results folder, then rerun this script."
    exit 0
}

$Result = Get-Content -Encoding UTF8 -Raw -LiteralPath $ResultJsonPath | ConvertFrom-Json

function Get-JsonArrayProperty {
    param([object]$Object, [string]$Name)
    if ($null -eq $Object -or $null -eq $Object.PSObject.Properties[$Name]) {
        return @()
    }
    return @($Object.$Name | Where-Object { $null -ne $_ })
}

function Get-JsonProperty {
    param([object]$Object, [string]$Name)
    if ($null -eq $Object -or $null -eq $Object.PSObject.Properties[$Name]) {
        return $null
    }
    return $Object.$Name
}

$KeyIds = @(
    "dev_tool_absent_python",
    "dev_tool_absent_pip",
    "dev_tool_absent_node",
    "dev_tool_absent_npm",
    "dev_tool_absent_rustc",
    "dev_tool_absent_cargo",
    "dev_tool_absent_tauri",
    "installer_exists",
    "installer_sha256_matches_manifest",
    "installer_size_matches_manifest",
    "installer_completed",
    "expected_install_dir_exists",
    "install_location_discovery",
    "toolhub_exe_discovery",
    "toolhub_exe_exists",
    "payload_apps_exists",
    "payload_runner_exists",
    "payload_runtime_exists",
    "release_manifest_found",
    "app_manifest_found",
    "bundled_python_exists",
    "web_automation_runtime_exists",
    "toolhub_launch",
    "user_data_dir_created",
    "app_cards_visible",
    "sample_gui_app_launch",
    "sample_playwright_app_launch",
    "uninstall_completed",
    "user_data_preserved_after_uninstall",
    "reinstall_completed",
    "user_data_preserved_after_reinstall"
)

$KeyChecks = @()
foreach ($Id in $KeyIds) {
    $Match = @($Result.checks | Where-Object { $_.id -eq $Id } | Select-Object -First 1)
    if ($Match.Count -gt 0) {
        $KeyChecks += $Match[0]
    }
}

$Summary = [ordered]@{
    result_json = (Resolve-Path $ResultJsonPath).Path
    overall_status = $Result.overall_status
    counts = $Result.counts
    expected_install_dir = (Get-JsonProperty -Object $Result -Name "expected_install_dir")
    expected_install_dir_exists = (Get-JsonProperty -Object $Result -Name "expected_install_dir_exists")
    discovered_install_dirs = @(Get-JsonArrayProperty -Object $Result -Name "discovered_install_dirs")
    discovered_toolhub_exes = @(Get-JsonArrayProperty -Object $Result -Name "discovered_toolhub_exes" | Select-Object path,size,last_write_time_utc)
    launched_toolhub_exe = (Get-JsonProperty -Object $Result -Name "launched_toolhub_exe")
    resource_root_candidate = (Get-JsonProperty -Object $Result -Name "resource_root_candidate")
    apps_dir_found = (Get-JsonProperty -Object $Result -Name "apps_dir_found")
    runner_dir_found = (Get-JsonProperty -Object $Result -Name "runner_dir_found")
    release_manifest_found = (Get-JsonProperty -Object $Result -Name "release_manifest_found")
    app_manifest_found = (Get-JsonProperty -Object $Result -Name "app_manifest_found")
    likely_failure_category = (Get-JsonProperty -Object $Result -Name "likely_failure_category")
    log_matches = @(Get-JsonArrayProperty -Object (Get-JsonProperty -Object $Result -Name "log_summary") -Name "matched_lines" | Select-Object -First 20)
    key_checks = @($KeyChecks | Select-Object id,status,message)
    checklist_reflection_candidate = "If overall_status is pass and required manual checks are pass, update docs/06_acceptance_checklist.md Phase 1-B VM result from incomplete to pass. If any manual_check remains, keep Phase 1-B incomplete and record the pending item."
}

$Summary | ConvertTo-Json -Depth 8
