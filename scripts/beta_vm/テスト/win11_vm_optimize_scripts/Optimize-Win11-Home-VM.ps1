
<#
Optimize-Win11-Home-VM.ps1
Windows 11 Home を VMware 仮想マシン上で軽量運用するための一括設定スクリプトです。

方針:
- Windows Update / Microsoft Defender / Microsoft Store / App Installer は残す
- 広告・おすすめ・Consumer Experience・Widgets・Copilot・Game Bar・Xbox・不要なプリインストールアプリを抑制
- 視覚効果・バックグラウンド常駐・検索インデックス・一部テレメトリを抑制
- 破壊的な高速化、Defender無効化、Windows Update停止、コンポーネント削除はしない

実行例:
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Optimize-Win11-Home-VM.ps1

さらに強める場合:
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Optimize-Win11-Home-VM.ps1 -Aggressive

戻したい/個別調整したい可能性があるもの:
  - WSearch: Windows Search indexing
  - SysMain: memory/disk prefetch
  - Spooler: printing / Microsoft Print to PDF 周辺
  - OneDrive / Teams / Outlook / Xbox apps
#>

[CmdletBinding()]
param(
    # さらに強く軽量化します。印刷、互換性支援、エラー報告、Connected Devices なども止めます。
    [switch]$Aggressive,

    # 検索インデックスを残します。ファイル検索を多用する場合はこちら。
    [switch]$KeepSearchIndexing,

    # OneDrive を残します。
    [switch]$KeepOneDrive,

    # Teams を残します。
    [switch]$KeepTeams,

    # New Outlook を残します。
    [switch]$KeepOutlook,

    # Xbox / Game 系アプリを残します。
    [switch]$KeepXbox,

    # プリインストールアプリ削除をスキップします。
    [switch]$SkipAppRemoval,

    # DISM のコンポーネントクリーンアップをスキップします。
    [switch]$SkipDismCleanup,

    # Explorer 再起動をスキップします。
    [switch]$SkipExplorerRestart
)

$ErrorActionPreference = 'Continue'

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdmin)) {
    Write-Host 'ERROR: 管理者として Windows PowerShell を開いて実行してください。' -ForegroundColor Red
    Write-Host '例: スタートメニューで「Windows PowerShell」を右クリック → 管理者として実行' -ForegroundColor Yellow
    exit 1
}

$LogRoot = Join-Path $env:SystemDrive 'Win11-VM-Optimize-Logs'
New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null
$LogFile = Join-Path $LogRoot ('Optimize-Win11-Home-VM_{0:yyyyMMdd_HHmmss}.log' -f (Get-Date))
try { Start-Transcript -Path $LogFile -Append | Out-Null } catch {}

function Write-Section {
    param([Parameter(Mandatory)][string]$Title)
    Write-Host "`n============================================================" -ForegroundColor DarkCyan
    Write-Host $Title -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor DarkCyan
}

function Write-Info {
    param([Parameter(Mandatory)][string]$Message)
    Write-Host "[INFO] $Message"
}

function Write-Skip {
    param([Parameter(Mandatory)][string]$Message)
    Write-Host "[SKIP] $Message" -ForegroundColor DarkGray
}

function Invoke-SafeStep {
    param(
        [Parameter(Mandatory)][string]$Title,
        [Parameter(Mandatory)][scriptblock]$ScriptBlock
    )
    Write-Section $Title
    try {
        & $ScriptBlock
    } catch {
        Write-Warning ("Step failed: {0} / {1}" -f $Title, $_.Exception.Message)
    }
}

function Set-RegDword {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][int]$Value
    )
    try {
        if (-not (Test-Path $Path)) { New-Item -Path $Path -Force | Out-Null }
        New-ItemProperty -Path $Path -Name $Name -PropertyType DWord -Value $Value -Force | Out-Null
        Write-Info ("REG DWORD {0}\{1} = {2}" -f $Path, $Name, $Value)
    } catch {
        Write-Warning ("REG failed: {0}\{1} / {2}" -f $Path, $Name, $_.Exception.Message)
    }
}

