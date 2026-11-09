# Phase 3: Component Ports — NSE Stock Predictor Angular Frontend

This document outlines the component structure for Phase 3, tracking progress as each piece is ported from the legacy `static/index.html`.

## Component Hierarchy

```
AppComponent (root)
├── HeaderComponent
│   ├── TitleBar
│   ├── MarketBadge
│   └── NavButtons (re-analyze, settings)
├── BulletinComponent (collapsible banner)
├── SidebarComponent
│   ├── SearchBox
│   ├── SectorFilter (chips)
│   ├── VerdictTabs (BUY/ACCUMULATE/HOLD/SELL/PENDING counts)
│   └── StockList
│       └── StockItemComponent (name, sector, price, verdict)
├── MainAreaComponent
│   ├── TickerRibbon (top performers, top losers)
│   ├── StockGridComponent
│   │   └── StockCardComponent (repeater, trackBy symbol)
│   │       ├── Symbol, name, sector
│   │       ├── Sparkline (25 candles)
│   │       ├── Latest price + change %
│   │       ├── Verdict badge
│   │       ├── Pattern badges
│   │       ├── Event badge
│   │       └── Click → open detail modal
│   └── BottomArea
│       ├── StockDetailModal
│       │   ├── CandleChartComponent (port drawCandleChart)
│       │   ├── PatternDetailsComponent
│       │   ├── EventsPanelComponent
│       │   ├── LongTermPanelComponent
│       │   └── ReAnalyzeButton
│       ├── PctCalculatorComponent (CDK drag)
│       ├── AddSymbolModalComponent
│       ├── AccuracyModalComponent
│       └── WorkflowModalComponent
└── FooterComponent (queue status, engine label, errors)
```

## Port Checklist

### Level 0: Foundation (Already Done ✅)
- [x] Models (stock.model.ts)
- [x] API service (api.service.ts)
- [x] WebSocket service (ws.service.ts)
- [x] State store (stocks.store.ts)
- [x] Utils (price.ts, verdict.ts)
- [x] Global styles (styles.css)
- [x] Root component (app.ts)

### Level 1: Shell (Priority 1)
Components that appear on every page.

#### HeaderComponent
**Legacy code:** `static/index.html` lines ~80–150 (top navbar)

- [ ] Title bar with icon
- [ ] Market state badge (premarket/open/closing/closed)
- [ ] Queue status display
- [ ] Engine label
- [ ] Settings/info buttons

**CSS:** `.top-bar`, `.bar-left`, `.bar-right`, `.badge`, `.btn-*`

**Tests:**
- Displays engine label from status
- Shows market state from quote_poller
- Queue counts update on /api/status refresh

---

#### BulletinComponent
**Legacy code:** `static/index.html` lines ~200–250 (bulletin banner)

- [ ] Collapsible banner
- [ ] Latest market bulletin (from cache_mgr.get_latest_market_bulletin())
- [ ] Close button

**CSS:** `.bulletin`, `.bulletin-content`, `.close-btn`

**Tests:**
- Fetches and displays latest bulletin
- Collapse/expand toggle works

---

### Level 2: Navigation & Sidebar (Priority 2)
Filtering and stock selection.

#### SidebarComponent
**Legacy code:** `static/index.html` lines ~1500–1800 (sidebar HTML)

- [ ] Search box (reactive, filters stock-grid live)
- [ ] Sector filter chips (GET from stocks, click = filter)
- [ ] Verdict tabs (BUY, ACCUMULATE, HOLD, REDUCE, SELL, PENDING with counts)
- [ ] Stock list (flat view, toggleable by sector)
- [ ] Collapse/expand (localStorage `nse_sidebar_state`)
- [ ] Mobile drawer

**CSS:** `.sidebar`, `.sidebar-search`, `.sidebar-chips`, `.sidebar-item-*`, `.verdict-tabs`

**Store usage:**
- `stocksStore.setSectorFilter(sector)`
- `stocksStore.setSearchFilter(query)`
- `stocksStore.setVerdictFilter(verdict)`
- `stocksStore.verdictCounts` (computed)
- `stocksStore.filteredStocks` (computed)

**Tests:**
- Verdict tabs show correct counts
- Clicking a sector filters grid
- Searching updates grid live
- Mobile drawer opens/closes

---

#### StockItemComponent
**Legacy code:** Sidebar list item (reused for sidebar + mobile)

- [ ] Symbol, name (from stock object)
- [ ] Latest price with change % (live updates via WebSocket)
- [ ] Verdict badge (click = select stock, open detail modal)
- [ ] Stale indicator (if is_stale)

**CSS:** `.sidebar-item`, `.sidebar-item-name`, `.sidebar-item-price`

**Tests:**
- Price updates from store signals
- Clicking selects stock and opens modal

