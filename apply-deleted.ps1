# apply-deleted.ps1 - remove files/directories listed in DELETED-FILES.txt
# One relative path per line; blank lines and lines starting with # are ignored.
# Run from the repo root after pasting a new release, before git add.
# Guards: absolute paths and paths containing ".." are skipped, never touched.
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$list = Join-Path $root 'DELETED-FILES.txt'

if (-not (Test-Path -LiteralPath $list)) {
    Write-Host 'DELETED-FILES.txt not found; nothing to do.'
    exit 0
}

$targets = Get-Content -LiteralPath $list | ForEach-Object { $_.Trim() } |
           Where-Object { $_ -ne '' -and -not $_.StartsWith('#') }

$removed = 0
foreach ($t in $targets) {
    if ([System.IO.Path]::IsPathRooted($t) -or $t.Contains('..')) {
        Write-Host "SKIP (unsafe path): $t"
        continue
    }
    $p = Join-Path $root $t
    if (Test-Path -LiteralPath $p) {
        Remove-Item -LiteralPath $p -Recurse -Force
        Write-Host "deleted: $t"
        $removed++
    } else {
        Write-Host "skip (not found): $t"
    }
}

# sweep directories left empty (never touches .git)
do {
    $empty = Get-ChildItem -LiteralPath $root -Directory -Recurse -Force |
             Where-Object {
                 $_.FullName -notmatch '[\\/]\.git([\\/]|$)' -and
                 -not (Get-ChildItem -LiteralPath $_.FullName -Recurse -Force |
                       Where-Object { $_.FullName -notmatch '[\\/]\.git([\\/]|$)' })
             }
    $empty | ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }
} while ($empty)

Write-Host "Done. $removed item(s) removed. Now review: git status --short"
