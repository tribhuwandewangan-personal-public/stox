<#
.SYNOPSIS
    Installs or updates Stox Workstation for autonomous production deployment on Windows:
      1. Stops any existing Stox Tray / Dashboard Server processes
      2. Generates storage\stox.ico
      3. Registers Windows Startup shortcut & creates Desktop / Quick Launch shortcuts
      4. Starts the new Stox Workstation tray supervisor
#>

[CmdletBinding()]
param(
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonW = Join-Path $RepoRoot ".venv\Scripts\pythonw.exe"
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$TrayScript = Join-Path $RepoRoot "stox_tray.py"

if (-not (Test-Path $PythonW)) {
    $PythonW = $PythonExe
}

Write-Host "[1/4] Stopping any existing Stox processes..." -ForegroundColor Cyan
$stoppedCount = 0

try {
    $procs = Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -like "*stox_tray.py*" -or
            $_.CommandLine -like "*dashboard_server.py*"
        }

    foreach ($proc in $procs) {
        Write-Host "  -> Stopping PID $($proc.ProcessId) ($($proc.Name))..." -ForegroundColor Yellow
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
        $stoppedCount++
    }
}
catch {}

# Ensure port 8765 is freed if an orphaned listener remains
try {
    $conns = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.OwningProcess -gt 0 }
    foreach ($conn in $conns) {
        Write-Host "  -> Freeing port 8765 (PID $($conn.OwningProcess))..." -ForegroundColor Yellow
        Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
        $stoppedCount++
    }
}
catch {}

if ($stoppedCount -gt 0) {
    Start-Sleep -Milliseconds 800
    Write-Host "  Stopped $stoppedCount existing process(es)." -ForegroundColor Green
} else {
    Write-Host "  No existing Stox processes running." -ForegroundColor DarkGray
}

Write-Host "[2/4] Generating Stox tray/taskbar icon..." -ForegroundColor Cyan
$IconPath = (& $PythonExe $TrayScript --make-icon).Trim()
Write-Host "  Icon: $IconPath" -ForegroundColor Green

$WshShell = New-Object -ComObject WScript.Shell

function New-StoxShortcut($ShortcutPath) {
    $Dir = Split-Path -Parent $ShortcutPath
    if (-not (Test-Path $Dir)) { New-Item -ItemType Directory -Path $Dir -Force | Out-Null }
    $Sc = $WshShell.CreateShortcut($ShortcutPath)
    $Sc.TargetPath = $PythonW
    $Sc.Arguments = "`"$TrayScript`""
    $Sc.WorkingDirectory = $RepoRoot
    $Sc.IconLocation = $IconPath
    $Sc.Description = "Stox Workstation (Autonomous Analysis + Catalyst Radar)"
    $Sc.Save()
}

Write-Host "[3/4] Registering Windows Startup & Desktop/Quick Launch shortcuts..." -ForegroundColor Cyan
$StartupLink = Join-Path ([Environment]::GetFolderPath("Startup")) "Stox Workstation.lnk"
$DesktopLink = Join-Path ([Environment]::GetFolderPath("Desktop")) "Stox Workstation.lnk"
$QuickLaunchLink = Join-Path $env:APPDATA "Microsoft\Internet Explorer\Quick Launch\Stox Workstation.lnk"
New-StoxShortcut $StartupLink
New-StoxShortcut $DesktopLink
New-StoxShortcut $QuickLaunchLink
Write-Host "  Startup:      $StartupLink" -ForegroundColor Green
Write-Host "  Desktop:      $DesktopLink" -ForegroundColor Green
Write-Host "  Quick Launch: $QuickLaunchLink" -ForegroundColor Green

if (-not $NoStart) {
    Write-Host "[4/4] Starting new Stox Workstation process..." -ForegroundColor Cyan
    Start-Process -FilePath $PythonW -ArgumentList "`"$TrayScript`"" -WorkingDirectory $RepoRoot
    Write-Host "  Stox Workstation started in system tray." -ForegroundColor Green
} else {
    Write-Host "[4/4] Skipped auto-start (-NoStart specified)." -ForegroundColor DarkGray
}

Write-Host "`nDone! Right-click the Desktop shortcut -> 'Pin to taskbar' if you also want it on the main Windows 11 taskbar." -ForegroundColor Yellow