function Set-RegQword {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][Int64]$Value
    )
    try {
        if (-not (Test-Path $Path)) { New-Item -Path $Path -Force | Out-Null }
        New-ItemProperty -Path $Path -Name $Name -PropertyType QWord -Value $Value -Force | Out-Null
        Write-Info ("REG QWORD {0}\{1} = {2}" -f $Path, $Name, $Value)
    } catch {
        Write-Warning ("REG failed: {0}\{1} / {2}" -f $Path, $Name, $_.Exception.Message)
    }
}

function Set-RegString {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$Value
    )
    try {
        if (-not (Test-Path $Path)) { New-Item -Path $Path -Force | Out-Null }
        New-ItemProperty -Path $Path -Name $Name -PropertyType String -Value $Value -Force | Out-Null
        Write-Info ("REG STRING {0}\{1} = {2}" -f $Path, $Name, $Value)
    } catch {
        Write-Warning ("REG failed: {0}\{1} / {2}" -f $Path, $Name, $_.Exception.Message)
    }
}

function Remove-RegValueSafe {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Name
    )
    try {
        if (Test-Path $Path) {
            Remove-ItemProperty -Path $Path -Name $Name -Force -ErrorAction SilentlyContinue
            Write-Info ("REG remove {0}\{1}" -f $Path, $Name)
        }
    } catch {
        Write-Warning ("REG remove failed: {0}\{1} / {2}" -f $Path, $Name, $_.Exception.Message)
    }
}

function Disable-ServiceSafe {
    param(
        [Parameter(Mandatory)][string]$Name,
        [ValidateSet('Disabled','Manual','Automatic')][string]$StartupType = 'Disabled'
    )
    try {
        $svc = Get-Service -Name $Name -ErrorAction SilentlyContinue
        if ($null -eq $svc) {
            Write-Skip "Service not found: $Name"
            return
        }
        if ($svc.Status -ne 'Stopped') {
            Stop-Service -Name $Name -Force -ErrorAction SilentlyContinue
        }
        Set-Service -Name $Name -StartupType $StartupType -ErrorAction Stop
        Write-Info "Service $Name -> $StartupType"
    } catch {
        Write-Warning ("Service failed: {0} / {1}" -f $Name, $_.Exception.Message)
    }
}

function Disable-TaskSafe {
    param(
        [Parameter(Mandatory)][string]$TaskPath,
        [Parameter(Mandatory)][string]$TaskName
    )
    try {
        $task = Get-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($null -eq $task) {
            Write-Skip "Task not found: $TaskPath$TaskName"
            return
        }
        Disable-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -ErrorAction Stop | Out-Null
        Write-Info "Task disabled: $TaskPath$TaskName"
    } catch {
        Write-Warning ("Task failed: {0}{1} / {2}" -f $TaskPath, $TaskName, $_.Exception.Message)
    }
}

function Remove-AppxByPattern {
    param([Parameter(Mandatory)][string]$Pattern)
    try {
        $installed = Get-AppxPackage -AllUsers -ErrorAction SilentlyContinue | Where-Object { $_.Name -like $Pattern }
        foreach ($pkg in $installed) {
            try {
                Write-Info "Remove installed Appx: $($pkg.Name)"
                Remove-AppxPackage -Package $pkg.PackageFullName -AllUsers -ErrorAction Stop
            } catch {
                Write-Warning ("Installed Appx remove failed: {0} / {1}" -f $pkg.Name, $_.Exception.Message)
            }
        }

        $provisioned = Get-AppxProvisionedPackage -Online -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -like $Pattern }
        foreach ($prov in $provisioned) {
            try {
                Write-Info "Remove provisioned Appx: $($prov.DisplayName)"
                Remove-AppxProvisionedPackage -Online -PackageName $prov.PackageName -ErrorAction Stop | Out-Null
            } catch {
                Write-Warning ("Provisioned Appx remove failed: {0} / {1}" -f $prov.DisplayName, $_.Exception.Message)
            }
        }
    } catch {
        Write-Warning ("Appx pattern failed: {0} / {1}" -f $Pattern, $_.Exception.Message)
    }
}

