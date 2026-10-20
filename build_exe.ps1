# ============================================
# 日期表格聚合项目管理框架 · PyInstaller 打包脚本 (PowerShell)
# 产物（全部平铺在 dist 根目录）：
#   sales_pm.exe  db_copy.exe  db_append.exe
#   weekreport_clean.exe  db_assign.exe  db_split.exe
#   fields.json（与 exe 同目录，改即生效）
# 前置：pip install pyinstaller openpyxl windows-toasts
# 用法：pwsh ./build_exe.ps1
# ============================================
$ErrorActionPreference = 'Stop'

function Build-One($name, $entry) {
    Write-Host "`n=== 打包 $name  (入口 $entry) ===" -ForegroundColor Cyan
    pyinstaller --onefile --console --name $name `
        --paths . `
        --collect-all windows_toasts `
        --distpath "dist" `
        --workpath "build\$name" `
        --specpath "build\$name" `
        --noconfirm `
        $entry
    if ($LASTEXITCODE -ne 0) { throw "$name 打包失败 (exit $LASTEXITCODE)" }
}

try {
    Build-One 'sales_pm'         'main.py'
    Build-One 'db_copy'          'db_copy\copy_gui.py'
    Build-One 'db_append'        'db_append\append_gui.py'
    Build-One 'weekreport_clean' 'weekreport_clean\clean_gui.py'
    Build-One 'db_assign'        'db_assign\assign_gui.py'
    Build-One 'db_split'         'db_split\split_gui.py'

    Copy-Item 'fields.json' 'dist\fields.json' -Force

    Write-Host "`n=== 完成 ===" -ForegroundColor Green
    Get-ChildItem dist -File | ForEach-Object { Write-Host ("  " + $_.Name) }
    Write-Host "`n用法：整个 dist 文件夹拷走即可，六个 exe 与 fields.json 同目录。"
}
catch {
    Write-Host "`n打包中断：$_" -ForegroundColor Red
    Write-Host "常见问题：pip install pyinstaller ｜ 杀毒加白 ｜ pip install -r requirements.txt"
    exit 1
}
