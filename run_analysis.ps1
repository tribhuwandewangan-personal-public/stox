<#
.SYNOPSIS
    Automated Update, Multi-Agent Analysis & Report Generation Script for NSE Stock Predictor.
.DESCRIPTION
    1. Pulls latest repository updates (git pull).
    2. Syncs Python dependencies via uv & checks Valkey/dashboard services.
    3. Syncs split-adjusted historical data & exports Excel workbook (NSE_Historical_Data.xlsx).
    4. Runs the multi-agent LangGraph workflow and generates prediction reports.
#>

# Trap script cancellation (Ctrl+C) to prevent PowerShell hanging
trap {
    if ($_ -match "PipelineStopped" -or $_ -match "ScriptCmdletBaseExecInterrupt" -or $_.Exception -is [System.Management.Automation.PipelineStoppedException]) {
        Write-Host "`n[STOP] Script stopped by user (Ctrl+C). Cleanup complete." -ForegroundColor Yellow
        exit 0
    }
}

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition

# Ensure UTF-8 console and Python environment to prevent Windows charmap/cp1252 errors
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "  NSE MULTI-AGENT STOCK PREDICTOR - AUTOMATED RUNNER" -ForegroundColor Cyan
Write-Host "========================================================================" -ForegroundColor Cyan

# Step 1: Update Repository & Download Data
Write-Host ""
Write-Host "[1/4] Checking for repository updates..." -ForegroundColor Yellow
try {
    git pull origin main
}
catch {
    Write-Host "Notice: Git pull skipped or encountered warning. Continuing with local data..." -ForegroundColor DarkYellow
}

# Step 2: Sync Python Dependencies via UV & Check Background Services
Write-Host ""
Write-Host "[2/4] Syncing Python dependencies using uv..." -ForegroundColor Yellow
try {
    uv sync
}
catch {
    Write-Host "uv sync warning: Ensure uv is installed. Continuing with active environment..." -ForegroundColor DarkYellow
}

# Check Valkey Server Availability on port 6379
try {
    $socket = New-Object System.Net.Sockets.TcpClient("localhost", 6379)
    $socket.Close()
    Write-Host "OK: Valkey/Redis server detected on localhost:6379" -ForegroundColor Green
}
catch {
    Write-Host "VALKEY WARNING: Valkey queue server is NOT running on localhost:6379" -ForegroundColor Yellow
    Write-Host "   Start Valkey server using: valkey-server (or redis-server)" -ForegroundColor DarkYellow
    Write-Host "   Resilient fallback to SQLite task queue enabled." -ForegroundColor DarkGray
}

# Start Dashboard Server in background if port 8000 is free
try {
    $dashSocket = New-Object System.Net.Sockets.TcpClient("localhost", 8000)
    $dashSocket.Close()
    Write-Host "Realtime Dashboard Server running at http://localhost:8000" -ForegroundColor Green
}
catch {
    Write-Host "Launching Realtime Dashboard Server on http://localhost:8000..." -ForegroundColor Yellow
    Start-Process -FilePath "uv" -ArgumentList "run python `"$ScriptDir\dashboard_server.py`"" -WindowStyle Hidden
}

# Step 3: Sync Reliable Historical Market Data & Export to Excel
Write-Host ""
Write-Host "[3/4] Syncing split-adjusted historical data & updating Excel dataset..." -ForegroundColor Yellow
try {
    uv run python "$ScriptDir\tools\historical_data_tools.py" --sync --excel
}
catch {
    Write-Host "Data sync notice: Continuing with existing SQLite historical dataset..." -ForegroundColor DarkYellow
}

# Step 4: Run Multi-Agent Analysis & Generate Report
Write-Host ""
Write-Host "[4/4] Triggering LangGraph Multi-Agent Analysis Pipeline..." -ForegroundColor Green
Write-Host "Target Symbols Configuration: $ScriptDir\symbols.json" -ForegroundColor DarkGray
Write-Host "Press Ctrl+C at any time to interrupt cleanly." -ForegroundColor DarkGray
Write-Host ""

try {
    uv run python "$ScriptDir\main.py"
}
catch [System.Management.Automation.PipelineStoppedException] {
    Write-Host "`n[STOP] Execution stopped by user." -ForegroundColor Yellow
    exit 0
}
catch {
    try {
        python "$ScriptDir\main.py"
    }
    catch {
        Write-Host "Notice: Pipeline finished or was interrupted." -ForegroundColor DarkYellow
    }
}

Write-Host ""
Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "  ANALYSIS COMPLETE! Reports generated in: $ScriptDir\reports" -ForegroundColor Cyan
Write-Host "  * Excel Historical Dataset: $ScriptDir\reports\NSE_Historical_Data.xlsx" -ForegroundColor Green
Write-Host "  * Realtime Dashboard Server: http://localhost:8000" -ForegroundColor Green
Write-Host "========================================================================" -ForegroundColor Cyan
