<#
.SYNOPSIS
    Interactive Multi-Agent Analysis, Update & Report Generation Runner for NSE Stock Predictor.
.DESCRIPTION
    1. Checks dependencies and background services (Valkey, Zerodha Kite Connect, Dashboard).
    2. Interactive Wizard: Prompt for Valkey wait, Zerodha login, and Analysis parameters (Complete Fresh vs Incremental).
    3. Syncs split-adjusted historical data and updates Excel dataset.
    4. Runs the multi-agent analysis workflow (deterministic, no LLM) and outputs prediction reports.
    5. Evaluates portfolio holdings and generates long-term / swing diagnostics.
.PARAMETER Force
    Force reset persistent queue and fresh re-analysis of all symbols without using cache.
.PARAMETER Symbol
    Specific comma-separated symbol(s) to analyze (e.g. -Symbol "RELIANCE,TCS").
.PARAMETER Portfolio
    Evaluates portfolio holdings and generates Portfolio Holdings Action report.
.PARAMETER AllUniverses
    Run analysis across all 3 symbol files (Curated Watchlist, Nifty 100 Large Cap, and Nifty Midcap 100). This is the default mode.
.PARAMETER NonInteractive
    Skip interactive prompts and run immediately with passed flags or defaults.
#>

[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$Fast,            # Kept for backward compatibility (ignored: engine is always LLM-free)
    [string]$Symbol = "",
    [switch]$Portfolio,
    [switch]$AllUniverses,
    [switch]$AllNse,
    [switch]$Midcap250,
    [string]$SymbolsFile = "",
    [int]$Limit = 0,
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
$pyExe = Join-Path $ScriptDir ".venv\Scripts\python.exe"
if (-not (Test-Path $pyExe)) {
    $pyExe = "python"
}

Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "  NSE MULTI-AGENT STOCK PREDICTOR - INTERACTIVE RUNNER" -ForegroundColor Cyan
Write-Host "========================================================================" -ForegroundColor Cyan

# Determine if we should run in interactive wizard mode
# Default to interactive if no specific execution flags were passed
$isInteractive = (-not $NonInteractive) -and (-not $Force) -and ($Symbol -eq "") -and (-not $Portfolio) -and (-not $AllUniverses) -and (-not $AllNse) -and (-not $Midcap250) -and ($SymbolsFile -eq "")

# -----------------------------------------------------------------------------
# STEP 1: Python Environment & Dependencies
# -----------------------------------------------------------------------------
Write-Host ""
Write-Host "[1/5] Checking Python environment and dependencies..." -ForegroundColor Yellow
if (Test-Path $pyExe) {
    Write-Host "   [OK] Python virtual environment verified (.venv)." -ForegroundColor Green
}
elseif (Get-Command uv -ErrorAction SilentlyContinue) {
    try {
        uv sync --offline --quiet 2>$null
        Write-Host "   [OK] Virtual environment verified via uv." -ForegroundColor Green
    }
    catch {
        Write-Host "   Using active Python environment." -ForegroundColor DarkGray
    }
}
else {
    Write-Host "   Using Python executable: $pyExe" -ForegroundColor DarkGray
}

# -----------------------------------------------------------------------------
# STEP 2: Valkey / Redis Service Check (with Interactive Wait Option)
# -----------------------------------------------------------------------------
Write-Host ""
Write-Host "[2/5] Checking Queue and Caching Services (Valkey on port 6379)..." -ForegroundColor Yellow

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
    Write-Host "   [OK] Valkey/Redis server active on localhost:6379" -ForegroundColor Green
}
else {
    Write-Host "   [WARN] Valkey server is NOT running on localhost:6379." -ForegroundColor Yellow
    if ($isInteractive) {
        Write-Host ""
        Write-Host "   Queue Server Options:" -ForegroundColor Cyan
        Write-Host "   [W] Wait for Valkey (starts polling; launch valkey-server in another terminal)" -ForegroundColor White
        Write-Host "   [C] Continue with resilient SQLite task queue (Default)" -ForegroundColor White
        $vChoice = Read-Host "   Select [W/C] (Default: C)"

        if ($vChoice -match "^[wW]") {
            Write-Host "   Waiting for Valkey server on localhost:6379... (Press Ctrl+C to cancel)" -ForegroundColor Yellow
            $elapsedWait = 0
            while (-not (Test-ValkeySocket)) {
                Start-Sleep -Seconds 2
                $elapsedWait += 2
                Write-Host "      Waiting for Valkey connection ($elapsedWait seconds elapsed)..." -ForegroundColor DarkGray
                if ($elapsedWait -ge 90) {
                    Write-Host "   [WARN] Wait timeout reached (90s). Falling back to SQLite queue." -ForegroundColor DarkYellow
                    break
                }
            }
            if (Test-ValkeySocket) {
                Write-Host "   [OK] Valkey server connected successfully on localhost:6379!" -ForegroundColor Green
                $valkeyUp = $true
            }
        }
        else {
            Write-Host "   Continuing with persistent SQLite task queue." -ForegroundColor DarkGray
        }
    }
    else {
        Write-Host "   Falling back to persistent SQLite task queue (storage/cache.db)." -ForegroundColor DarkGray
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
            if ($tokData.created_at) {
                $tokCreated = [DateTime]::Parse($tokData.created_at)
                if ($tokCreated.Date -eq [DateTime]::Today) {
                    $kiteActive = $true
                }
            }
        }
    }
    catch {}
}

