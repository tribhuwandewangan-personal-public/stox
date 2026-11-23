<#
.SYNOPSIS
    Emergency Cleanup & Health Check Script for NSE Stock Predictor Server.
.DESCRIPTION
    1. Identifies and terminates any hung or zombie dashboard server processes.
    2. Frees up ports 8765, 8766, 8767 if occupied by stale listeners.
    3. Validates symbols.json syntax to prevent JSON parsing crashes.
    4. Optionally restarts the dashboard server with -Restart switch.
.EXAMPLE
    .\cleanup_server.ps1
    .\cleanup_server.ps1 -Restart
#>

[CmdletBinding()]
param(
    [switch]$Restart
)

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition

Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "  NSE DASHBOARD SERVER CLEANUP & PORT RESCUE UTILITY" -ForegroundColor Cyan
Write-Host "========================================================================" -ForegroundColor Cyan

# 1. Kill any python.exe running dashboard_server.py
Write-Host ""
Write-Host "[1/3] Scanning for python processes running dashboard_server.py..." -ForegroundColor Yellow
$killedCount = 0

try {
    $processes = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*dashboard_server.py*" }
    
    if ($processes) {
        foreach ($proc in $processes) {
            Write-Host "  -> Terminating process PID $($proc.ProcessId)..." -ForegroundColor Yellow
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
            $killedCount++
        }
    }
}
catch {}

# Fallback: check via wmic or standard process check if CIM was restricted
if ($killedCount -eq 0) {
    try {
        $wmicOut = wmic process where "name='python.exe' and commandline like '%%dashboard_server.py%%'" get processid 2>$null
        $pids = ($wmicOut | Select-String -Pattern '\d+').Matches.Value
        foreach ($p in $pids) {
            if ($p -and $p -ne $PID) {
                Write-Host "  -> Terminating process PID $p..." -ForegroundColor Yellow
                Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
                $killedCount++
            }
        }
    }
    catch {}
}

if ($killedCount -gt 0) {
    Write-Host "  OK: Terminated $killedCount stale dashboard process(es)." -ForegroundColor Green
} else {
    Write-Host "  OK: No orphaned dashboard_server.py processes found." -ForegroundColor DarkGray
}

# 2. Check ports 8765, 8766, 8767 and kill any remaining owners
Write-Host ""
Write-Host "[2/3] Checking ports 8765, 8766, 8767..." -ForegroundColor Yellow
$ports = @(8765, 8766, 8767)
$freedPorts = 0

foreach ($port in $ports) {
    try {
        $conns = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue |
            Where-Object { $_.State -eq "Listen" -and $_.OwningProcess -gt 0 }
        
        foreach ($conn in $conns) {
            $pidToKill = $conn.OwningProcess
            Write-Host "  -> Port $port occupied by PID $pidToKill. Terminating..." -ForegroundColor Yellow
            Stop-Process -Id $pidToKill -Force -ErrorAction SilentlyContinue
            $freedPorts++
        }
    }
    catch {}
}

if ($freedPorts -gt 0) {
    Write-Host "  OK: Freed $freedPorts occupied port listener(s)." -ForegroundColor Green
} else {
    Write-Host "  OK: Ports 8765-8767 are all clear and available." -ForegroundColor Green
}

# 3. Validate symbols.json integrity
Write-Host ""
Write-Host "[3/3] Validating symbols.json..." -ForegroundColor Yellow
$symbolsPath = Join-Path $ScriptDir "symbols.json"

if (Test-Path $symbolsPath) {
    try {
        $content = Get-Content $symbolsPath -Raw -Encoding UTF8
        $json = $content | ConvertFrom-Json
        $count = ($json.symbols).Count
        Write-Host "  OK: symbols.json is valid! ($count symbols configured)" -ForegroundColor Green
    }
    catch {
        Write-Host "  ERROR: symbols.json has invalid JSON syntax!" -ForegroundColor Red
        Write-Host "  Details: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "  Tip: Check for extra notes or missing commas at the bottom of symbols.json." -ForegroundColor Yellow
    }
} else {
    Write-Host "  Warning: symbols.json not found at $symbolsPath" -ForegroundColor DarkYellow
}

# Summary
Write-Host ""
Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "  CLEANUP COMPLETE! System is clean." -ForegroundColor Cyan
Write-Host "========================================================================" -ForegroundColor Cyan

# 4. Optional restart
$FrontendUrl = "http://localhost:4200"
if ($Restart) {
    Write-Host ""
    Write-Host "Restarting dashboard server..." -ForegroundColor Cyan
    $venvPy = Join-Path $ScriptDir ".venv\Scripts\python.exe"
    if (Test-Path $venvPy) {
        Start-Process -FilePath $venvPy -ArgumentList @("$ScriptDir\dashboard_server.py", "--no-browser") -WorkingDirectory $ScriptDir -WindowStyle Hidden
    } else {
        Start-Process -FilePath "python" -ArgumentList @("$ScriptDir\dashboard_server.py", "--no-browser") -WorkingDirectory $ScriptDir -WindowStyle Hidden
    }

    # Ensure Angular frontend dev server is running on port 4200, then open Angular URL
    $ngRunning = [bool](Get-NetTCPConnection -LocalPort 4200 -State Listen -ErrorAction SilentlyContinue)
    if (-not $ngRunning) {
        $frontendDir = Join-Path $ScriptDir "frontend"
        if (Test-Path $frontendDir) {
            Write-Host "Starting Angular frontend dev server on $FrontendUrl..." -ForegroundColor Cyan
            Start-Process -FilePath "cmd.exe" -ArgumentList @("/c", "npm start") -WorkingDirectory $frontendDir -WindowStyle Minimized
        }
    }
    Write-Host "Launching Angular Workstation in browser: $FrontendUrl" -ForegroundColor Green
    Start-Process $FrontendUrl
} else {
    Write-Host "To start the dashboard now, run:" -ForegroundColor DarkGray
    Write-Host "  .\cleanup_server.ps1 -Restart" -ForegroundColor White
    Write-Host "  Angular UI URL: $FrontendUrl" -ForegroundColor Cyan
}