function Remove-ClassicOneDrive {
    if ($KeepOneDrive) {
        Write-Skip 'OneDrive removal skipped by -KeepOneDrive'
        return
    }

    Remove-RegValueSafe -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name 'OneDrive'
    Remove-RegValueSafe -Path 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Run' -Name 'OneDrive'

    $candidates = @(
        (Join-Path $env:SystemRoot 'SysWOW64\OneDriveSetup.exe'),
        (Join-Path $env:SystemRoot 'System32\OneDriveSetup.exe')
    )
    foreach ($exe in $candidates) {
        if (Test-Path $exe) {
            try {
                Write-Info "Run OneDrive uninstaller: $exe"
                Start-Process -FilePath $exe -ArgumentList '/uninstall' -Wait -WindowStyle Hidden
            } catch {
                Write-Warning ("OneDrive uninstall failed: {0}" -f $_.Exception.Message)
            }
            break
        }
    }
}

Invoke-SafeStep '0. 実行情報' {
    Write-Info "Computer: $env:COMPUTERNAME"
    Write-Info "User: $env:USERNAME"
    Write-Info "Log: $LogFile"
    Write-Info "Aggressive: $($Aggressive.IsPresent)"
    Write-Info '作業前に VMware の Snapshot を取っておくことを推奨します。'
}

Invoke-SafeStep '1. 電源・VM向け基本設定' {
    try { powercfg.exe /hibernate off | Out-Null; Write-Info 'Hibernate disabled' } catch { Write-Warning $_.Exception.Message }
    try { powercfg.exe /setactive SCHEME_MIN | Out-Null; Write-Info 'Power plan: High performance' } catch { Write-Warning $_.Exception.Message }
    try { powercfg.exe -change -monitor-timeout-ac 0 | Out-Null } catch {}
    try { powercfg.exe -change -standby-timeout-ac 0 | Out-Null } catch {}
    try { powercfg.exe -change -hibernate-timeout-ac 0 | Out-Null } catch {}
}

Invoke-SafeStep '2. 広告・おすすめ・Consumer Experience・Spotlight 抑制' {
    # Machine policy
    Set-RegDword 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\CloudContent' 'DisableWindowsConsumerFeatures' 1
    Set-RegDword 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\CloudContent' 'DisableSoftLanding' 1
    Set-RegDword 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\CloudContent' 'DisableWindowsSpotlightFeatures' 1
    Set-RegDword 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\CloudContent' 'DisableThirdPartySuggestions' 1
    Set-RegDword 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\CloudContent' 'DisableWindowsSpotlightOnActionCenter' 1
    Set-RegDword 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\CloudContent' 'DisableWindowsSpotlightOnSettings' 1
    Set-RegDword 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\CloudContent' 'DisableWindowsSpotlightWindowsWelcomeExperience' 1

    # User policy / user preferences
    Set-RegDword 'HKCU:\SOFTWARE\Policies\Microsoft\Windows\CloudContent' 'DisableTailoredExperiencesWithDiagnosticData' 1
    Set-RegDword 'HKCU:\SOFTWARE\Policies\Microsoft\Windows\CloudContent' 'DisableWindowsSpotlightFeatures' 1
    Set-RegDword 'HKCU:\SOFTWARE\Policies\Microsoft\Windows\CloudContent' 'DisableWindowsSpotlightOnActionCenter' 1
    Set-RegDword 'HKCU:\SOFTWARE\Policies\Microsoft\Windows\CloudContent' 'DisableWindowsSpotlightOnSettings' 1
    Set-RegDword 'HKCU:\SOFTWARE\Policies\Microsoft\Windows\CloudContent' 'DisableWindowsSpotlightWindowsWelcomeExperience' 1

    Set-RegDword 'HKCU:\Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo' 'Enabled' 0
    Set-RegDword 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Privacy' 'TailoredExperiencesWithDiagnosticDataEnabled' 0
    Set-RegDword 'HKCU:\Software\Microsoft\Windows\CurrentVersion\UserProfileEngagement' 'ScoobeSystemSettingEnabled' 0

    $cdm = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager'
    Set-RegDword $cdm 'ContentDeliveryAllowed' 0
    Set-RegDword $cdm 'FeatureManagementEnabled' 0
    Set-RegDword $cdm 'OemPreInstalledAppsEnabled' 0
    Set-RegDword $cdm 'PreInstalledAppsEnabled' 0
    Set-RegDword $cdm 'PreInstalledAppsEverEnabled' 0
    Set-RegDword $cdm 'SilentInstalledAppsEnabled' 0
    Set-RegDword $cdm 'SoftLandingEnabled' 0
    Set-RegDword $cdm 'SubscribedContentEnabled' 0
    Set-RegDword $cdm 'SystemPaneSuggestionsEnabled' 0
    Set-RegDword $cdm 'RotatingLockScreenEnabled' 0
    Set-RegDword $cdm 'RotatingLockScreenOverlayEnabled' 0

    # Windows の「おすすめ」「ヒント」「ウェルカム」「設定内おすすめ」系。存在しないビルドでは無視されます。
    $subscribedContentIds = @(
        'SubscribedContent-310093Enabled',
        'SubscribedContent-314563Enabled',
        'SubscribedContent-338387Enabled',
        'SubscribedContent-338388Enabled',
        'SubscribedContent-338389Enabled',
        'SubscribedContent-338393Enabled',
        'SubscribedContent-353694Enabled',
        'SubscribedContent-353696Enabled',
        'SubscribedContent-88000105Enabled'
    )
    foreach ($name in $subscribedContentIds) { Set-RegDword $cdm $name 0 }
}

