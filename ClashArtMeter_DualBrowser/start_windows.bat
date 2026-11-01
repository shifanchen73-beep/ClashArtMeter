@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if %errorlevel%==0 (
    py app.py
) else (
    python app.py
)
if errorlevel 1 (
    echo.
    echo Launch failed. Please take a screenshot of this window.
    pause
)
