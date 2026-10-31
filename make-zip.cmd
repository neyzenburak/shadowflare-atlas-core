@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0launcher.ps1" -Package %*
if errorlevel 1 (
  echo.
  echo ZIP creation failed. Check the error above.
  pause
  exit /b 1
)
echo.
echo Your local ShadowFlare-Atlas-Core.zip is in the parent folder.
pause
