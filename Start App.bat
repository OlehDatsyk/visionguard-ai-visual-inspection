@echo off
setlocal
cd /d "%~dp0"
title VisionGuard AI

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo.
  echo [VisionGuard] Python was not found.
  echo Install Python 3.12 from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  echo.
  pause
  exit /b 1
)

%PY% "scripts\start.py" %*
set "CODE=%ERRORLEVEL%"
if not "%CODE%"=="0" (
  echo.
  echo [VisionGuard] Stopped with an error. See INSTRUCTION.md, section Troubleshooting.
  if /i not "%~1"=="--check" if not defined VG_NO_PAUSE pause
)
exit /b %CODE%
