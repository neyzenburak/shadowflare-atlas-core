@echo off
py -3 "%~dp0live_server.py" --elevate
if errorlevel 1 pause
