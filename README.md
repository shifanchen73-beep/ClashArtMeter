# Clash Art Meter — Dual Browser Edition

Windows desktop floating monitor for estimating ChatGPT-related traffic routed through a local Clash/Mihomo controller. Designed for users who run ChatGPT in both Microsoft Edge and Google Chrome.

## Get the source

The source archive is stored as six Base64 parts in the source-archive folder to keep each GitHub upload small and verifiable. Download this repository using **Code → Download ZIP**, extract it, then double-click **assemble_source.bat**. It reconstructs ClashArtMeter_DualBrowser_v2_Source.zip. Extract that source ZIP to get the complete Python application, tests, icons, Windows launcher, and local build script.

## Features

- Filters traffic by configured ChatGPT/OpenAI domains.
- Estimates Edge and Chrome traffic separately when Clash connection metadata or Windows TCP ownership data makes the process identifiable.
- Keeps unattributed matching traffic in a separate bucket instead of assigning it to a browser without evidence.
- Shows filtered upload/download rates and session totals.
- Saves session history locally in SQLite.
- Uses the local Clash/Mihomo controller API in read-only mode.

## Important accuracy limits

This is an estimate based on Clash connection snapshots and Windows TCP process ownership. It is not a browser-tab-level network meter and cannot distinguish image generation from ordinary ChatGPT chat traffic on the same domains. Very short-lived connections, unrecognized CDN domains, direct (non-Clash) connections, and bytes not visible in connection snapshots may be missed. Edge/Chrome attribution may be incomplete on some Clash for Windows builds; unattributed traffic is shown separately.

## Build a Windows executable

The GitHub Actions workflow reassembles the source archive, runs the 13 unit tests, and packages ClashArtMeterDual.exe with PyInstaller. Open **Actions → Build Windows EXE** to view the latest run and download its artifact.

## Local use

Inside the extracted ClashArtMeter_DualBrowser folder, double-click start_windows.bat (Python 3.11+ required). Configure the local controller URL and API Secret in the app settings. Do not expose the controller API to the public internet.

## Privacy

- The repository excludes local settings, API Secret values, and traffic-history databases.
- Runtime settings and traffic history are stored locally under %LOCALAPPDATA%\\ClashArtMeter\\.
- The app does not read browser cookies, login credentials, ChatGPT conversation text, or generated image contents.
- API Secret is stored locally in the settings file in plaintext; protect access to your Windows user account and never upload that settings file.

MIT License.