if ($kiteActive) {
    Write-Host "   [OK] Kite Connect active: Logged in as $kiteUser (session fresh for today)" -ForegroundColor Green
}
else {
    if (Test-Path $kiteTokenFile) {
        Write-Host "   [WARN] Kite Connect token exists but may be expired (Zerodha requires daily login)." -ForegroundColor Yellow
    }
    else {
        Write-Host "   [WARN] No Zerodha Kite Connect session token found." -ForegroundColor Yellow
    }

    if ($isInteractive) {
        Write-Host ""
        Write-Host "   Zerodha Connection Options:" -ForegroundColor Cyan
        Write-Host "   [L] Log in to Zerodha Kite interactively now (opens browser session)" -ForegroundColor White
        Write-Host "   [S] Skip / Continue with local snapshot advisory mode (Default)" -ForegroundColor White
        $kChoice = Read-Host "   Select [L/S] (Default: S)"

        if ($kChoice -match "^[lL]") {
            Write-Host "   Launching Zerodha Kite secure interactive login..." -ForegroundColor Cyan
            & $pyExe "$ScriptDir\tools\kite_portfolio.py" --login
            if (Test-Path $kiteTokenFile) {
                try {
                    $tokData = Get-Content $kiteTokenFile -Raw | ConvertFrom-Json
                    if ($tokData.access_token) {
                        $kiteActive = $true
                        Write-Host "   [OK] Zerodha Kite session established successfully!" -ForegroundColor Green
                    }
                }
                catch {}
            }
        }
        else {
            Write-Host "   Continuing with offline snapshot data (storage/my_holdings.json)." -ForegroundColor DarkGray
        }
    }
    else {
        Write-Host "   Proceeding in offline/snapshot advisory mode." -ForegroundColor DarkGray
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
    Write-Host "  ANALYSIS CONFIGURATION WIZARD" -ForegroundColor Cyan
    Write-Host "------------------------------------------------------------------------" -ForegroundColor DarkCyan
    Write-Host "   Analysis is very fast because the engine is 100% rule-based (no slow LLM)" -ForegroundColor DarkGray
    Write-Host "   and caches calculations for 12 hours unless a full refresh is requested." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "   Select Execution Mode:" -ForegroundColor White
    Write-Host "   [1] All 3 Universes (Curated + Nifty 100 + Midcap 100) - Incremental Analysis (Default)" -ForegroundColor Cyan
    Write-Host "   [2] My Curated List (symbols.json) - Incremental Analysis (Fast, 12h cache)" -ForegroundColor White
    Write-Host "   [3] My Curated List (symbols.json) - Complete Fresh Analysis (--force: Re-evaluates from scratch)" -ForegroundColor White
    Write-Host "   [4] Specific Target Symbol(s) (e.g. RELIANCE,TCS,BEL)" -ForegroundColor White
    Write-Host "   [5] Portfolio Holdings Only (diagnostics for your current holdings)" -ForegroundColor White
    Write-Host "   [6] Nifty Midcap 100 Stocks Analysis (symbols_midcap_250.json)" -ForegroundColor Green
    Write-Host "   [7] Nifty 100 Large Cap Analysis (symbols_nse_all.json)" -ForegroundColor Cyan

    $modeSelect = Read-Host "`n   Enter mode [1-7] (Default: 1)"

    switch ($modeSelect.Trim()) {
        "2" {
            Write-Host "   Curated Watchlist Incremental Analysis selected (fast, cache-assisted)." -ForegroundColor Green
        }
        "3" {
            $Force = $true
            Write-Host "   [!] Complete Fresh Analysis selected: Recomputing all 6 agents for every stock in symbols.json." -ForegroundColor Yellow
        }
        "4" {
            $customSyms = Read-Host "   Enter stock symbol(s) comma-separated (e.g. RELIANCE,TCS,BEL)"
            if ($customSyms.Trim()) {
                $Symbol = $customSyms.Trim()
                Write-Host "   Target symbol(s): $Symbol" -ForegroundColor Yellow
            }
        }
        "5" {
            $portfolioOnly = $true
            Write-Host "   Portfolio-Only mode selected." -ForegroundColor Yellow
        }
        "6" {
            $Midcap250 = $true
            Write-Host "   [!] Nifty Midcap 100 Stocks Analysis selected." -ForegroundColor Green
            Write-Host "   Will use symbols_midcap_250.json (your symbols.json is kept untouched)." -ForegroundColor DarkGray
            $limInput = Read-Host "   Optional: Enter limit on number of midcap stocks to scan (e.g. 50, or Enter for ALL 100)"
            if ($limInput.Trim() -match "^\d+$") {
                $Limit = [int]$limInput.Trim()
                Write-Host "   Scan limit set to first $Limit stocks." -ForegroundColor Yellow
            }
        }
        "7" {
            $AllNse = $true
            Write-Host "   [!] Nifty 100 Large Cap Analysis selected." -ForegroundColor Cyan
            Write-Host "   Will use symbols_nse_all.json (your symbols.json is kept untouched)." -ForegroundColor DarkGray
            $allNseFile = Join-Path $ScriptDir "symbols_nse_all.json"
            if (-not (Test-Path $allNseFile)) {
                Write-Host "   symbols_nse_all.json not found. Fetching Nifty 100 index constituents..." -ForegroundColor Yellow
                & $pyExe "$ScriptDir\tools\refresh_index_universe.py"
            }
            $limInput = Read-Host "   Optional: Enter limit on number of stocks to scan (e.g. 50, or Enter for ALL 100)"
            if ($limInput.Trim() -match "^\d+$") {
                $Limit = [int]$limInput.Trim()
                Write-Host "   Scan limit set to first $Limit stocks." -ForegroundColor Yellow
            }
        }
        default {
            $AllUniverses = $true
            Write-Host "   All 3 Universes Incremental Analysis selected (Curated + Nifty 100 + Midcap 100)." -ForegroundColor Cyan
        }
    }

    if (-not $portfolioOnly) {
        $syncPrompt = Read-Host "`n   Sync split-adjusted historical data and Excel workbook? [Y/n] (Default: Y)"
        if ($syncPrompt -match "^[nN]") {
            $runSync = $false
            Write-Host "   Historical sync skipped." -ForegroundColor DarkGray
        }
        else {
            Write-Host "   Historical data sync enabled." -ForegroundColor Green
        }
    }
    Write-Host "------------------------------------------------------------------------" -ForegroundColor DarkCyan
}
elseif (($Symbol -eq "") -and (-not $Portfolio) -and (-not $AllNse) -and (-not $Midcap250) -and ($SymbolsFile -eq "")) {
    $AllUniverses = $true
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
    }
    catch {
        $serverRunning = $false
    }
}
$DashUrl = "http://localhost:$activePort"

