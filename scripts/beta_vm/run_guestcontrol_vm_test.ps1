param(
    [string]$VMName = "ToolHubTestWidows",
    [string]$Username = "ToolHub_Test",
    [string]$Domain = "",
    [string]$VBoxManagePath = "",
    [string]$SharedRoot = "\\VBOXSVR\beta_vm\package\ToolHub_Beta_VM_Test",
    [string]$ResultsDir = "\\VBOXSVR\beta_vm\package\ToolHub_Beta_VM_Test\results",
    [string]$PasswordFile = "",
    [int]$CommandTimeoutMs = 120000,
    [switch]$RunInstallTest,
    [switch]$SkipUninstall,
    [switch]$SkipReinstall,
    [switch]$NoPasswordPrompt
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

function Resolve-VBoxManagePath {
    param([string]$Path)

    if (-not [string]::IsNullOrWhiteSpace($Path)) {
        if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
            throw "VBoxManage.exe not found: $Path"
        }
        return (Resolve-Path -LiteralPath $Path).Path
    }

    $Command = Get-Command VBoxManage -ErrorAction SilentlyContinue
    if ($null -ne $Command) {
        return $Command.Source
    }

    $DefaultPath = "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"
    if (Test-Path -LiteralPath $DefaultPath -PathType Leaf) {
        return $DefaultPath
    }

    throw "VBoxManage.exe was not found. Pass -VBoxManagePath explicitly."
}

function New-TempPasswordFile {
    $SecurePassword = Read-Host -Prompt "Guest Windows password for $Username" -AsSecureString
    $TempPath = [System.IO.Path]::GetTempFileName()
    $Bstr = [System.IntPtr]::Zero
    try {
        $Bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecurePassword)
        $PlainPassword = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($Bstr)
        $Encoding = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($TempPath, $PlainPassword, $Encoding)
        return $TempPath
    } finally {
        if ($Bstr -ne [System.IntPtr]::Zero) {
            [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Bstr)
        }
        $PlainPassword = $null
    }
}

function Invoke-VBoxManage {
    param(
        [string]$ExePath,
        [string[]]$Arguments
    )

    Write-Host ">> VBoxManage $($Arguments -join ' ')"
    & $ExePath @Arguments
    $ExitCode = $LASTEXITCODE
    if ($ExitCode -ne 0) {
        throw "VBoxManage failed with exit code $ExitCode"
    }
}

function Invoke-GuestProgram {
    param(
        [string]$ExePath,
        [string[]]$AuthArgs,
        [string]$GuestExe,
        [string[]]$GuestArgs,
        [int]$TimeoutMs
    )

    $Args = @(
        "guestcontrol",
        $VMName,
        "run",
        "--exe=$GuestExe",
        "--wait-stdout",
        "--wait-stderr",
        "--timeout=$TimeoutMs"
    ) + $AuthArgs + @("--") + $GuestArgs

    Invoke-VBoxManage -ExePath $ExePath -Arguments $Args
}

function ConvertTo-EncodedPowerShellCommand {
    param([string]$Script)
    $Bytes = [System.Text.Encoding]::Unicode.GetBytes($Script)
    return [Convert]::ToBase64String($Bytes)
}

function Get-DetectedDomain {
    param(
        [string]$ExePath,
        [string]$Vm,
        [string]$User
    )

    $Properties = & $ExePath guestproperty enumerate $Vm
    foreach ($Line in $Properties) {
        if ($Line -match "/VirtualBox/GuestInfo/User/$([Regex]::Escape($User))@([^/]+)/UsageState") {
            return $Matches[1]
        }
    }
    return ""
}

$VBoxManage = Resolve-VBoxManagePath -Path $VBoxManagePath
$TemporaryPasswordFile = ""
$EffectivePasswordFile = ""

