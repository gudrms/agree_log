@echo off
setlocal

where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py -3 "%~dp0run_analysis.py" %*
  exit /b %ERRORLEVEL%
)

where python >nul 2>nul
if %ERRORLEVEL%==0 (
  python "%~dp0run_analysis.py" %*
  exit /b %ERRORLEVEL%
)

echo Python was not found. Install Python 3.10+ or add it to PATH.
exit /b 1
