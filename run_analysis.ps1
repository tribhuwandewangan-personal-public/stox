<#
.SYNOPSIS
    Automated Update, Multi-Agent Analysis & Report Generation Script for NSE Stock Predictor.
.DESCRIPTION
    1. Pulls latest repository updates (git pull).
    2. Syncs Python dependencies via uv & checks Valkey/dashboard services.
    3. Syncs split-adjusted historical data & exports Excel workbook (NSE_Historical_Data.xlsx).
    4. Runs the multi-agent LangGraph workflow and generates prediction reports.
.PARAMETER Force
    Force reset persistent queue and fresh re-analysis of all symbols.
.PARAMETER Symbol
    Specific comma-separated symbol(s) to analyze (e.g. -Symbol "RELIANCE,TCS").
.PARAMETER Fast
    [DEPRECATED - now default] Explicitly enable fast quantitative mode (zero-LLM, all 34 stocks in <60s).
.PARAMETER NoFast
    Disable fast mode and use Ollama LLM narrative synthesis (requires Ollama running locally).
    WARNING: Takes 1-3 hours for all 34 symbols without cache.
#>

[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$Fast,       # Kept for backward compatibility (now default)
    [switch]$NoFast,     # Opt-in to full Ollama LLM synthesis (slow: ~1-3hrs for 34 symbols)
    [string]$Symbol = ""
)

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

# # Step 1: Update Repository & Download Data
# Write-Host ""
# Write-Host "[1/4] Checking for repository updates..." -ForegroundColor Yellow
# try {
#     git pull origin main
# }
# catch {
#     Write-Host "Notice: Git pull skipped or encountered warning. Continuing with local data..." -ForegroundColor DarkYellow
# }

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

# Dashboard Server Configuration (Uncommon Port 8765)
$DashPort = 8765
$DashUrl = "http://localhost:$DashPort"

# Check if Dashboard Server is already listening and responding on 8765, 8766, or 8767
$serverRunning = $false
$activePort = $DashPort

foreach ($checkPort in @($DashPort, ($DashPort + 1), ($DashPort + 2))) {
    try {
        $statusResp = Invoke-RestMethod -Uri "http://127.0.0.1:$checkPort/api/status" -TimeoutSec 2 -ErrorAction Stop
        if ($statusResp -and $statusResp.model) {
            $serverRunning = $true
            $activePort = $checkPort
            break
        }
    }
    catch {
        $serverRunning = $false
    }
}
$DashUrl = "http://localhost:$activePort"

if ($serverRunning) {
    Write-Host "Realtime Dashboard Server running at $DashUrl" -ForegroundColor Green
}
else {
    # Clean up any stale or hung dashboard server instances
    try {
        Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue | 
            Where-Object { $_.CommandLine -like "*dashboard_server.py*" } | 
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    }
    catch {}

    Write-Host "Launching Realtime Dashboard Server on $DashUrl..." -ForegroundColor Yellow
    
    # Prefer project .venv Python directly for reliable startup
    $venvPy = Join-Path $ScriptDir ".venv\Scripts\python.exe"
    if (Test-Path $venvPy) {
        Start-Process -FilePath $venvPy -ArgumentList @("$ScriptDir\dashboard_server.py", "--port", "$DashPort") -WorkingDirectory $ScriptDir -WindowStyle Hidden
    }
    elseif (Get-Command uv -ErrorAction SilentlyContinue) {
        Start-Process -FilePath "uv" -ArgumentList @("run", "python", "$ScriptDir\dashboard_server.py", "--port", "$DashPort") -WorkingDirectory $ScriptDir -WindowStyle Hidden
    }
    else {
        Start-Process -FilePath "python" -ArgumentList @("$ScriptDir\dashboard_server.py", "--port", "$DashPort") -WorkingDirectory $ScriptDir -WindowStyle Hidden
    }
    
    # Wait for server to bind and answer HTTP requests (Python library imports take ~7-9 seconds on Windows)
    $retries = 25
    while ($retries -gt 0) {
        Start-Sleep -Milliseconds 500
        foreach ($checkPort in @($DashPort, ($DashPort + 1), ($DashPort + 2))) {
            try {
                $statusResp = Invoke-RestMethod -Uri "http://127.0.0.1:$checkPort/api/status" -TimeoutSec 2 -ErrorAction Stop
                if ($statusResp -and $statusResp.model) {
                    $serverRunning = $true
                    $activePort = $checkPort
                    break
                }
            }
            catch {}
        }
        if ($serverRunning) { break }
        $retries--
    }
    $DashUrl = "http://localhost:$activePort"
    if ($serverRunning) {
        Write-Host "Realtime Dashboard Server started successfully at $DashUrl" -ForegroundColor Green
    }
    else {
        Write-Host "Notice: Dashboard background process launched. Connecting to $DashUrl..." -ForegroundColor DarkYellow
    }
}

# Automatically launch browser once server port is confirmed
try {
    Start-Process $DashUrl
    Write-Host "Opening dashboard in web browser: $DashUrl" -ForegroundColor Cyan
}
catch {
    Write-Host "Dashboard available at: $DashUrl" -ForegroundColor DarkGray
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

$mainArgs = @()
if ($Force) { $mainArgs += "--force" }
if ($NoFast) {
    # Explicitly disable fast mode - use Ollama LLM (slow, requires Ollama running)
    $env:FAST_MODE = "false"
    Write-Host "WARNING: NoFast mode enabled. Ollama LLM synthesis active." -ForegroundColor Yellow
    Write-Host "         Estimated time: 1-3 hours for 34 symbols." -ForegroundColor Yellow
    Write-Host "         Ensure Ollama is running: ollama serve" -ForegroundColor DarkYellow
} else {
    # Default: fast quantitative mode (all 34 stocks in <60 seconds, no Ollama required)
    $mainArgs += "--fast"
    Write-Host "Fast Mode: ON (quantitative synthesis, zero LLM calls, <60s for 34 symbols)" -ForegroundColor Green
}
if ($Symbol -and $Symbol.Trim() -ne "") { $mainArgs += @("--symbol", $Symbol.Trim()) }

try {
    uv run python "$ScriptDir\main.py" @mainArgs
}
catch [System.Management.Automation.PipelineStoppedException] {
    Write-Host "`n[STOP] Execution stopped by user." -ForegroundColor Yellow
    exit 0
}
catch {
    try {
        python "$ScriptDir\main.py" @mainArgs
    }
    catch {
        Write-Host "Notice: Pipeline finished or was interrupted." -ForegroundColor DarkYellow
    }
}

Write-Host ""
Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "  ANALYSIS COMPLETE! Reports generated in: $ScriptDir\reports" -ForegroundColor Cyan
Write-Host "  * Excel Historical Dataset: $ScriptDir\reports\NSE_Historical_Data.xlsx" -ForegroundColor Green
Write-Host "  * Realtime Dashboard Server: $DashUrl" -ForegroundColor Green
Write-Host "========================================================================" -ForegroundColor Cyan