Invoke-SafeStep '3. Widgets / Copilot / Search Web / Start / Taskbar 抑制' {
    # Widgets
    Set-RegDword 'HKLM:\SOFTWARE\Policies\Microsoft\Dsh' 'AllowNewsAndInterests' 0
    Set-RegDword 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced' 'TaskbarDa' 0

    # Copilot
    Set-RegDword 'HKCU:\Software\Policies\Microsoft\Windows\WindowsCopilot' 'TurnOffWindowsCopilot' 1
    Set-RegDword 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsCopilot' 'TurnOffWindowsCopilot' 1
    Set-RegDword 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced' 'ShowCopilotButton' 0

    # Windows AI / Paint AI 系。対応ビルドのみ反映され、非対応ビルドでは無視されます。
    Set-RegDword 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsAI' 'DisableCocreator' 1
    Set-RegDword 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsAI' 'DisableImageCreator' 1
    Set-RegDword 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsAI' 'DisableGenerativeFill' 1

    # Search web / Bing suggestions
    Set-RegDword 'HKCU:\Software\Policies\Microsoft\Windows\Explorer' 'DisableSearchBoxSuggestions' 1
    Set-RegDword 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Search' 'BingSearchEnabled' 0
    Set-RegDword 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Search' 'CortanaConsent' 0
    Set-RegDword 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\Windows Search' 'AllowCortana' 0
    Set-RegDword 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\Windows Search' 'DisableWebSearch' 1
    Set-RegDword 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\Windows Search' 'ConnectedSearchUseWeb' 0

    # Taskbar / Start simplification
    $adv = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced'
    Set-RegDword $adv 'SearchboxTaskbarMode' 0
    Set-RegDword $adv 'ShowTaskViewButton' 0
    Set-RegDword $adv 'TaskbarMn' 0
    Set-RegDword $adv 'Start_TrackDocs' 0
    Set-RegDword $adv 'Start_TrackProgs' 0
    Set-RegDword $adv 'Start_ShowRecentlyAddedApps' 0
    Set-RegDword $adv 'Start_ShowMostUsedApps' 0
    Set-RegDword $adv 'ShowSyncProviderNotifications' 0
    Set-RegDword $adv 'LaunchTo' 1
    Set-RegDword $adv 'HideFileExt' 0

    # Some Windows 11 policy names are edition/build dependent; harmless if ignored.
    Set-RegDword 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\Explorer' 'HideRecentlyAddedApps' 1
    Set-RegDword 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\Explorer' 'HideRecommendedSection' 1
    Set-RegDword 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\Explorer' 'DisableSearchBoxSuggestions' 1
}

