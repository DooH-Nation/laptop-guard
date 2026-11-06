# Run from this project folder after installing requirements and PyInstaller.
$ErrorActionPreference = 'Stop'
$guardProject = $PSScriptRoot
$guardIcon = Join-Path $guardProject 'LaptopGuard.ico'
python -m PyInstaller --noconfirm --onefile --windowed --name LaptopGuard --icon $guardIcon --add-data ($guardIcon+';.') --collect-all bleak --collect-all winrt --collect-all cryptography --hidden-import pystray._win32 --hidden-import _cffi_backend --distpath $guardProject --workpath (Join-Path $guardProject 'work\build') --specpath (Join-Path $guardProject 'work') (Join-Path $guardProject 'app.py')