try {
    Write-Host "== VirtualBox Guest Control preflight =="
    Write-Host "VMName: $VMName"
    Write-Host "Username: $Username"
    Write-Host "VBoxManage: $VBoxManage"

    Invoke-VBoxManage -ExePath $VBoxManage -Arguments @("list", "runningvms")

    $GuestProperties = & $VBoxManage guestproperty enumerate $VMName
    $GuestAddVersion = $GuestProperties | Select-String -Pattern "/VirtualBox/GuestAdd/Version\s+=\s+'([^']+)'" | Select-Object -First 1
    $LoggedInUsers = $GuestProperties | Select-String -Pattern "/VirtualBox/GuestInfo/OS/LoggedInUsersList\s+=\s+'([^']+)'" | Select-Object -First 1
    if ($GuestAddVersion) {
        Write-Host "Guest Additions: $($GuestAddVersion.Matches[0].Groups[1].Value)"
    } else {
        Write-Warning "Guest Additions version was not detected from guest properties."
    }
    if ($LoggedInUsers) {
        Write-Host "Logged-in users: $($LoggedInUsers.Matches[0].Groups[1].Value)"
    }

    if ([string]::IsNullOrWhiteSpace($Domain)) {
        $DetectedDomain = Get-DetectedDomain -ExePath $VBoxManage -Vm $VMName -User $Username
        if (-not [string]::IsNullOrWhiteSpace($DetectedDomain)) {
            Write-Host "Detected Windows domain/computer: $DetectedDomain"
            Write-Host "Domain is not passed by default because VirtualBox Guest Control can reject local Windows logons when --domain is set."
        }
    }

    if (-not [string]::IsNullOrWhiteSpace($PasswordFile)) {
        if (-not (Test-Path -LiteralPath $PasswordFile -PathType Leaf)) {
            throw "Password file not found: $PasswordFile"
        }
        $EffectivePasswordFile = (Resolve-Path -LiteralPath $PasswordFile).Path
    } elseif ($NoPasswordPrompt) {
        $TemporaryPasswordFile = [System.IO.Path]::GetTempFileName()
        $EffectivePasswordFile = $TemporaryPasswordFile
    } else {
        $TemporaryPasswordFile = New-TempPasswordFile
        $EffectivePasswordFile = $TemporaryPasswordFile
    }

    $AuthArgs = @("--username=$Username", "--passwordfile=$EffectivePasswordFile")
    if (-not [string]::IsNullOrWhiteSpace($Domain)) {
        $AuthArgs += "--domain=$Domain"
    }

    Write-Host ""
    Write-Host "== Guest Control login probe =="
    Invoke-GuestProgram `
        -ExePath $VBoxManage `
        -AuthArgs $AuthArgs `
        -GuestExe "C:\Windows\System32\cmd.exe" `
        -GuestArgs @("/c", "whoami") `
        -TimeoutMs $CommandTimeoutMs

    Write-Host ""
    Write-Host "== Guest environment probe =="
    $ProbeScript = @"
`$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
`$Data = [ordered]@{
    whoami = (whoami)
    username = `$env:USERNAME
    computer_name = `$env:COMPUTERNAME
    local_app_data = `$env:LOCALAPPDATA
    user_profile = `$env:USERPROFILE
    shared_root = '$SharedRoot'
    shared_root_exists = (Test-Path -LiteralPath '$SharedRoot')
    vm_install_test_exists = (Test-Path -LiteralPath (Join-Path '$SharedRoot' 'vm_install_test.ps1'))
    results_dir = '$ResultsDir'
    results_dir_exists = (Test-Path -LiteralPath '$ResultsDir')
    toolhub_exe_exists = (Test-Path -LiteralPath (Join-Path `$env:LOCALAPPDATA 'Programs\ToolHub\ToolHub.exe'))
}
`$Data | ConvertTo-Json -Depth 5
"@
    $EncodedProbe = ConvertTo-EncodedPowerShellCommand -Script $ProbeScript
    Invoke-GuestProgram `
        -ExePath $VBoxManage `
        -AuthArgs $AuthArgs `
        -GuestExe "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" `
        -GuestArgs @("-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", $EncodedProbe) `
        -TimeoutMs $CommandTimeoutMs

    if ($RunInstallTest) {
        Write-Host ""
        Write-Host "== Running vm_install_test.ps1 in guest =="
        $Switches = New-Object System.Collections.Generic.List[string]
        if ($SkipUninstall) {
            $Switches.Add("-SkipUninstall") | Out-Null
        }
        if ($SkipReinstall) {
            $Switches.Add("-SkipReinstall") | Out-Null
        }

        $InstallTestScript = @"
`$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Set-Location -LiteralPath '$SharedRoot'
& (Join-Path '$SharedRoot' 'vm_install_test.ps1') -SharedRoot '$SharedRoot' -ResultsDir '$ResultsDir' $($Switches -join ' ')
"@
        $EncodedInstallTest = ConvertTo-EncodedPowerShellCommand -Script $InstallTestScript
        Invoke-GuestProgram `
            -ExePath $VBoxManage `
            -AuthArgs $AuthArgs `
            -GuestExe "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" `
            -GuestArgs @("-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", $EncodedInstallTest) `
            -TimeoutMs ([Math]::Max($CommandTimeoutMs, 3600000))

        Write-Host ""
        Write-Host "Result files should be written under: $ResultsDir"
    } else {
        Write-Host ""
        Write-Host "Guest Control setup is usable. Add -RunInstallTest to run the VM installer validation script."
    }
} finally {
    if (-not [string]::IsNullOrWhiteSpace($TemporaryPasswordFile) -and (Test-Path -LiteralPath $TemporaryPasswordFile -PathType Leaf)) {
        Remove-Item -LiteralPath $TemporaryPasswordFile -Force
    }
}
