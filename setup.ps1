# setup.ps - create one-word command shims for the db_* submodules.
#
# After running this script you can type, from any directory:
#   db_split <args>        (instead of: python -m db_split <args>)
#   db_copy / db_append / db_assign / db_recycled / db_analysis work the same.
#
# What it does:
#   1. Creates a "bin" folder next to this script.
#   2. Writes one small .cmd shim per submodule into that folder.
#   3. Adds the folder to your user PATH (persistent) and to the
#      current session, so the commands work right away.
#
# Usage (run once, from the project root):
#   powershell -ExecutionPolicy Bypass -File setup.ps
#
# Requirements: the "python" launcher must be on PATH (it is, if you
# installed Python from python.org or Anaconda with default options).
# ASCII only, by design.
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Bin  = Join-Path $Root "bin"
New-Item -ItemType Directory -Force -Path $Bin | Out-Null

$Modules = @(
    "db_recycled",
    "db_split",
    "db_copy",
    "db_append",
    "db_assign",
    "db_analysis"
)

foreach ($m in $Modules) {
    $shim = Join-Path $Bin "$m.cmd"
    $lines = @(
        "@echo off",
        "rem One-word shim for: python -m $m",
        "set ROOT=%~dp0..",
        "set PYTHONPATH=%ROOT%;%PYTHONPATH%",
        "python -m $m %*"
    )
    [System.IO.File]::WriteAllText($shim, ($lines -join "`r`n") + "`r`n")
    Write-Host ("created " + $shim)
}

# Persistent user PATH update
$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not $UserPath) { $UserPath = "" }
$entries = $UserPath -split ";" | Where-Object { $_ -ne "" }
if ($entries -notcontains $Bin) {
    $newPath = $Bin
    if ($UserPath) { $newPath = $Bin + ";" + $UserPath }
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    Write-Host ("added to user PATH: " + $Bin)
} else {
    Write-Host ("already on user PATH: " + $Bin)
}

# Current session PATH update
if (($env:Path -split ";") -notcontains $Bin) {
    $env:Path = $Bin + ";" + $env:Path
}

Write-Host ""
Write-Host "Done. New terminals will have the commands automatically."
Write-Host "This terminal has them too. Try one:"
foreach ($m in $Modules) {
    Write-Host ("    " + $m + " --help")
}
