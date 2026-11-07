@echo off
rem Open ELEMENTALS on this computer. Double-click to start; close this window to stop.
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 app.py %*
) else (
  python app.py %*
)
pause