if ($serverRunning) {
    Write-Host "`n   [OK] Realtime Dashboard Server already active at $DashUrl" -ForegroundColor Green
}
else {
    try {
        Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue | 
            Where-Object { $_.CommandLine -like "*dashboard_server.py*" } | 
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    }
    catch {}

    Write-Host "`n   Launching Realtime Dashboard Server on $DashUrl..." -ForegroundColor Yellow
    Start-Process -FilePath $pyExe -ArgumentList @("$ScriptDir\dashboard_server.py", "--port", "$DashPort", "--no-browser") -WorkingDirectory $ScriptDir -WindowStyle Hidden

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
            }
            catch {}
        }
        if ($serverRunning) { break }
        $retries--
    }
    $DashUrl = "http://localhost:$activePort"
    if ($serverRunning) {
        Write-Host "   [OK] Dashboard Server started successfully at $DashUrl" -ForegroundColor Green
    }
}

$FrontendUrl = "http://localhost:4200"

# Ensure Angular dev server is active on port 4200 and launch Angular URL in browser
if (-not $NonInteractive) {
    try {
        $ngRunning = [bool](Get-NetTCPConnection -LocalPort 4200 -State Listen -ErrorAction SilentlyContinue)
        if (-not $ngRunning) {
            $frontendDir = Join-Path $ScriptDir "frontend"
            if (Test-Path $frontendDir) {
                Write-Host "   Starting Angular dev server on $FrontendUrl..." -ForegroundColor Yellow
                Start-Process -FilePath "cmd.exe" -ArgumentList @("/c", "npm start") -WorkingDirectory $frontendDir -WindowStyle Minimized
            }
        }
        Start-Process $FrontendUrl
        Write-Host "   Angular Workstation opened in browser: $FrontendUrl" -ForegroundColor Cyan
    }
    catch {}
}

