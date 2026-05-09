$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$FixtureRoot = Join-Path $Root "tools\app_studio\tests\fixtures\app_pack_contract"
$ContractPath = Join-Path $FixtureRoot "expected_contract.json"
$HelperPath = Join-Path $PSScriptRoot "lib\app_pack_contract.ps1"

if (-not (Test-Path -LiteralPath $ContractPath -PathType Leaf)) {
    throw "Contract fixture is missing: $ContractPath"
}
if (-not (Test-Path -LiteralPath $HelperPath -PathType Leaf)) {
    throw "App Pack contract helper is missing: $HelperPath"
}

# package_app_pack.ps1 and verify_release.ps1 execute their main flow on load.
# This read-only test uses the side-effect-free helper module instead of
# dot-sourcing production scripts.
. $HelperPath

function Assert-Equal {
    param(
        [AllowNull()]$Actual,
        [AllowNull()]$Expected,
        [string]$Message
    )
    if ($null -eq $Expected) {
        if ($null -ne $Actual) {
            throw "$Message expected <null>, got <$Actual>"
        }
        return
    }
    if ($Actual -ne $Expected) {
        throw "$Message expected <$Expected>, got <$Actual>"
    }
}

function Assert-SequenceEqual {
    param(
        [string[]]$Actual,
        [string[]]$Expected,
        [string]$Message
    )
    $ActualSorted = @($Actual | Sort-Object)
    $ExpectedSorted = @($Expected | Sort-Object)
    $Diff = Compare-Object -ReferenceObject $ExpectedSorted -DifferenceObject $ActualSorted
    if ($Diff) {
        $Formatted = ($Diff | ForEach-Object { "$($_.SideIndicator) $($_.InputObject)" }) -join "; "
        throw "$Message mismatch: $Formatted"
    }
}

$Contract = Get-Content -LiteralPath $ContractPath -Raw | ConvertFrom-Json

foreach ($Case in $Contract.cases) {
    $AppDir = Join-Path $FixtureRoot $Case.app_dir
    $YamlPath = Join-Path $AppDir "app.yaml"
    if (-not (Test-Path -LiteralPath $YamlPath -PathType Leaf)) {
        throw "Fixture app.yaml is missing for $($Case.id): $YamlPath"
    }
    $YamlText = Get-Content -LiteralPath $YamlPath -Raw
    $Summary = Get-AppPackContractSummary -AppId $Case.app_id -YamlText $YamlText

    Assert-Equal -Actual $Summary.run_entry -Expected $Case.expected_run_entry -Message "$($Case.id) run.entry"
    Assert-Equal -Actual $Summary.display_icon -Expected $Case.expected_display_icon -Message "$($Case.id) display.icon"
    Assert-Equal -Actual $Summary.requirements_lock -Expected $Case.expected_requirements_lock -Message "$($Case.id) runtime.requirements_lock"

    foreach ($RelativePath in @("README.md", "requirements.txt", $Summary.run_entry, $Summary.display_icon)) {
        $FullPath = Resolve-AppRelativeFile -AppDir $AppDir -RelativePath $RelativePath -Label "$($Case.id) $RelativePath"
        if (-not (Test-Path -LiteralPath $FullPath -PathType Leaf)) {
            throw "$($Case.id) fixture file is missing: $FullPath"
        }
    }
    if ($Summary.requirements_lock) {
        $LockPath = Resolve-AppRelativeFile -AppDir $AppDir -RelativePath $Summary.requirements_lock -Label "$($Case.id) runtime.requirements_lock"
        if (-not (Test-Path -LiteralPath $LockPath -PathType Leaf)) {
            throw "$($Case.id) lock fixture file is missing: $LockPath"
        }
    }

    Assert-SequenceEqual -Actual @($Summary.required_entries) -Expected @($Case.expected_required_entries) -Message "$($Case.id) required entries"
}

foreach ($Case in $Contract.path_normalization_cases) {
    $HasExpected = $null -ne $Case.PSObject.Properties["expected"]
    $HasError = $null -ne $Case.PSObject.Properties["error_contains"]
    try {
        $Actual = Normalize-AppRelativePath -Path $Case.input -Label "fixture path"
        if ($HasError) {
            throw "$($Case.id) expected an error containing <$($Case.error_contains)>"
        }
        Assert-Equal -Actual $Actual -Expected $Case.expected -Message "$($Case.id) normalized path"
    } catch {
        if ($HasExpected) {
            throw
        }
        if (-not ($_.Exception.Message -like "*$($Case.error_contains)*")) {
            throw "$($Case.id) expected error containing <$($Case.error_contains)>, got <$($_.Exception.Message)>"
        }
    }
}

Write-Host "[OK] App Pack contract parity fixture matches PowerShell read-only helper expectations."