Invoke-SafeStep '4. 視覚効果・アニメーション抑制' {
    Set-RegDword 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize' 'EnableTransparency' 0
    Set-RegDword 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects' 'VisualFXSetting' 2
    Set-RegString 'HKCU:\Control Panel\Desktop\WindowMetrics' 'MinAnimate' '0'
    Set-RegString 'HKCU:\Control Panel\Desktop' 'MenuShowDelay' '80'
    Set-RegString 'HKCU:\Control Panel\Mouse' 'MouseHoverTime' '80'
    Set-RegDword 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced' 'TaskbarAnimations' 0
    Set-RegDword 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced' 'ListviewAlphaSelect' 0
    Set-RegDword 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced' 'ListviewShadow' 0
    Set-RegDword 'HKCU:\Software\Microsoft\Windows\DWM' 'EnableAeroPeek' 0

    # Startup delay の短縮
    Set-RegDword 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Serialize' 'StartupDelayInMSec' 0
}

Invoke-SafeStep '5. Privacy / Activity / Feedback / Diagnostics 抑制' {
    Set-RegDword 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\System' 'EnableActivityFeed' 0
    Set-RegDword 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\System' 'PublishUserActivities' 0
    Set-RegDword 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\System' 'UploadUserActivities' 0

    Set-RegDword 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\DataCollection' 'AllowTelemetry' 1
    Set-RegDword 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\DataCollection' 'DoNotShowFeedbackNotifications' 1
    Set-RegDword 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\DataCollection' 'LimitDiagnosticLogCollection' 1
    Set-RegDword 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\DataCollection' 'LimitDumpCollection' 1

    Set-RegDword 'HKCU:\Software\Microsoft\Siuf\Rules' 'NumberOfSIUFInPeriod' 0
    Set-RegQword 'HKCU:\Software\Microsoft\Siuf\Rules' 'PeriodInNanoSeconds' 0

    # Background apps global toggle
    Set-RegDword 'HKCU:\Software\Microsoft\Windows\CurrentVersion\BackgroundAccessApplications' 'GlobalUserDisabled' 1
    Set-RegDword 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Search' 'BackgroundAppGlobalToggle' 0
}

Invoke-SafeStep '6. Game Bar / Game DVR / Xbox 常駐抑制' {
    Set-RegDword 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\GameDVR' 'AllowGameDVR' 0
    Set-RegDword 'HKCU:\System\GameConfigStore' 'GameDVR_Enabled' 0
    Set-RegDword 'HKCU:\Software\Microsoft\Windows\CurrentVersion\GameDVR' 'AppCaptureEnabled' 0
    Set-RegDword 'HKCU:\Software\Microsoft\GameBar' 'ShowStartupPanel' 0
    Set-RegDword 'HKCU:\Software\Microsoft\GameBar' 'AutoGameModeEnabled' 0
    Set-RegDword 'HKCU:\Software\Microsoft\GameBar' 'AllowAutoGameMode' 0
}

Invoke-SafeStep '7. Edge の初回起動・サイドバー・新しいタブのおすすめ抑制' {
    $edge = 'HKLM:\SOFTWARE\Policies\Microsoft\Edge'
    Set-RegDword $edge 'HideFirstRunExperience' 1
    Set-RegDword $edge 'HubsSidebarEnabled' 0
    Set-RegDword $edge 'PersonalizationReportingEnabled' 0
    Set-RegDword $edge 'SearchSuggestEnabled' 0
    Set-RegDword $edge 'NewTabPageContentEnabled' 0
    Set-RegDword $edge 'NewTabPageQuickLinksEnabled' 0
    Set-RegDword $edge 'NewTabPageHideDefaultTopSites' 1
    Set-RegDword $edge 'EdgeShoppingAssistantEnabled' 0
    Set-RegDword $edge 'ShowRecommendationsEnabled' 0
}