# -----------------------------------------------------------------------------
# STEP 6: Historical Data Sync & Excel Export
# -----------------------------------------------------------------------------
if ($runSync -and (-not $portfolioOnly)) {
    Write-Host ""
    Write-Host "[4/5] Syncing split-adjusted historical data and updating Excel dataset..." -ForegroundColor Yellow
    try {
        if ($AllUniverses) {
            & $pyExe "$ScriptDir\tools\historical_data_tools.py" --sync --symbols-file "$ScriptDir\symbols.json"
            & $pyExe "$ScriptDir\tools\historical_data_tools.py" --sync --all-nse
            & $pyExe "$ScriptDir\tools\historical_data_tools.py" --sync --excel --symbols-file "$ScriptDir\symbols_midcap_250.json"
        }
        else {
            $syncArgs = @("--sync", "--excel")
            if ($Midcap250) { $syncArgs += @("--symbols-file", "$ScriptDir\symbols_midcap_250.json") }
            elseif ($AllNse) { $syncArgs += "--all-nse" }
            elseif ($SymbolsFile) { $syncArgs += @("--symbols-file", $SymbolsFile) }
            & $pyExe "$ScriptDir\tools\historical_data_tools.py" @syncArgs
        }
    }
    catch {
        Write-Host "   Data sync notice: Continuing with existing historical dataset..." -ForegroundColor DarkYellow
    }
}

