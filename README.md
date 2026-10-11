[![GetBhavCopy](https://github.com/tilak999/NSE-Data-bank/actions/workflows/autoDownload.yml/badge.svg?branch=main)](https://github.com/tilak999/NSE-Data-bank/actions/workflows/autoDownload.yml)

# NSE-Data-bank & Multi-Agent Stock Predictor

This repository contains daily NSE Bhavcopy stock data spanning over two decades, paired with a zero-cost **LangGraph & LangChain Multi-Agent RAG Stock Prediction System** powered by **Ollama (`qwen2.5:7b`)**.

---

## 🤖 Multi-Agent Architecture

The system uses 8 specialized AI agents working together to evaluate equities listed in `symbols.json`:

1. **Supervisor / Orchestrator Agent**: Manages execution flow, checks incremental SQLite cache (`storage/cache.db`), and orchestrates agent runs.
2. **Historical Data RAG Agent**: Performs RAG over local daily Bhavcopy CSV files in `data/`, evaluating price action memory, volume surges, and delivery trends.
3. **Technical Analysis Agent**: Computes SMA 20/50/200, RSI, MACD, Bollinger Bands, and Support/Resistance pivot levels.
4. **Real-Time News & Sentiment Agent**: Scrapes online news using free DuckDuckGo search and calculates sentiment scores.
5. **Global Macro & Market Agent**: Evaluates global market indicators (S&P 500, Nasdaq, Crude Oil, DXY Dollar Index, Gold).
6. **Fundamental Analyst Agent**: Evaluates financial health (P/E, P/B, ROE, Debt/Equity, Revenue Growth).
7. **Risk & Volatility Agent**: Computes Beta, 95% VaR, Maximum Drawdown, stop-loss placement, and risk-reward ratio.
8. **Master Prediction Synthesizer Agent**: Aggregates multi-agent findings, resolves conflicting signals, and outputs final price targets, confidence ratings, and forecast reports.

---

## 🚀 One-Click Run & Automated Report Generation

To pull the latest repo updates, sync dependencies via `uv`, analyze target stocks in `symbols.json`, and generate Markdown reports in `reports/`:

```powershell
.\run_analysis.ps1
```

Or run via Python directly:
```bash
uv run python main.py
```

---

## ⚙️ Target Stock Configuration (`symbols.json`)

Stock symbols analyzed by the multi-agent system are defined in [`symbols.json`](file:///c:/Users/tdewa/Documents/LearnPython/NSE-Data-bank/symbols.json). You can add or edit symbols anytime:

```json
{
  "symbols": [
    { "symbol": "RELIANCE", "name": "Reliance Industries Limited", "sector": "Energy & Retail" },
    { "symbol": "TCS", "name": "Tata Consultancy Services Limited", "sector": "Information Technology" },
    { "symbol": "INFY", "name": "Infosys Limited", "sector": "Information Technology" }
  ]
}
```

---

## ⚡ Incremental Data Storage

All parsed metrics, news, macro sentiment, and agent reports are stored incrementally in **`storage/cache.db`** (SQLite). Re-running analysis utilizes cached data when fresh (<12h old), reducing analysis time and network overhead.
