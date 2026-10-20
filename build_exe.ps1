# ============================================
# Date-Table Aggregated PM Framework - PyInstaller build script (PowerShell)
# Output (all flat in dist/):
#   sales_pm.exe  db_copy.exe  db_append.exe
#   weekreport_clean.exe  db_assign.exe  db_split.exe
#   fields.json (next to the exes, edit to take effect after restart)
# Prereq: pip install pyinstaller openpyxl windows-toasts
# Usage: pwsh ./build_exe.ps1
# ============================================
$ErrorActionPreference = 'Stop'

function Build-One($name, $entry) {
    Write-Host "`n=== Building $name (entry: $entry) ===" -ForegroundColor Cyan
    pyinstaller --onefile --console --name $name `
        --paths . `
        --collect-all windows_toasts `
        --distpath "dist" `
        --workpath "build\$name" `
        --specpath "build\$name" `
        --noconfirm `
        $entry
    if ($LASTEXITCODE -ne 0) { throw "$name build failed (exit $LASTEXITCODE)" }
}

try {
    Build-One 'sales_pm'         'main.py'
    Build-One 'db_copy'          'db_copy\copy_gui.py'
    Build-One 'db_append'        'db_append\append_gui.py'
    Build-One 'weekreport_clean' 'weekreport_clean\clean_gui.py'
    Build-One 'db_assign'        'db_assign\assign_gui.py'
    Build-One 'db_split'         'db_split\split_gui.py'

    Copy-Item 'fields.json' 'dist\fields.json' -Force

    Write-Host "`n=== Done ===" -ForegroundColor Green
    Get-ChildItem dist -File | ForEach-Object { Write-Host ("  " + $_.Name) }
    Write-Host "`nCopy the whole dist folder anywhere. Six exes + fields.json in one dir."
}
catch {
    Write-Host "`nBuild aborted: $_" -ForegroundColor Red
    Write-Host "Common fixes: pip install pyinstaller | whitelist dist in antivirus | pip install -r requirements.txt"
    exit 1
}