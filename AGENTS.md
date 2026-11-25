# Agent & Developer Rules: Stox Project

## 🛡️ STRICT SAFETY RULE: READ-ONLY & ADVISORY MODE ONLY

### 1. Zero Real-Money Execution / Order Placement
- Under NO circumstances may this application place, modify, or cancel orders on Zerodha Kite Connect or any other brokerage/exchange API.
- The application is strictly an **advisory and quantitative intelligence platform**.
- The following KiteConnect methods and concepts are strictly **FORBIDDEN** from being written, imported, or executed:
  - `place_order`
  - `modify_order`
  - `cancel_order`
  - `order_margins`
  - Any automated trading, algorithmic trade execution, or live order submission.

### 2. Permitted Broker Operations (Read-Only Only)
- The only permitted broker operations are strictly read-only:
  - `kite.holdings()` — Reading user delivery holdings for portfolio diagnostics.
  - `kite.ltp(...)` / `kite.quote(...)` — Reading market price telemetry.
  - Interactive login session generation for daily access token acquisition.

### 3. Credential & Holdings Privacy
- Never log, commit, or push API keys, API secrets, access tokens, or personal holding snapshot files to Git.
- Files matching `storage/kite_token.json`, `storage/my_holdings.json`, `*credentials*.json`, and `*.env*` must remain strictly gitignored at all times.
- If credentials or tokens are absent or expired, the system must degrade gracefully (fallback to offline snapshot or user prompt), never crash.

### 4. Deterministic Engine Invariant
- All calculations, scores, stop losses, price targets, risk levels, and verdicts must be deterministic and rule-based (no LLM hallucinations for quantitative numbers).
- Automated regression tests must verify that order placement methods remain absent across the entire codebase.

## Project Quick-Reference
- **Context File**: Read `CONTEXT.md` in the repo root first before exploring or grepping broadly across the codebase.
- **Runtime Ports**:
  - Backend HTTP API (`dashboard_server.py`): `http://127.0.0.1:8765` (no hot-reload; run `.\cleanup_server.ps1 -Restart` after Python edits)
  - Angular 22 dev server (`frontend/` `npm start`): `http://localhost:4200` (proxies `/api`, `/ws`, `/news_reports`, `/reports` -> `:8765`)
- **Key Paths**:
  - Universes & Config: `config.py`, `symbols.json` (curated), `symbols_midcap_250.json` (250 midcap), `symbols_nse_all.json` (all NSE)
  - Backend API: `dashboard_server.py`, `api/routes.py`, `api/services.py` (`get_stocks_response_body`, `get_all_stock_data`)
  - Frontend Root & State: `frontend/src/app.ts`, `frontend/src/app/core/stores/stocks.store.ts`, `frontend/src/app/core/services/api.service.ts`
  - Frontend Dashboard UI: `frontend/src/app/features/shell/header.component.ts`, `frontend/src/app/features/dashboard/`
- **Commands**:
  - Restart backend: `.\cleanup_server.ps1 -Restart`
  - Backend tests: `.\.venv\Scripts\python.exe -m unittest discover tests`
  - Frontend build: `cd frontend; npm run build`

## Frontend Grid & Centralized Styling Context
- **Shared Data Grid**: Use `<app-stox-grid>` (`frontend/src/app/shared/data-grid/stox-grid.component.ts`, powered by `@tanstack/angular-table`) for all tabular views instead of raw `<table>` elements.
  - Supports `StoxGridColumn<T>` (`id`, `header`, `accessorFn`, `cellTemplate`, `sortable`, `align`, `headerClass`, `cellClass`), `[defaultSort]`, `[clickable]`, `[emptyText]`, `[rowClass]`, and `[rowSymbolFn]`.
  - **Angular Gotcha**: Any `<ng-template>` referenced via `@ViewChild(..., { static: true })` MUST be placed outside `@if` / `*ngIf` blocks in the parent template.
- **Centralized Grid & Banner CSS**: `frontend/src/app/shared/data-grid/stox-grid.css` (imported globally in `frontend/src/styles.css`) is the single source of truth for all grid, cell chip/badge, collapsible banner, and `[data-theme='light']` styles. Do **not** duplicate `.stox-grid-*` or cell chip CSS inside individual components.
  - **Collapsible Banners**: `.stox-banner-wrap`, `.stox-banner-card` (`.stox-banner-card--emerald`), `.stox-banner-header`, `.stox-banner-title-block`, `.stox-banner-heading`, `.stox-banner-sub`, `.stox-banner-controls`, `.stox-banner-toggle`, `.stox-banner-body`, `.stox-banner-tip` (`.stox-banner-tip--emerald`).
  - **Cell Pills & Chips**: `.sym-pill` (`.sym-pill--green`), `.trig-chip` / `.entry-chip`, `.sl-chip`, `.upside-pill` (`.upside-pill--neg`), `.rr-pill`, `.score-pill` (`.high-score`), `.val-pill`, `.verdict-pill`, `.verdict-badge`, `.category-badge`, `.stage-badge`, `.micro-tags` / `.micro-tag` (`.micro-tag--good`).
  - **Column Widths & Utilities**: `.col-num`, `.col-mono`, `.col-muted`, `.accent-green`, `.accent-sky`, `.accent-red`. Keep `.col-pattern` / `.col-proj` compact (`min-width: 140px; max-width: 210px`) with 2-line `.proj-line` clamping so numeric/chip columns retain breathing room.
