# bt-tray paketini derler: dist\bt-tray.exe (tek dosya) ve dist\bt-tray-<surum>-windows-x64.zip
# (install.ps1'in kurdugu tasinabilir paket), her biri .sha256 ile.
#   pwsh ./tools/build.ps1 -Version 1.2.3
param([string]$Version = '0.0.0')
$ErrorActionPreference = 'Stop'
if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw "Surum x.y.z olmali: $Version" }
Set-Location (Split-Path $PSScriptRoot -Parent)

pyinstaller --noconfirm --clean --onefile --noconsole --uac-admin --name bt-tray bt_tray.py
if ($LASTEXITCODE) { throw "pyinstaller exit $LASTEXITCODE" }

$pkg = 'dist/pkg'
Remove-Item $pkg -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $pkg | Out-Null
Copy-Item dist/bt-tray.exe, README.md $pkg
$zip = "dist/bt-tray-$Version-windows-x64.zip"
Remove-Item $zip -Force -ErrorAction SilentlyContinue
Compress-Archive -Path "$pkg/*" -DestinationPath $zip
Remove-Item $pkg -Recurse -Force

foreach ($f in 'dist/bt-tray.exe', $zip) {
    $h = (Get-FileHash $f -Algorithm SHA256).Hash.ToLower()
    "$h  $(Split-Path $f -Leaf)" | Set-Content "$f.sha256" -Encoding ascii
    '{0}  {1:N1} MB  sha256={2}' -f (Split-Path $f -Leaf), ((Get-Item $f).Length / 1MB), $h
}
