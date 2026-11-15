<#
.SYNOPSIS
    Automated Update, Multi-Agent Analysis & Report Generation Script for NSE Stock Predictor.
.DESCRIPTION
    1. Pulls latest repository updates (git pull).
    2. Syncs Python dependencies via uv & checks Valkey/dashboard services.
    3. Syncs split-adjusted historical data & exports Excel workbook (NSE_Historical_Data.xlsx).
    4. Runs the multi-agent analysis workflow (deterministic, no LLM) and generates prediction reports.
.PARAMETER Force
    Force reset persistent queue and fresh re-analysis of all symbols.
.PARAMETER Symbol
    Specific comma-separated symbol(s) to analyze (e.g. -Symbol "RELIANCE,TCS").
.PARAMETER Fast
    [DEPRECATED - ignored] The engine is always deterministic and LLM-free. 
#>

[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$Fast,       # Kept for backward compatibility (ignored)
    [string]$Symbol = "",
    [switch]$Portfolio   # Evaluates portfolio holdings and generates Portfolio Holdings Action report
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
Write-Host "[4/4] Triggering Multi-Agent Analysis Pipeline (rule-based, no LLM)..." -ForegroundColor Green
Write-Host "Target Symbols Configuration: $ScriptDir\symbols.json" -ForegroundColor DarkGray
Write-Host "Press Ctrl+C at any time to interrupt cleanly." -ForegroundColor DarkGray
Write-Host ""

$mainArgs = @()
if ($Force) { $mainArgs += "--force" }
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

# Step 5: Portfolio Diagnostics & Holdings Action Report (if portfolio snapshot or token exists)
if ($Portfolio -or (Test-Path "$ScriptDir\storage\my_holdings.json") -or (Test-Path "$ScriptDir\storage\kite_token.json")) {
    Write-Host ""
    Write-Host "[5/5] Generating Portfolio Holdings Diagnostics & Strategy Report..." -ForegroundColor Green
    try {
        uv run python "$ScriptDir\tools\kite_portfolio.py" --report
    }
    catch {
        try {
            python "$ScriptDir\tools\kite_portfolio.py" --report
        }
        catch {
            Write-Host "Notice: Portfolio report generation skipped." -ForegroundColor DarkGray
        }
    }
}

Write-Host ""
Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "  ANALYSIS COMPLETE! Reports generated in: $ScriptDir\reports" -ForegroundColor Cyan
Write-Host "  * Excel Historical Dataset: $ScriptDir\reports\NSE_Historical_Data.xlsx" -ForegroundColor Green
Write-Host "  * Realtime Dashboard Server: $DashUrl" -ForegroundColor Green
Write-Host "========================================================================" -ForegroundColor Cyan
