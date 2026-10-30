# Clash Art Meter — Dual Browser Edition

Windows desktop floating monitor for estimating ChatGPT-related traffic routed through a local Clash/Mihomo controller. Designed for users who run ChatGPT in both Microsoft Edge and Google Chrome.

## Upload the source package (one-time setup)

The GitHub Actions workflow is ready, but the source ZIP still needs to be added to the repository once:

1. Download `ClashArtMeter_DualBrowser_v2_Source.zip` from the ChatGPT conversation where this project was prepared.
2. Open this repository on GitHub and choose **Add file → Upload files**.
3. Upload the ZIP to the repository root (do not extract it).
4. Commit the upload to the `main` branch.

The upload triggers **Actions → Build Windows EXE**. After a successful run, download the `ClashArtMeter-DualBrowser-Windows-x64` artifact from that run.

## Features

- Filters traffic by configured ChatGPT/OpenAI domains.
- Estimates Edge and Chrome traffic separately when Clash connection metadata or Windows TCP ownership data makes the process identifiable.
- Keeps unattributed matching traffic in a separate bucket instead of assigning it to a browser without evidence.
- Shows filtered upload/download rates and session totals.
- Saves session history locally in SQLite.
- Uses the local Clash/Mihomo controller API in read-only mode.

## Important accuracy limits

This is an estimate based on Clash connection snapshots and Windows TCP process ownership. It is not a browser-tab-level network meter and cannot distinguish image generation from ordinary ChatGPT chat traffic on the same domains. Very short-lived connections, unrecognized CDN domains, direct (non-Clash) connections, and bytes not visible in connection snapshots may be missed. Edge/Chrome attribution may be incomplete on some Clash for Windows builds; unattributed traffic is shown separately.

## Local use

After extracting the source ZIP, double-click `start_windows.bat` (Python 3.11+ required). Configure the local controller URL and API Secret in the app settings. Do not expose the controller API to the public internet.

## Privacy

- The source package and repository exclude local settings, API Secret values, and traffic-history databases.
- Runtime settings and traffic history are stored locally under `%LOCALAPPDATA%\\ClashArtMeter\\`.
- The app does not read browser cookies, login credentials, ChatGPT conversation text, or generated image contents.
- API Secret is stored locally in the settings file in plaintext; protect access to your Windows user account and never upload that settings file.

MIT License.
