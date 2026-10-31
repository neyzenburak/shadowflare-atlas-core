@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0launcher.ps1" -SetupOnly %*
if errorlevel 1 (
  echo.
  echo Setup failed. Run setup.cmd again to resume.
  pause
  exit /b 1
)
echo.
echo Setup complete. Open start.cmd or the desktop shortcut.
pause