Invoke-SafeStep '8. 不要サービスの停止・無効化' {
    # 比較的安全に止めやすいもの
    Disable-ServiceSafe 'DiagTrack' 'Disabled'
    Disable-ServiceSafe 'dmwappushservice' 'Disabled'
    Disable-ServiceSafe 'MapsBroker' 'Disabled'
    Disable-ServiceSafe 'RemoteRegistry' 'Disabled'
    Disable-ServiceSafe 'RetailDemo' 'Disabled'
    Disable-ServiceSafe 'WMPNetworkSvc' 'Disabled'
    Disable-ServiceSafe 'WalletService' 'Disabled'
    Disable-ServiceSafe 'lfsvc' 'Disabled'

    # Xbox services
    if (-not $KeepXbox) {
        Disable-ServiceSafe 'XblAuthManager' 'Disabled'
        Disable-ServiceSafe 'XblGameSave' 'Disabled'
        Disable-ServiceSafe 'XboxGipSvc' 'Disabled'
        Disable-ServiceSafe 'XboxNetApiSvc' 'Disabled'
    } else {
        Write-Skip 'Xbox services kept by -KeepXbox'
    }

    # Windows Search indexing
    if (-not $KeepSearchIndexing) {
        Disable-ServiceSafe 'WSearch' 'Disabled'
    } else {
        Write-Skip 'WSearch kept by -KeepSearchIndexing'
    }

    # VM では体感差が出やすいことがあるため標準で Manual。完全停止は -Aggressive。
    if ($Aggressive) {
        Disable-ServiceSafe 'SysMain' 'Disabled'
    } else {
        Disable-ServiceSafe 'SysMain' 'Manual'
    }

    if ($Aggressive) {
        Disable-ServiceSafe 'Spooler' 'Disabled'
        Disable-ServiceSafe 'Fax' 'Disabled'
        Disable-ServiceSafe 'WerSvc' 'Disabled'
        Disable-ServiceSafe 'PcaSvc' 'Disabled'
        Disable-ServiceSafe 'CDPSvc' 'Disabled'
        Disable-ServiceSafe 'SSDPSRV' 'Disabled'
        Disable-ServiceSafe 'upnphost' 'Disabled'
    }
}

Invoke-SafeStep '9. 不要なスケジュールタスク抑制' {
    Disable-TaskSafe '\Microsoft\Windows\Application Experience\' 'Microsoft Compatibility Appraiser'
    Disable-TaskSafe '\Microsoft\Windows\Application Experience\' 'ProgramDataUpdater'
    Disable-TaskSafe '\Microsoft\Windows\Application Experience\' 'StartupAppTask'
    Disable-TaskSafe '\Microsoft\Windows\Customer Experience Improvement Program\' 'Consolidator'
    Disable-TaskSafe '\Microsoft\Windows\Customer Experience Improvement Program\' 'UsbCeip'
    Disable-TaskSafe '\Microsoft\Windows\Autochk\' 'Proxy'
    Disable-TaskSafe '\Microsoft\Windows\DiskDiagnostic\' 'Microsoft-Windows-DiskDiagnosticDataCollector'
    Disable-TaskSafe '\Microsoft\Windows\Feedback\Siuf\' 'DmClient'
    Disable-TaskSafe '\Microsoft\Windows\Feedback\Siuf\' 'DmClientOnScenarioDownload'
    Disable-TaskSafe '\Microsoft\Windows\Maps\' 'MapsToastTask'
    Disable-TaskSafe '\Microsoft\Windows\Maps\' 'MapsUpdateTask'
    Disable-TaskSafe '\Microsoft\Windows\Windows Error Reporting\' 'QueueReporting'

    if (-not $KeepXbox) {
        Disable-TaskSafe '\Microsoft\XblGameSave\' 'XblGameSaveTask'
        Disable-TaskSafe '\Microsoft\XblGameSave\' 'XblGameSaveTaskLogon'
        Disable-TaskSafe '\Microsoft\Windows\XblGameSave\' 'XblGameSaveTask'
        Disable-TaskSafe '\Microsoft\Windows\XblGameSave\' 'XblGameSaveTaskLogon'
    }
}

