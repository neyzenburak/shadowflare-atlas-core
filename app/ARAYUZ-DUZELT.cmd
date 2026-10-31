@echo off
py -3 "%~dp0live_server.py" --elevate --display-fix
if errorlevel 1 pause