# -----------------------------------------------------------------------------
# STEP 7: Run Multi-Agent Analysis Pipeline
# -----------------------------------------------------------------------------
if (-not $portfolioOnly) {
    Write-Host ""
    Write-Host "[5/5] Triggering Multi-Agent Analysis Pipeline (rule-based, no LLM)..." -ForegroundColor Green
    if ($AllUniverses) {
        Write-Host "   Scope: All 3 Universes (Curated Watchlist + Nifty 100 Large Cap + Nifty Midcap 100)" -ForegroundColor Cyan
    }
    elseif ($Midcap250) {
        Write-Host "   Scope: Nifty Midcap 100 Universe ($ScriptDir\symbols_midcap_250.json)" -ForegroundColor Green
    }
    elseif ($AllNse) {
        Write-Host "   Scope: Nifty 100 Large Cap Universe ($ScriptDir\symbols_nse_all.json)" -ForegroundColor Cyan
    }
    elseif ($SymbolsFile) {
        Write-Host "   Scope: Custom Symbols File ($SymbolsFile)" -ForegroundColor Cyan
    }
    else {
        Write-Host "   Scope: Curated Watchlist ($ScriptDir\symbols.json)" -ForegroundColor DarkGray
    }
    Write-Host "   Press Ctrl+C at any time to interrupt cleanly." -ForegroundColor DarkGray
    Write-Host ""

    $baseArgs = @()
    if ($Force) { $baseArgs += "--force" }
    if ($Symbol -and $Symbol.Trim() -ne "") { $baseArgs += @("--symbol", $Symbol.Trim()) }
    if ($Limit -gt 0) { $baseArgs += @("--limit", "$Limit") }

    try {
        if ($AllUniverses) {
            Write-Host "   >> [1/3] Curated Watchlist (symbols.json)..." -ForegroundColor Yellow
            & $pyExe "$ScriptDir\main.py" @baseArgs

            Write-Host "`n   >> [2/3] Nifty 100 Large Cap (symbols_nse_all.json)..." -ForegroundColor Cyan
            $largeArgs = $baseArgs + @("--all-nse")
            & $pyExe "$ScriptDir\main.py" @largeArgs

            Write-Host "`n   >> [3/3] Nifty Midcap 100 (symbols_midcap_250.json)..." -ForegroundColor Green
            $midArgs = $baseArgs + @("--midcap-250")
            & $pyExe "$ScriptDir\main.py" @midArgs
        }
        else {
            $mainArgs = @() + $baseArgs
            if ($Midcap250) { $mainArgs += "--midcap-250" }
            elseif ($AllNse) { $mainArgs += "--all-nse" }
            elseif ($SymbolsFile) { $mainArgs += @("--symbols-file", $SymbolsFile) }
            & $pyExe "$ScriptDir\main.py" @mainArgs
        }
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
    Write-Host "Generating Portfolio Diagnostics and Action Strategy Report..." -ForegroundColor Green
    try {
        & $pyExe "$ScriptDir\tools\kite_portfolio.py" --report
    }
    catch {
        Write-Host "   Notice: Portfolio report generation skipped." -ForegroundColor DarkGray
    }
}

$predReport = if ($AllUniverses) { "$ScriptDir\reports\NSE_Stock_Predictions_latest.md (+ NSE_All_Stocks_Predictions_latest.md)" } elseif ($AllNse) { "$ScriptDir\reports\NSE_All_Stocks_Predictions_latest.md" } else { "$ScriptDir\reports\NSE_Stock_Predictions_latest.md" }

Write-Host ""
Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "  RUN COMPLETE! Reports and dashboard are ready:" -ForegroundColor Cyan
Write-Host "  * Angular Analyst Workstation: $FrontendUrl" -ForegroundColor Green
Write-Host "  * Backend HTTP API Server:     $DashUrl" -ForegroundColor Cyan
Write-Host "  * Daily Predictions Report:   $predReport" -ForegroundColor Green
Write-Host "  * Portfolio Action Report:    $ScriptDir\reports\Portfolio_Holdings_Analysis_latest.md" -ForegroundColor Green
Write-Host "  * Historical Excel Dataset:   $ScriptDir\reports\NSE_Historical_Data.xlsx" -ForegroundColor Green
Write-Host "========================================================================" -ForegroundColor Cyan
