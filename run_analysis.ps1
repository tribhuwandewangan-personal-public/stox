<#
.SYNOPSIS
    Interactive Multi-Agent Analysis, Update & Report Generation Runner for NSE Stock Predictor.
.DESCRIPTION
    1. Checks dependencies & background services (Valkey, Zerodha Kite Connect, Dashboard).
    2. Interactive Wizard: Prompt for Valkey wait, Zerodha login, and Analysis parameters (Complete Fresh vs Incremental).
    3. Syncs split-adjusted historical data & updates Excel dataset.
    4. Runs the multi-agent analysis workflow (deterministic, no LLM) and outputs prediction reports.
    5. Evaluates portfolio holdings & generates long-term / swing diagnostics.
.PARAMETER Force
    Force reset persistent queue and fresh re-analysis of all symbols without using cache.
.PARAMETER Symbol
    Specific comma-separated symbol(s) to analyze (e.g. -Symbol "RELIANCE,TCS").
.PARAMETER Portfolio
    Evaluates portfolio holdings and generates Portfolio Holdings Action report.
.PARAMETER NonInteractive
    Skip interactive prompts and run immediately with passed flags or defaults.
#>

[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$Fast,            # Kept for backward compatibility (ignored: engine is always LLM-free)
    [string]$Symbol = "",
    [switch]$Portfolio,
    [switch]$NonInteractive
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

# Resolve best Python executable (prefer project venv)
$venvPy = Join-Path $ScriptDir ".venv\Scripts\python.exe"
if (Test-Path $venvPy) {
    $pyRunner = @($venvPy)
}
elseif (Get-Command uv -ErrorAction SilentlyContinue) {
    $pyRunner = @("uv", "run", "python")
}
else {
    $pyRunner = @("python")
}

Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "  📈 NSE MULTI-AGENT STOCK PREDICTOR - INTERACTIVE RUNNER" -ForegroundColor Cyan
Write-Host "========================================================================" -ForegroundColor Cyan

# Determine if we should run in interactive wizard mode
# Default to interactive if no specific execution flags were passed
$isInteractive = (-not $NonInteractive) -and (-not $Force) -and ($Symbol -eq "") -and (-not $Portfolio)

# -----------------------------------------------------------------------------
# STEP 1: Python Environment & Dependencies
# -----------------------------------------------------------------------------
Write-Host ""
Write-Host "[1/5] Checking Python environment & dependencies..." -ForegroundColor Yellow
if (Test-Path $venvPy) {
    Write-Host "   ✅ Python virtual environment verified (.venv)." -ForegroundColor Green
}
elseif (Get-Command uv -ErrorAction SilentlyContinue) {
    try {
        uv sync --offline --quiet 2>$null
        Write-Host "   ✅ Virtual environment verified via uv." -ForegroundColor Green
    }
    catch {
        Write-Host "   Using active Python environment." -ForegroundColor DarkGray
    }
} else {
    Write-Host "   Using Python environment: $($pyRunner -join ' ')" -ForegroundColor DarkGray
}

# -----------------------------------------------------------------------------
# STEP 2: Valkey / Redis Service Check (with Interactive Wait Option)
# -----------------------------------------------------------------------------
Write-Host ""
Write-Host "[2/5] Checking Queue & Caching Services (Valkey on port 6379)..." -ForegroundColor Yellow

function Test-ValkeySocket {
    try {
        $socket = New-Object System.Net.Sockets.TcpClient
        $iar = $socket.BeginConnect("127.0.0.1", 6379, $null, $null)
        $waitOk = $iar.AsyncWaitHandle.WaitOne(800, $false)
        if ($waitOk -and $socket.Connected) {
            $socket.EndConnect($iar)
            $socket.Close()
            return $true
        }
        $socket.Close()
        return $false
    }
    catch {
        return $false
    }
}

$valkeyUp = Test-ValkeySocket

if ($valkeyUp) {
    Write-Host "   ✅ Valkey/Redis server active on localhost:6379" -ForegroundColor Green
}
else {
    Write-Host "   ⚠️  Valkey server is NOT running on localhost:6379." -ForegroundColor Yellow
    if ($isInteractive) {
        Write-Host ""
        Write-Host "   Queue Server Options:" -ForegroundColor Cyan
        Write-Host "   [W] Wait for Valkey (starts polling; launch 'valkey-server' in another terminal)" -ForegroundColor White
        Write-Host "   [C] Continue with resilient SQLite task queue (Default)" -ForegroundColor White
        $vChoice = Read-Host "   Select [W/C] (Default: C)"

        if ($vChoice -match "^[wW]") {
            Write-Host "   ⏳ Waiting for Valkey server on localhost:6379... (Press Ctrl+C to cancel)" -ForegroundColor Yellow
            $elapsedWait = 0
            while (-not (Test-ValkeySocket)) {
                Start-Sleep -Seconds 2
                $elapsedWait += 2
                Write-Host "      Waiting for Valkey connection ($elapsedWait`s elapsed)..." -ForegroundColor DarkGray
                if ($elapsedWait -ge 90) {
                    Write-Host "   ⚠️  Wait timeout reached (90s). Falling back to SQLite queue." -ForegroundColor DarkYellow
                    break
                }
            }
            if (Test-ValkeySocket) {
                Write-Host "   ✅ Valkey server connected successfully on localhost:6379!" -ForegroundColor Green
                $valkeyUp = $true
            }
        }
        else {
            Write-Host "   ℹ️  Continuing with persistent SQLite task queue." -ForegroundColor DarkGray
        }
    }
    else {
        Write-Host "   ℹ️  Falling back to persistent SQLite task queue (storage/cache.db)." -ForegroundColor DarkGray
    }
}

# -----------------------------------------------------------------------------
# STEP 3: Zerodha Kite Connect Check (with Interactive Login Option)
# -----------------------------------------------------------------------------
Write-Host ""
Write-Host "[3/5] Checking Zerodha Kite Connect Integration (Advisory Read-Only)..." -ForegroundColor Yellow

$kiteTokenFile = Join-Path $ScriptDir "storage\kite_token.json"
$kiteActive = $false
$kiteUser = ""

if (Test-Path $kiteTokenFile) {
    try {
        $tokData = Get-Content $kiteTokenFile -Raw | ConvertFrom-Json
        if ($tokData.access_token) {
            $kiteUser = if ($tokData.user_id) { $tokData.user_id } else { "Active User" }
            # Check if token was created today (Zerodha tokens expire daily at 06:00 AM IST)
            if ($tokData.created_at) {
                $tokCreated = [DateTime]::Parse($tokData.created_at)
                if ($tokCreated.Date -eq [DateTime]::Today) {
                    $kiteActive = $true
                }
            }
        }
    } catch {}
}

if ($kiteActive) {
    Write-Host "   ✅ Kite Connect active: Logged in as '$kiteUser' (session fresh for today)" -ForegroundColor Green
}
else {
    if (Test-Path $kiteTokenFile) {
        Write-Host "   ⚠️  Kite Connect token exists but may be expired (Zerodha requires daily login)." -ForegroundColor Yellow
    } else {
        Write-Host "   ⚠️  No Zerodha Kite Connect session token found." -ForegroundColor Yellow
    }

    if ($isInteractive) {
        Write-Host ""
        Write-Host "   Zerodha Connection Options:" -ForegroundColor Cyan
        Write-Host "   [L] Log in to Zerodha Kite interactively now (opens browser session)" -ForegroundColor White
        Write-Host "   [S] Skip / Continue with local snapshot advisory mode (Default)" -ForegroundColor White
        $kChoice = Read-Host "   Select [L/S] (Default: S)"

        if ($kChoice -match "^[lL]") {
            Write-Host "   Launching Zerodha Kite secure interactive login..." -ForegroundColor Cyan
            & $pyRunner[0] $pyRunner[1..$pyRunner.Length] "$ScriptDir\tools\kite_portfolio.py" --login
            # Re-check token
            if (Test-Path $kiteTokenFile) {
                try {
                    $tokData = Get-Content $kiteTokenFile -Raw | ConvertFrom-Json
                    if ($tokData.access_token) {
                        $kiteActive = $true
                        Write-Host "   ✅ Zerodha Kite session established successfully!" -ForegroundColor Green
                    }
                } catch {}
            }
        }
        else {
            Write-Host "   ℹ️  Continuing with offline snapshot data (storage/my_holdings.json)." -ForegroundColor DarkGray
        }
    }
    else {
        Write-Host "   ℹ️  Proceeding in offline/snapshot advisory mode." -ForegroundColor DarkGray
    }
}

# -----------------------------------------------------------------------------
# STEP 4: Interactive Parameter Configuration Wizard
# -----------------------------------------------------------------------------
$runSync = $true
$portfolioOnly = $false

if ($isInteractive) {
    Write-Host ""
    Write-Host "------------------------------------------------------------------------" -ForegroundColor DarkCyan
    Write-Host "🎯 ANALYSIS CONFIGURATION WIZARD" -ForegroundColor Cyan
    Write-Host "------------------------------------------------------------------------" -ForegroundColor DarkCyan
    Write-Host "   Analysis is very fast because the engine is 100% rule-based (no slow LLM)" -ForegroundColor DarkGray
    Write-Host "   and caches calculations for 12 hours unless a full refresh is requested." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "   Select Execution Mode:" -ForegroundColor White
    Write-Host "   [1] Incremental Analysis (Default: Fast, re-uses fresh 12h cache for unchanged stocks)" -ForegroundColor White
    Write-Host "   [2] Complete Fresh Analysis (--force: Re-runs all 6 agents across all stocks from scratch)" -ForegroundColor White
    Write-Host "   [3] Specific Target Symbol(s) (e.g. RELIANCE,TCS,BEL)" -ForegroundColor White
    Write-Host "   [4] Portfolio Holdings Only (diagnostics for your current holdings)" -ForegroundColor White

    $modeSelect = Read-Host "`n   Enter mode [1-4] (Default: 1)"

    switch ($modeSelect.Trim()) {
        "2" {
            $Force = $true
            Write-Host "   ⚡ Complete Fresh Analysis selected: Will recompute all 6 agents for every stock." -ForegroundColor Yellow
        }
        "3" {
            $customSyms = Read-Host "   Enter stock symbol(s) comma-separated (e.g. RELIANCE,TCS,BEL)"
            if ($customSyms.Trim()) {
                $Symbol = $customSyms.Trim()
                Write-Host "   🎯 Filtered target symbol(s): $Symbol" -ForegroundColor Yellow
            }
        }
        "4" {
            $portfolioOnly = $true
            Write-Host "   💼 Portfolio-Only mode selected." -ForegroundColor Yellow
        }
        default {
            Write-Host "   ⚡ Incremental Analysis mode selected (fast, cache-assisted)." -ForegroundColor Green
        }
    }

    # Historical Data sync prompt
    if (-not $portfolioOnly) {
        $syncPrompt = Read-Host "`n   Sync split-adjusted historical data & Excel workbook? [Y/n] (Default: Y)"
        if ($syncPrompt -match "^[nN]") {
            $runSync = $false
            Write-Host "   ℹ️  Historical sync skipped." -ForegroundColor DarkGray
        } else {
            Write-Host "   ✅ Historical data sync enabled." -ForegroundColor Green
        }
    }
    Write-Host "------------------------------------------------------------------------" -ForegroundColor DarkCyan
}

# -----------------------------------------------------------------------------
# STEP 5: Dashboard Server Check & Startup
# -----------------------------------------------------------------------------
$DashPort = 8765
$DashUrl = "http://localhost:$DashPort"
$serverRunning = $false
$activePort = $DashPort

foreach ($checkPort in @($DashPort, ($DashPort + 1), ($DashPort + 2))) {
    try {
        $statusResp = Invoke-RestMethod -Uri "http://127.0.0.1:$checkPort/api/status" -TimeoutSec 2 -ErrorAction Stop
        if ($statusResp) {
            $serverRunning = $true
            $activePort = $checkPort
            break
        }
    } catch {
        $serverRunning = $false
    }
}
$DashUrl = "http://localhost:$activePort"

if ($serverRunning) {
    Write-Host "`n   ✅ Realtime Dashboard Server already active at $DashUrl" -ForegroundColor Green
}
else {
    try {
        Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue | 
            Where-Object { $_.CommandLine -like "*dashboard_server.py*" } | 
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    } catch {}

    Write-Host "`n   Launching Realtime Dashboard Server on $DashUrl..." -ForegroundColor Yellow
    Start-Process -FilePath $pyRunner[0] -ArgumentList @($pyRunner[1..$pyRunner.Length] + @("$ScriptDir\dashboard_server.py", "--port", "$DashPort")) -WorkingDirectory $ScriptDir -WindowStyle Hidden

    $retries = 20
    while ($retries -gt 0) {
        Start-Sleep -Milliseconds 500
        foreach ($checkPort in @($DashPort, ($DashPort + 1), ($DashPort + 2))) {
            try {
                $statusResp = Invoke-RestMethod -Uri "http://127.0.0.1:$checkPort/api/status" -TimeoutSec 2 -ErrorAction Stop
                if ($statusResp) {
                    $serverRunning = $true
                    $activePort = $checkPort
                    break
                }
            } catch {}
        }
        if ($serverRunning) { break }
        $retries--
    }
    $DashUrl = "http://localhost:$activePort"
    if ($serverRunning) {
        Write-Host "   ✅ Dashboard Server started successfully at $DashUrl" -ForegroundColor Green
    }
}

# Launch browser
try {
    Start-Process $DashUrl
    Write-Host "   🌐 Dashboard opened in browser: $DashUrl" -ForegroundColor Cyan
} catch {}

# -----------------------------------------------------------------------------
# STEP 6: Historical Data Sync & Excel Export
# -----------------------------------------------------------------------------
if ($runSync -and (-not $portfolioOnly)) {
    Write-Host ""
    Write-Host "[4/5] Syncing split-adjusted historical data & updating Excel dataset..." -ForegroundColor Yellow
    try {
        & $pyRunner[0] $pyRunner[1..$pyRunner.Length] "$ScriptDir\tools\historical_data_tools.py" --sync --excel
    } catch {
        Write-Host "   Data sync notice: Continuing with existing SQLite historical dataset..." -ForegroundColor DarkYellow
    }
}

# -----------------------------------------------------------------------------
# STEP 7: Run Multi-Agent Analysis Pipeline
# -----------------------------------------------------------------------------
if (-not $portfolioOnly) {
    Write-Host ""
    Write-Host "[5/5] Triggering Multi-Agent Analysis Pipeline (rule-based, no LLM)..." -ForegroundColor Green
    Write-Host "   Config: $ScriptDir\symbols.json" -ForegroundColor DarkGray
    Write-Host "   Press Ctrl+C at any time to interrupt cleanly." -ForegroundColor DarkGray
    Write-Host ""

    $mainArgs = @()
    if ($Force) { $mainArgs += "--force" }
    if ($Symbol -and $Symbol.Trim() -ne "") { $mainArgs += @("--symbol", $Symbol.Trim()) }

    try {
        & $pyRunner[0] $pyRunner[1..$pyRunner.Length] "$ScriptDir\main.py" @mainArgs
    }
    catch [System.Management.Automation.PipelineStoppedException] {
        Write-Host "`n[STOP] Execution stopped by user." -ForegroundColor Yellow
        exit 0
    }
    catch {
        Write-Host "Notice: Pipeline completed or was stopped." -ForegroundColor DarkYellow
    }
}

# -----------------------------------------------------------------------------
# STEP 8: Portfolio Diagnostics & Action Report
# -----------------------------------------------------------------------------
if ($Portfolio -or $portfolioOnly -or (Test-Path "$ScriptDir\storage\my_holdings.json") -or (Test-Path "$ScriptDir\storage\kite_token.json")) {
    Write-Host ""
    Write-Host "💼 Generating Portfolio Diagnostics & Action Strategy Report..." -ForegroundColor Green
    try {
        & $pyRunner[0] $pyRunner[1..$pyRunner.Length] "$ScriptDir\tools\kite_portfolio.py" --report
    } catch {
        Write-Host "   Notice: Portfolio report generation skipped." -ForegroundColor DarkGray
    }
}

Write-Host ""
Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "  🎉 RUN COMPLETE! Reports and dashboard are ready:" -ForegroundColor Cyan
Write-Host "  * Realtime Web Dashboard:     $DashUrl" -ForegroundColor Green
Write-Host "  * Daily Predictions Report:   $ScriptDir\reports\NSE_Stock_Predictions_latest.md" -ForegroundColor Green
Write-Host "  * Portfolio Action Report:    $ScriptDir\reports\Portfolio_Holdings_Analysis_latest.md" -ForegroundColor Green
Write-Host "  * Historical Excel Dataset:   $ScriptDir\reports\NSE_Historical_Data.xlsx" -ForegroundColor Green
Write-Host "========================================================================" -ForegroundColor Cyan
