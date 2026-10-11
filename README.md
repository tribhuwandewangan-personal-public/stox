# NSE-Data-bank & Multi-Agent Stock Predictor

This repository contains corporate-action adjusted historical stock market data paired with a zero-cost **LangGraph & LangChain Multi-Agent RAG Stock Prediction System** powered by **Ollama (`qwen2.5:7b`)**. Historical data is automatically synced to SQLite (`storage/cache.db`) and exported to Excel ([`reports/NSE_Historical_Data.xlsx`](file:///c:/Users/tdewa/Documents/LearnPython/NSE-Data-bank/reports/NSE_Historical_Data.xlsx)).

---

## 🤖 Multi-Agent Architecture

The system uses 8 specialized AI agents working together to evaluate equities listed in `symbols.json`:

1. **Supervisor / Orchestrator Agent**: Manages execution flow, checks incremental SQLite cache (`storage/cache.db`), and orchestrates agent runs.
2. **Historical Data RAG Agent**: Evaluates corporate-action adjusted price history, volume surges, and long-term momentum trends.
3. **Technical Analysis Agent**: Computes SMA 20/50/200, RSI, MACD, Bollinger Bands, and Support/Resistance pivot levels.
4. **Real-Time News & Sentiment Agent**: Scrapes online news using free RSS & DuckDuckGo search and calculates sentiment scores.
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

## 📰 Daily Multi-Source Market & Stock News Reports

The system continuously collects and curates online financial news from **Google News RSS**, **The Economic Times**, **Livemint**, **Moneycontrol**, and **DuckDuckGo**, generating exactly two reports per day in **`news_reports/YYYY-MM-DD/`**:

1. **Generic Market & Macro News** ([`general_market_news.md`](file:///c:/Users/tdewa/Documents/LearnPython/NSE-Data-bank/news_reports/latest_market_news.md)):
   - **Crude Oil Price & Trend** (Brent & WTI prices, daily changes, and sectoral transmission impact on OMCs, aviation, paints, chemicals)
   - **Indian Rupee (USD/INR) Dynamics** (exchange rates, forex reserves, and IT/pharma vs importer impacts)
   - **Global Market Cues** (S&P 500, Nasdaq, US 10Y Yields, DXY Dollar Index, Gold)
   - **Domestic Catalysts & FII/DII Flows**
   - **Curated Market-Moving Headlines** from *The Economic Times*, *Livemint*, and *Moneycontrol*

2. **Stock-Specific News Digest** ([`stock_specific_news.md`](file:///c:/Users/tdewa/Documents/LearnPython/NSE-Data-bank/news_reports/latest_stocks_news.md)):
   - A single consolidated file containing news from multiple sources for all tracked stocks in `symbols.json`.
   - Quick navigation index, article counts, source attribution, direct article URLs, publication dates, and bullish/neutral/bearish sentiment ratings.

Run news generation independently anytime:
```bash
uv run python generate_news_report.py
```

---

## ⚡ Incremental Data Storage

All parsed metrics, news, macro sentiment, and agent reports are stored incrementally in **`storage/cache.db`** (SQLite). Re-running analysis utilizes cached data when fresh (<12h old), reducing analysis time and network overhead.
