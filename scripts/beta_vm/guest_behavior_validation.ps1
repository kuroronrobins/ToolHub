param(
    [string]$PackageRoot = "\\VBOXSVR\beta_vm\package\ToolHub_Beta_VM_Test",
    [string]$InstallRoot = "",
    [string]$ResultRoot = ""
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

function New-StepResult {
    param([string]$Name)
    return [ordered]@{ name = $Name; ok = $false; details = [ordered]@{}; error = $null }
}

function Set-StepError {
    param([object]$Step, [object]$ErrorObject)
    $Step.ok = $false
    $Step.error = ($ErrorObject | Out-String).Trim()
}

function Invoke-JsonProcess {
    param(
        [string]$Exe,
        [string[]]$Args,
        [int]$TimeoutSeconds = 180
    )
    $QuotedArgs = New-Object System.Collections.Generic.List[string]
    foreach ($Arg in $Args) {
        [void]$QuotedArgs.Add(('"{0}"' -f $Arg.Replace('"', '\"')))
    }

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $Exe
    $psi.Arguments = ($QuotedArgs.ToArray() -join " ")
    $ExeParent = Split-Path -LiteralPath $Exe -Parent
    if ($ExeParent -and (Test-Path -LiteralPath $ExeParent -PathType Container)) {
        $psi.WorkingDirectory = $ExeParent
    }
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8
    try {
        $Process = [System.Diagnostics.Process]::Start($psi)
        $StdoutTask = $Process.StandardOutput.ReadToEndAsync()
        $StderrTask = $Process.StandardError.ReadToEndAsync()
        if (-not $Process.WaitForExit($TimeoutSeconds * 1000)) {
            try { $Process.Kill() } catch {}
            try { $Process.WaitForExit() } catch {}
            try { [void]$StdoutTask.Wait(5000) } catch {}
            try { [void]$StderrTask.Wait(5000) } catch {}
            $TimedOutStdout = try { $StdoutTask.Result } catch { "" }
            $TimedOutStderr = try { $StderrTask.Result } catch { "" }
            return [ordered]@{ exit_code = 124; stdout = $TimedOutStdout; stderr = ("timeout`n" + $TimedOutStderr).Trim() }
        }
        try { [void]$StdoutTask.Wait(5000) } catch {}
        try { [void]$StderrTask.Wait(5000) } catch {}
        $Stdout = try { $StdoutTask.Result } catch { "" }
        $Stderr = try { $StderrTask.Result } catch { "" }
        return [ordered]@{
            exit_code = $Process.ExitCode
            stdout = $Stdout
            stderr = $Stderr
        }
    } finally {
        if ($Process) {
            $Process.Dispose()
        }
    }
}

function Get-AppDirs {
    param([string]$Root)
    $AppsRoot = [System.IO.Path]::Combine($Root, "apps")
    if (-not (Test-Path -LiteralPath $AppsRoot -PathType Container)) {
        return @()
    }
    return @(Get-ChildItem -LiteralPath $AppsRoot -Directory | ForEach-Object { $_.Name } | Sort-Object)
}

function Stop-ToolHubProcesses {
    param([string]$Root)
    Get-Process |
        Where-Object {
            $_.ProcessName -like "ToolHub*" -or
            $_.ProcessName -like "ToolHub_Setup*" -or
            $_.ProcessName -like "pdf-workbench*" -or
            ($_.Path -and $_.Path -like "$Root*")
        } |
        Stop-Process -Force -ErrorAction SilentlyContinue
}

function Write-ValidationPythonScripts {
    param(
        [string]$ValidationRoot,
        [string]$PdfScriptPath,
        [string]$ExcelScriptPath
    )

    $PdfCode = @"
from __future__ import annotations
import json
import pathlib
import sys

payload = pathlib.Path(sys.argv[1])
validation = pathlib.Path(sys.argv[2])
sys.path.insert(0, str(payload / 'src-python'))

from pypdf import PdfWriter
from pdf_workbench_engine.jobs.inspect_pdf import handle as inspect_pdf
from pdf_workbench_engine.jobs.render_thumbnails import handle as render_thumbnails

validation.mkdir(parents=True, exist_ok=True)
pdf_path = validation / 'sample.pdf'
writer = PdfWriter()
writer.add_blank_page(width=200, height=200)
writer.add_metadata({'/Title': 'Codex VM PDF validation'})
with pdf_path.open('wb') as handle:
    writer.write(handle)

thumb_dir = validation / 'pdf_thumbnails'
inspect_result = inspect_pdf({'sourcePath': str(pdf_path)})
thumb_result = render_thumbnails({
    'sourcePath': str(pdf_path),
    'outputDir': str(thumb_dir),
    'pageNumbers': [1],
    'thumbnailZoom': 0.4,
    'previewZoom': 0.8,
})
thumbs = thumb_result.get('thumbnails') or []
thumb_paths = []
for item in thumbs:
    for key in ('thumbnailPath', 'previewPath'):
        path = item.get(key)
        if path:
            p = pathlib.Path(path)
            thumb_paths.append({'path': str(p), 'exists': p.is_file(), 'size': p.stat().st_size if p.is_file() else 0})
print(json.dumps({
    'ok': inspect_result.get('pageCount') == 1 and all(t['exists'] and t['size'] > 0 for t in thumb_paths),
    'pdf': str(pdf_path),
    'pdf_exists': pdf_path.is_file(),
    'pdf_size': pdf_path.stat().st_size if pdf_path.is_file() else 0,
    'inspect': inspect_result,
    'thumbnail_count': len(thumbs),
    'thumb_paths': thumb_paths,
}, ensure_ascii=False))
"@

    $ExcelCode = @"
from __future__ import annotations
import glob
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
validation = pathlib.Path(sys.argv[2])
app_src = root / 'apps' / 'app_20251123_excelbatchreplace' / 'src'
sys.path.insert(0, str(app_src))

import win32com.client
from app.batch_logic import BatchWorker, JobConfig, TemplateOption

work = validation / 'excel'
work.mkdir(parents=True, exist_ok=True)
template = work / 'template.xlsx'
target = work / 'target.xlsx'
backup = work / 'backup'
backup.mkdir(parents=True, exist_ok=True)

excel = win32com.client.DispatchEx('Excel.Application')
excel.Visible = False
excel.DisplayAlerts = False
try:
    wb = excel.Workbooks.Add()
    ws = wb.Worksheets(1)
    ws.Name = 'AllFile'
    ws.Range('A1').Value = 'KEY'
    ws.Range('B1').Value = 'NEW'
    wb.SaveAs(str(template), FileFormat=51)
    wb.Close(SaveChanges=False)

    wb = excel.Workbooks.Add()
    ws = wb.Worksheets(1)
    ws.Name = 'Target'
    ws.Range('A1').Value = 'KEY'
    ws.Range('B1').Value = 'OLD'
    wb.SaveAs(str(target), FileFormat=51)
    wb.Close(SaveChanges=False)
finally:
    excel.Quit()

logs = []
progress = []
done = {}
def log(msg):
    logs.append(str(msg))
def prog(cur, total):
    progress.append([cur, total])
def on_done(success, results, started_at, finished_at):
    done.update({
        'success': bool(success),
        'results': results,
        'started_at': started_at.isoformat(),
        'finished_at': finished_at.isoformat(),
    })

job = JobConfig(
    targets=[str(target)],
    templates=[TemplateOption(path=str(template), sheet_mode='AllFile', base_cell='A1', reflect_mode='value')],
    backup_enabled=True,
    backup_dir=str(backup),
)
worker = BatchWorker(job, log, prog, on_done)
worker.run()

excel = win32com.client.DispatchEx('Excel.Application')
excel.Visible = False
excel.DisplayAlerts = False
try:
    wb = excel.Workbooks.Open(str(target), ReadOnly=True, UpdateLinks=0)
    ws = wb.Worksheets(1)
    a1 = ws.Range('A1').Value
    b1 = ws.Range('B1').Value
    wb.Close(SaveChanges=False)
finally:
    excel.Quit()

backups = glob.glob(str(backup / '*' / 'target.xlsx')) + glob.glob(str(backup / 'target.xlsx'))
print(json.dumps({
    'ok': bool(done.get('success')) and b1 == 'NEW' and len(backups) >= 1,
    'target': str(target),
    'template': str(template),
    'target_a1': a1,
    'target_b1': b1,
    'done': done,
    'progress': progress,
    'backup_count': len(backups),
    'backup_paths': backups,
    'logs_tail': logs[-10:],
}, ensure_ascii=False))
"@

    Set-Content -LiteralPath $PdfScriptPath -Value $PdfCode -Encoding UTF8
    Set-Content -LiteralPath $ExcelScriptPath -Value $ExcelCode -Encoding UTF8
}

$StartedAt = Get-Date
if ([string]::IsNullOrWhiteSpace($InstallRoot)) {
    $InstallRoot = [System.IO.Path]::Combine($env:LOCALAPPDATA, "Programs", "ToolHub")
}
$UserDataRoot = [System.IO.Path]::Combine($env:LOCALAPPDATA, "ToolHub")
if ([string]::IsNullOrWhiteSpace($ResultRoot)) {
    $ResultRoot = [System.IO.Path]::Combine($UserDataRoot, "validation")
}
$ValidationRoot = [System.IO.Path]::Combine($ResultRoot, ("codex_" + $StartedAt.ToString("yyyyMMdd_HHmmss")))
New-Item -ItemType Directory -Force -Path $ValidationRoot | Out-Null
$Sentinel = [System.IO.Path]::Combine($UserDataRoot, "codex_validation_sentinel.txt")
New-Item -ItemType Directory -Force -Path $UserDataRoot | Out-Null
Set-Content -LiteralPath $Sentinel -Value ("created=" + $StartedAt.ToString("o")) -Encoding UTF8

$Result = [ordered]@{
    started_at = $StartedAt.ToString("o")
    root = $InstallRoot
    user_data_root = $UserDataRoot
    validation_root = $ValidationRoot
    steps = [ordered]@{}
}

$Step = New-StepResult "installed_state"
try {
    $AppDirs = Get-AppDirs -Root $InstallRoot
    $Setting = [System.IO.Path]::Combine($InstallRoot, "apps", "app_20251123_excelbatchreplace", "src", "Setting.xlsx")
    $Step.details = [ordered]@{
        toolhub_exists = Test-Path -LiteralPath ([System.IO.Path]::Combine($InstallRoot, "ToolHub.exe"))
        apps = $AppDirs
        setting_exists = Test-Path -LiteralPath $Setting
        python_exists = Test-Path -LiteralPath ([System.IO.Path]::Combine($InstallRoot, "runtime", "python", "python.exe"))
    }
    $Step.ok = $Step.details.toolhub_exists -and $Step.details.setting_exists -and ($AppDirs.Count -eq 2) -and ($AppDirs -contains "pdf_workbench") -and ($AppDirs -contains "app_20251123_excelbatchreplace")
} catch { Set-StepError $Step $_ }
$Result.steps.installed_state = $Step

$PdfScript = [System.IO.Path]::Combine($ValidationRoot, "pdf_validation.py")
$ExcelScript = [System.IO.Path]::Combine($ValidationRoot, "excel_validation.py")
Write-ValidationPythonScripts -ValidationRoot $ValidationRoot -PdfScriptPath $PdfScript -ExcelScriptPath $ExcelScript

$Step = New-StepResult "pdf_real_processing"
try {
    $Payload = [System.IO.Path]::Combine($InstallRoot, "apps", "pdf_workbench", "src", "assets", "payload")
    $PayloadPython = [System.IO.Path]::Combine($Payload, "python", "python.exe")
    $Run = Invoke-JsonProcess -Exe $PayloadPython -Args @($PdfScript, $Payload, $ValidationRoot) -TimeoutSeconds 180
    $Step.details.raw = $Run
    if ($Run.exit_code -eq 0 -and $Run.stdout.Trim()) {
        $Parsed = $Run.stdout | ConvertFrom-Json
        $Step.details.parsed = $Parsed
        $Step.ok = [bool]$Parsed.ok
    }
} catch { Set-StepError $Step $_ }
$Result.steps.pdf_real_processing = $Step

$Step = New-StepResult "excel_real_processing"
try {
    $RuntimePython = [System.IO.Path]::Combine($InstallRoot, "runtime", "python", "python.exe")
    $Bootstrap = [System.IO.Path]::Combine($InstallRoot, "runner", "toolhub_runner", "shared_env_bootstrap.py")
    $ExcelEnv = [System.IO.Path]::Combine($InstallRoot, "runtime", "envs", "py313-win_amd64-pywin32310-dd4d21f1")
    $Run = Invoke-JsonProcess -Exe $RuntimePython -Args @($Bootstrap, $ExcelEnv, $ExcelScript, $InstallRoot, $ValidationRoot) -TimeoutSeconds 240
    $Step.details.raw = $Run
    if ($Run.exit_code -eq 0 -and $Run.stdout.Trim()) {
        $Parsed = $Run.stdout | ConvertFrom-Json
        $Step.details.parsed = $Parsed
        $Step.ok = [bool]$Parsed.ok
    }
} catch { Set-StepError $Step $_ }
$Result.steps.excel_real_processing = $Step

$Step = New-StepResult "repeated_runner_launch_and_logs"
try {
    $RuntimePython = [System.IO.Path]::Combine($InstallRoot, "runtime", "python", "python.exe")
    $RunnerMain = [System.IO.Path]::Combine($InstallRoot, "runner", "toolhub_runner", "main.py")
    $Launches = @()
    foreach ($Round in 1..3) {
        foreach ($AppId in @("pdf_workbench", "app_20251123_excelbatchreplace")) {
            $Run = Invoke-JsonProcess -Exe $RuntimePython -Args @($RunnerMain, "--project-root", $InstallRoot, "--app-id", $AppId) -TimeoutSeconds 90
            $Launches += [ordered]@{ round = $Round; app_id = $AppId; exit_code = $Run.exit_code; stdout = $Run.stdout; stderr = $Run.stderr }
            Start-Sleep -Seconds 1
            Stop-ToolHubProcesses -Root $InstallRoot
        }
    }
    $Patterns = "Traceback|ModuleNotFoundError|ImportError|TclError|shared env site-packages not found|entry file not found|missing required asset"
    $LogRoots = @(
        [System.IO.Path]::Combine($UserDataRoot, "data", "logs"),
        [System.IO.Path]::Combine($InstallRoot, "data", "logs")
    )
    $Matches = @()
    foreach ($LogRoot in $LogRoots) {
        if (Test-Path -LiteralPath $LogRoot) {
            $Files = Get-ChildItem -LiteralPath $LogRoot -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -ge $StartedAt.AddMinutes(-1) }
            foreach ($File in $Files) {
                $Found = Select-String -LiteralPath $File.FullName -Pattern $Patterns -AllMatches -ErrorAction SilentlyContinue
                foreach ($Line in $Found) {
                    $Matches += [ordered]@{ path = $File.FullName; line = $Line.LineNumber; text = $Line.Line }
                }
            }
        }
    }
    $Step.details = [ordered]@{ launches = $Launches; fatal_log_matches = $Matches }
    $Step.ok = (@($Launches | Where-Object { $_.exit_code -ne 0 }).Count -eq 0) -and ($Matches.Count -eq 0)
} catch { Set-StepError $Step $_ }
$Result.steps.repeated_runner_launch_and_logs = $Step