---

### Level 3: Main Grid (Priority 3)
Core stock display.

#### StockGridComponent
**Legacy code:** `static/index.html` lines ~1100–1400 (grid + card templates)

- [ ] CSS Grid layout (4 columns, responsive)
- [ ] No full re-render (use trackBy)
- [ ] Infinite scroll placeholder (optional, load more)

**CSS:** `.stock-grid`, `.stock-card`, responsive breakpoints

**Tests:**
- Renders correct number of cards
- trackBy prevents unnecessary re-renders
- Grid reflows on sidebar collapse

---

#### StockCardComponent
**Legacy code:** `static/index.html` card template

- [ ] Symbol, name, sector (text)
- [ ] Sparkline (last 25 candles, mini line chart)
- [ ] Latest price + change %, source tag
- [ ] Verdict badge (BUY/ACCUMULATE/HOLD/SELL/PENDING + confidence)
- [ ] 2–3 pattern badges (if detected)
- [ ] Event badge (if upcoming events)
- [ ] Click = select stock, open detail modal
- [ ] Hover effect

**CSS:** `.stock-card`, `.stock-card-*`, `.sparkline`, `.pattern-badge`, `.event-badge`

**Components needed:**
- SparklineComponent (canvas chart, 25 points)
- PatternBadgesComponent (reusable badge list)
- EventBadgeComponent (collapsible event tooltip)

**Tests:**
- Card renders all fields
- Click opens modal with correct symbol
- Prices update live (WebSocket)
- Stale indicator appears after 72h

---

### Level 4: Modals (Priority 4)
Detail views and dialogs.

#### StockDetailModal
**Legacy code:** `static/index.html` modal section (~lines 2500–3800)

- [ ] Header: symbol, close button
- [ ] Tabs or scrollable sections:
  - Technical Analysis (patterns, indicators)
  - Long-term Strategy (target, horizon, peers)
  - Events (upcoming catalysts)
  - Reports (link to markdown viewer)
- [ ] CandleChart (port from legacy drawCandleChart, 3801–4017 lines)
- [ ] Re-Analyze button (POST /api/trigger)

**CSS:** `.modal`, `.modal-header`, `.modal-body`, `.modal-tabs`, `.modal-tab-content`

**Components needed:**
- CandleChartComponent (ResizeObserver, canvas drawing)
- PatternDetailsComponent (expandable list)
- EventsPanelComponent (list + links)
- LongTermPanelComponent (stats + peer list)

**Tests:**
- Opens for correct stock
- Chart renders without errors
- Re-Analyze button triggers analysis
- Tabs switch content

---

#### PctCalculatorComponent
**Legacy code:** `static/index.html` pct-tool section (~lines 700–1000)

Port the existing, fully-tested Target/SL calculator:
- [ ] BUY PRICE input
- [ ] TARGET (price ↔ %)
- [ ] STOP LOSS (price ↔ %)
- [ ] "Use live" button (fills from current price)
- [ ] Summary: target + stop prices + percentages + R:R ratio
- [ ] Drag-move with CDK (cdkDrag directive)
- [ ] Per-symbol buy price storage (localStorage `stox.pctTool.buy.XXX`)

**CSS:** `.pct-tool`, `.pct-row`, `.pct-detail`, `.pct-summary`, `.pct-rr`, `.pct-live`

**Utils already exist:** pctTool() calc logic (ported from legacy JS)

**Tests:** (28 existing jsdom tests can become vitest tests)
- Price ↔ % sync works
- R:R calculated correctly
- "Use live" fills correctly
- Buy price persists per symbol
- No NaN/Infinity shown

**Notes:**
- The jsdom harness (`stox_calc_check.js`) already tests all this
- Port the exact same logic to TypeScript (utils/pct.ts)
- Angular reactive forms handle state

---

#### AddSymbolComponent
**Legacy code:** `static/index.html` add-symbol modal

- [ ] Search internet (GET /api/search-symbol?q=ABC)
- [ ] Results list (symbol, name, sector, exchange)
- [ ] Add button (POST /api/add-symbol)
- [ ] Manual entry fallback

**Tests:**
- Search works (call ApiService.searchSymbol)
- Add button POSTs with correct headers (CSRF)
- Stock appears in grid after add

---

#### AccuracyModalComponent
**Legacy code:** `static/index.html` accuracy-body section

- [ ] Fetch GET /api/accuracy
- [ ] Display stats: total, resolved, accuracy by verdict, R:R avg, recovery time
- [ ] Format percentages, numbers

**Tests:**
- Data fetches and displays
- Numbers formatted correctly

---

#### WorkflowModalComponent
**Legacy code:** Queue status display + manual trigger

- [ ] Show queue (pending, in_progress, completed counts)
- [ ] Manual trigger form (POST /api/trigger)
- [ ] Status polling feedback

