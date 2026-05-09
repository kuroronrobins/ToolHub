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
    "toolhub_exe_exists",
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
    key_checks = @($KeyChecks | Select-Object id,status,message)
    checklist_reflection_candidate = "If overall_status is pass and required manual checks are pass, update docs/06_acceptance_checklist.md Phase 1-B VM result from 未実施 to pass. If any manual_check remains, keep Phase 1-B incomplete and record the pending item."
}

$Summary | ConvertTo-Json -Depth 8
