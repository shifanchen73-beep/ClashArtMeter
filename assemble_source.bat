@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0assemble_source.ps1"
if errorlevel 1 (
  echo.
  echo Source archive assembly failed.
  pause
  exit /b 1
)
echo.
echo Source archive created. Extract ClashArtMeter_DualBrowser_v2_Source.zip to use the project.
pause
