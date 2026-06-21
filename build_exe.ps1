# Build a standalone Magpie.exe (no Python needed by recipients).
# Requires: pip install pyinstaller
Set-Location -Path $PSScriptRoot

pip install pyinstaller | Out-Null

pyinstaller --onefile --name Magpie `
  --add-data "magpie/web;magpie/web" `
  --add-data "magpie/default_config.json;magpie" `
  run_magpie.py

Write-Host ""
Write-Host "Done. Your distributable is at: dist\Magpie.exe"
Write-Host "Send that single file to anyone — they just double-click it."