$Step = New-StepResult "uninstall_reinstall_user_data_preservation"
try {
    Stop-ToolHubProcesses -Root $InstallRoot
    $UninstallerCandidates = @()
    if (Test-Path -LiteralPath $InstallRoot) {
        $UninstallerCandidates += @(Get-ChildItem -LiteralPath $InstallRoot -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -match "uninst|uninstall" } | ForEach-Object { $_.FullName })
    }
    foreach ($RegPath in @("HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*", "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*")) {
        $Items = @(Get-ItemProperty -Path $RegPath -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -like "*ToolHub*" })
        foreach ($Item in $Items) {
            if ($Item.UninstallString) {
                $Candidate = ([string]$Item.UninstallString).Trim('"')
                if (Test-Path -LiteralPath $Candidate -PathType Leaf) {
                    $UninstallerCandidates += $Candidate
                }
            }
        }
    }
    $Uninstaller = @($UninstallerCandidates | Select-Object -Unique | Select-Object -First 1)[0]
    if (-not $Uninstaller) { throw "uninstaller not found" }

    $UninstallProcess = Start-Process -FilePath $Uninstaller -ArgumentList "/S" -PassThru -Wait
    Start-Sleep -Seconds 3
    $AfterUninstall = [ordered]@{
        exit_code = $UninstallProcess.ExitCode
        toolhub_exe_exists = Test-Path -LiteralPath ([System.IO.Path]::Combine($InstallRoot, "ToolHub.exe"))
        install_root_exists = Test-Path -LiteralPath $InstallRoot
        sentinel_exists = Test-Path -LiteralPath $Sentinel
        user_data_root_exists = Test-Path -LiteralPath $UserDataRoot
    }

    $ManifestPath = [System.IO.Path]::Combine($PackageRoot, "release", "manifest.json")
    $Manifest = Get-Content -Encoding UTF8 -Raw -LiteralPath $ManifestPath | ConvertFrom-Json
    $Installer = [System.IO.Path]::Combine($PackageRoot, "release", "dist_installer", ([string]$Manifest.toolhub.installer.file))
    $LocalInstaller = [System.IO.Path]::Combine($env:TEMP, ("ToolHub_Setup_reinstall_" + [Guid]::NewGuid().ToString("N") + ".exe"))
    Copy-Item -LiteralPath $Installer -Destination $LocalInstaller -Force
    $ReinstallProcess = Start-Process -FilePath $LocalInstaller -ArgumentList "/S" -PassThru -Wait
    Remove-Item -LiteralPath $LocalInstaller -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
    $AppDirs = Get-AppDirs -Root $InstallRoot
    $AfterReinstall = [ordered]@{
        exit_code = $ReinstallProcess.ExitCode
        toolhub_exe_exists = Test-Path -LiteralPath ([System.IO.Path]::Combine($InstallRoot, "ToolHub.exe"))
        sentinel_exists = Test-Path -LiteralPath $Sentinel
        user_data_root_exists = Test-Path -LiteralPath $UserDataRoot
        apps = $AppDirs
        setting_exists = Test-Path -LiteralPath ([System.IO.Path]::Combine($InstallRoot, "apps", "app_20251123_excelbatchreplace", "src", "Setting.xlsx"))
    }
    $Step.details = [ordered]@{ uninstaller = $Uninstaller; after_uninstall = $AfterUninstall; installer = $Installer; after_reinstall = $AfterReinstall }
    $Step.ok = ($AfterUninstall.exit_code -eq 0) -and (-not $AfterUninstall.toolhub_exe_exists) -and $AfterUninstall.sentinel_exists -and ($AfterReinstall.exit_code -eq 0) -and $AfterReinstall.toolhub_exe_exists -and $AfterReinstall.sentinel_exists -and ($AppDirs.Count -eq 2) -and ($AppDirs -contains "pdf_workbench") -and ($AppDirs -contains "app_20251123_excelbatchreplace") -and $AfterReinstall.setting_exists
} catch { Set-StepError $Step $_ }
$Result.steps.uninstall_reinstall_user_data_preservation = $Step

