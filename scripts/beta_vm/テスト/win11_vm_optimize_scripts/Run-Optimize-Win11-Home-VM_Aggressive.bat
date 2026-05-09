@echo off
setlocal
cd /d "%~dp0"
echo Windows 11 Home VM aggressive optimization will start.
echo Please run this BAT as Administrator.
echo Warning: This disables more services such as Print Spooler.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Optimize-Win11-Home-VM.ps1" -Aggressive
echo.
echo Finished. Reboot Windows to apply all changes.
pause
