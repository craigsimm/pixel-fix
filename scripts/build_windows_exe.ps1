$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$entryScript = Join-Path $repoRoot "scripts\pyinstaller_gui_entry.py"
$iconFile = Join-Path $repoRoot "pixel-fix.ico"
$windowIcon = Join-Path $repoRoot "ico-32.png"

Push-Location $repoRoot
try {
    python -m pip install pyinstaller
    python .\scripts\generate_windows_icon.py

    python -m PyInstaller `
        --noconfirm `
        --clean `
        --onefile `
        --windowed `
        --name "pixel-fix-gui" `
        --paths "src" `
        --icon $iconFile `
        --add-data "${iconFile};." `
        --add-data "${windowIcon};." `
        $entryScript
}
finally {
    Pop-Location
}