$Step = New-StepResult "post_reinstall_smoke"
try {
    $RuntimePython = [System.IO.Path]::Combine($InstallRoot, "runtime", "python", "python.exe")
    $Bootstrap = [System.IO.Path]::Combine($InstallRoot, "runner", "toolhub_runner", "shared_env_bootstrap.py")
    $Checks = @()
    foreach ($App in @(
        [ordered]@{ id = "pdf_workbench"; env = "py313-win_amd64-runtime-37c71daf"; entry = [System.IO.Path]::Combine($InstallRoot, "apps", "pdf_workbench", "src", "main.py") },
        [ordered]@{ id = "app_20251123_excelbatchreplace"; env = "py313-win_amd64-pywin32310-dd4d21f1"; entry = [System.IO.Path]::Combine($InstallRoot, "apps", "app_20251123_excelbatchreplace", "src", "main.py") }
    )) {
        $EnvRoot = [System.IO.Path]::Combine($InstallRoot, "runtime", "envs", $App.env)
        $Run = Invoke-JsonProcess -Exe $RuntimePython -Args @($Bootstrap, $EnvRoot, $App.entry, "--toolhub-smoke") -TimeoutSeconds 120
        $Checks += [ordered]@{ app_id = $App.id; exit_code = $Run.exit_code; stdout = $Run.stdout; stderr = $Run.stderr }
    }
    $Step.details = [ordered]@{ checks = $Checks }
    $Step.ok = (@($Checks | Where-Object { $_.exit_code -ne 0 }).Count -eq 0)
} catch { Set-StepError $Step $_ }
$Result.steps.post_reinstall_smoke = $Step

$Result.finished_at = (Get-Date).ToString("o")
$Result.overall_ok = (@($Result.steps.GetEnumerator() | Where-Object { -not $_.Value.ok }).Count -eq 0)
$ResultPath = [System.IO.Path]::Combine($ValidationRoot, "codex_vm_behavior_validation_result.json")
$Result | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $ResultPath -Encoding UTF8
$Result.result_path = $ResultPath
$Result | ConvertTo-Json -Depth 20
