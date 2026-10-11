<#
.SYNOPSIS
    Automated Update, Multi-Agent Analysis & Report Generation Script for NSE Stock Predictor.
.DESCRIPTION
    1. Pulls latest repository updates & daily Bhavcopy data.
    2. Syncs Python dependencies via uv.
    3. Runs the multi-agent LangGraph workflow for target symbols in symbols.json.
    4. Generates timestamped report files in the reports directory.
#>

# Trap script cancellation (Ctrl+C) to prevent PowerShell hanging
trap {
    if ($_ -match "PipelineStopped" -or $_ -match "ScriptCmdletBaseExecInterrupt" -or $_.Exception -is [System.Management.Automation.PipelineStoppedException]) {
        Write-Host "`n🛑 Script stopped by user (Ctrl+C). Cleanup complete." -ForegroundColor Yellow
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

# # Step 2: Download latest daily Bhavcopy if NodeJS script is available
if (Test-Path "$ScriptDir\dataDownloader.js") {
    Write-Host ""
    Write-Host "[2/4] Checking latest daily Bhavcopy data..." -ForegroundColor Yellow
    try {
        node "$ScriptDir\dataDownloader.js"
    }
    catch {
        Write-Host "Data downloader notice: Continuing with existing Bhavcopy dataset..." -ForegroundColor DarkYellow
    }
}
else {
    Write-Host ""
    Write-Host "[2/4] Daily Bhavcopy data directory verified." -ForegroundColor Yellow
}

# Step 3: Sync Python Environment via UV & Check Valkey Status
Write-Host ""
Write-Host "[3/4] Syncing Python dependencies using uv..." -ForegroundColor Yellow
try {
    uv sync
}
catch {
    Write-Host "uv sync warning: Ensure uv is installed. Attempting python execution directly..." -ForegroundColor DarkYellow
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
    Write-Host "🌐 Realtime Dashboard Server running at http://localhost:8000" -ForegroundColor Green
}
catch {
    Write-Host "🌐 Launching Realtime Dashboard Server on http://localhost:8000..." -ForegroundColor Yellow
    Start-Process -FilePath "uv" -ArgumentList "run python `"$ScriptDir\dashboard_server.py`"" -WindowStyle Hidden
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
    Write-Host "`n🛑 Execution stopped by user." -ForegroundColor Yellow
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
Write-Host "  ANALYSIS COMPLETE! Report generated in: $ScriptDir\reports" -ForegroundColor Cyan
Write-Host "  🌐 Open Realtime Dashboard: http://localhost:8000" -ForegroundColor Green
Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "  🌐 Open Realtime Dashboard: http://localhost:8000" -ForegroundColor Green
Write-Host "========================================================================" -ForegroundColor Cyan