Invoke-SafeStep '10. プリインストールアプリ削除' {
    if ($SkipAppRemoval) {
        Write-Skip 'App removal skipped by -SkipAppRemoval'
        return
    }

    # 残すもの: Store / App Installer / Calculator / Notepad / Photos / Paint / Snipping Tool / Terminal 等
    $patterns = @(
        'Microsoft.549981C3F5F10',              # Cortana legacy
        'Microsoft.BingNews',
        'Microsoft.BingWeather',
        'Microsoft.GetHelp',
        'Microsoft.Getstarted',
        'Microsoft.MicrosoftOfficeHub',
        'Microsoft.MicrosoftSolitaireCollection',
        'Microsoft.MixedReality.Portal',
        'Microsoft.People',
        'Microsoft.PowerAutomateDesktop',
        'Microsoft.SkypeApp',
        'Microsoft.Todos',
        'Microsoft.Wallet',
        'Microsoft.WindowsAlarms',
        'Microsoft.windowscommunicationsapps',
        'Microsoft.WindowsFeedbackHub',
        'Microsoft.WindowsMaps',
        'Microsoft.YourPhone',
        'Microsoft.ZuneMusic',
        'Microsoft.ZuneVideo',
        'Clipchamp.Clipchamp',
        'MicrosoftTeams',
        'Microsoft.MicrosoftTeams',
        'MSTeams',
        'Microsoft.OutlookForWindows'
    )

    if ($KeepTeams) {
        $patterns = $patterns | Where-Object { $_ -notin @('MicrosoftTeams','Microsoft.MicrosoftTeams','MSTeams') }
    }
    if ($KeepOutlook) {
        $patterns = $patterns | Where-Object { $_ -ne 'Microsoft.OutlookForWindows' }
    }
    if ($KeepXbox) {
        Write-Skip 'Xbox apps kept by -KeepXbox'
    } else {
        $patterns += @(
            'Microsoft.GamingApp',
            'Microsoft.Xbox*'
        )
    }

    foreach ($pattern in $patterns) {
        Remove-AppxByPattern -Pattern $pattern
    }

    Remove-ClassicOneDrive
}

Invoke-SafeStep '11. Delivery Optimization / 更新まわりの軽量化。ただし Windows Update は止めない' {
    # P2P配信を使わない。Windows Update 自体は維持。
    Set-RegDword 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\DeliveryOptimization' 'DODownloadMode' 0
    Set-RegDword 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\DeliveryOptimization\Config' 'DODownloadMode' 0
}

Invoke-SafeStep '12. 一時ファイル清掃' {
    $tempPaths = @(
        $env:TEMP,
        (Join-Path $env:WINDIR 'Temp')
    )
    foreach ($path in $tempPaths) {
        if (Test-Path $path) {
            Write-Info "Clean temp: $path"
            Get-ChildItem -LiteralPath $path -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

Invoke-SafeStep '13. DISM コンポーネントクリーンアップ' {
    if ($SkipDismCleanup) {
        Write-Skip 'DISM cleanup skipped by -SkipDismCleanup'
        return
    }
    try {
        Write-Info 'DISM /Online /Cleanup-Image /StartComponentCleanup'
        Start-Process -FilePath dism.exe -ArgumentList '/Online','/Cleanup-Image','/StartComponentCleanup' -Wait -NoNewWindow
    } catch {
        Write-Warning ("DISM cleanup failed: {0}" -f $_.Exception.Message)
    }
}

Invoke-SafeStep '14. Explorer 再起動' {
    if ($SkipExplorerRestart) {
        Write-Skip 'Explorer restart skipped by -SkipExplorerRestart'
        return
    }
    try {
        Stop-Process -Name explorer -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
        Start-Process explorer.exe
        Write-Info 'Explorer restarted'
    } catch {
        Write-Warning ("Explorer restart failed: {0}" -f $_.Exception.Message)
    }
}

Write-Section '完了'
Write-Host '完了しました。完全反映には Windows の再起動を推奨します。' -ForegroundColor Green
Write-Host "ログ: $LogFile" -ForegroundColor Green
Write-Host ''
Write-Host '問題が出た場合の目安:' -ForegroundColor Yellow
Write-Host '  - ファイル検索が不便: 管理者 PowerShell で Set-Service WSearch -StartupType Automatic; Start-Service WSearch'
Write-Host '  - 印刷/PDF出力が必要: 管理者 PowerShell で Set-Service Spooler -StartupType Automatic; Start-Service Spooler'
Write-Host '  - OneDrive/Teams/Outlook/Xboxが必要: Microsoft Store から再インストール'
Write-Host ''
try { Stop-Transcript | Out-Null } catch {}