**Tests:**
- Queue counts display
- Trigger POSTs correctly

---

### Level 5: Charts (Priority 5, Complex)

#### CandleChartComponent
**Legacy code:** `static/index.html` drawCandleChart() (~lines 3801–4017)

**Approach:**
1. Port the canvas drawing logic to a pure function: `drawCandles(ctx, data, width, height)`
2. Component handles ResizeObserver + re-draw on resize
3. Test the draw function with snapshots (Playwright screenshots)

**Tests:**
- Chart renders without errors
- Updates on new candles
- Responsive to container resize
- Scales correctly

---

#### TickerRibbon (Optional, Phase 3.5)
**Legacy code:** Ticker-style top performers / top losers

- [ ] Top 5 BUY recommendations
- [ ] Top 5 SELL recommendations
- [ ] Animated scroll

---

## Sprint Plan

### Week 1 (Days 1–2)
- [ ] HeaderComponent + BulletinComponent (easy, few bindings)
- [ ] SidebarComponent + StockItemComponent (moderate, filtering logic)
- [ ] Basic layout (header top, sidebar left, main right)

### Week 2 (Days 3–4)
- [ ] StockGridComponent + StockCardComponent (main work)
- [ ] SparklineComponent (canvas chart)
- [ ] PatternBadgesComponent + EventBadgeComponent (reusable)
- [ ] Live price updates via WebSocket

### Week 3 (Days 5–6)
- [ ] StockDetailModal + CandleChartComponent (port chart logic)
- [ ] PatternDetailsComponent + EventsPanelComponent + LongTermPanelComponent
- [ ] Modal opening/closing, routing

### Week 4 (Days 7–8)
- [ ] PctCalculatorComponent (port existing logic, add CDK drag)
- [ ] AddSymbolComponent + AccuracyComponent + WorkflowComponent
- [ ] End-to-end test: app running locally talking to backend

## Testing Strategy

### Unit Tests (Vitest)
- Utility functions (price, verdict)
- Store actions and computations
- Component input/output (with mocked services)

### Integration Tests
- WebSocket connection + message handling
- API calls with CSRF headers
- Store updates from API responses

### E2E Tests (Playwright)
- Side-by-side comparison with legacy UI
- Screenshot diffs (pixel regression)
- User workflows: search, filter, open modal, calculate, add stock
- Real stock data flow end-to-end

## CSS Migration

**Source:** Extract from `static/index.html` style block (~2,160 lines)

**Strategy:**
1. Global theme variables (already done in `styles.css`)
2. Component scoped CSS (each component gets its styles)
3. Map CSS class prefixes:
   - `.top-bar` → HeaderComponent.css
   - `.sidebar` → SidebarComponent.css
   - `.stock-card` → StockCardComponent.css
   - `.modal` → StockDetailModal.css
   - etc.

No visual change to user — all styling preserved, just reorganized.

## Cleanup & Dead Code Removal

Remove from legacy `static/index.html` (after Angular version is live):
- Duplicate search functions (lines 4047–4202)
- `exportAsHTML` function and `.btn-export` (200 lines)
- Hard-coded `curated` table (33 symbols)
- Unused CSS classes: `.pct-result`, `.pct-rr`, `.pill-already-added`, `--accent-teal`
- `safeJsonParse` (no longer needed)
- Comments mentioning localhost:8765 errors

## Heroku Deployment Groundwork

**After Phase 3 is done:**
- Static file serving: `app.mount("/", StaticFiles(..., html=True))`
- Build step: `frontend/dist/stox/browser` must exist before `python dashboard_server.py`
- Environment: `TZ=Asia/Kolkata` in Procfile
- Database: Postgres setup (deferred to Phase 4 docs)

## Definition of Done (Phase 3)

- [ ] All components ported and rendering
- [ ] All CSS migrated, no visual regressions
- [ ] WebSocket broadcasts prices live
- [ ] All modals functional (detail, pct, add, accuracy, workflow)
- [ ] Sidebar filtering works
- [ ] Search works
- [ ] Live tests pass (93+)
- [ ] E2E tests (Playwright side-by-side) pass
- [ ] App runs locally (`ng serve` + `python dashboard_server.py`) without errors
- [ ] Legacy UI and Angular UI show identical data (snapshots match)
- [ ] Ready for sign-off → retire `static/index.html`

## Notes

- Use `signal()` and `computed()` for all state (no RxJS subscriptions unless necessary)
- Use `trackBy` in all `*ngFor` loops
- All text via Angular bindings (auto-escaped)
- No `innerHTML` except markdown viewer (backend-rendered)
- CDK for drag, modal, overlay
- Vitest + Playwright for coverage
- Commit at each component milestone (tight feedback loop)
