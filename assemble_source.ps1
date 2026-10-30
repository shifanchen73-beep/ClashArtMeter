$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$partDir = Join-Path $root "source-archive"
$parts = Get-ChildItem -LiteralPath $partDir -Filter "part-*.b64" | Sort-Object Name
if ($parts.Count -ne 6) {
    throw "Expected 6 source archive parts in source-archive; found $($parts.Count)."
}
$joined = ($parts | ForEach-Object { (Get-Content -LiteralPath $_.FullName -Raw).Trim() }) -join ""
$bytes = [Convert]::FromBase64String($joined)
$zipPath = Join-Path $root "ClashArtMeter_DualBrowser_v2_Source.zip"
[System.IO.File]::WriteAllBytes($zipPath, $bytes)
Write-Host "Created $zipPath ($($bytes.Length) bytes)"
