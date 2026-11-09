# Next Session Handoff: Phase 3 Level 2 — Stock Grid & Sidebar

**Previous Session Status:** ✅ COMPLETE  
**Final Commit:** 532fa59 (Session final status)  
**Tests:** 93/93 passing  
**Next Task:** Phase 3 Level 2 (Stock Grid)  

---

## 🎯 What's Ready for You

### Completed Work (Don't Redo!)
✅ Phase 1: Backend service extraction  
✅ Phase 2: Angular 22 scaffold + core services  
✅ Phase 3 Level 1: Shell components (header, bulletin)  

### Current App Status
- Header showing market badge, queue status, engine label ✅
- Bulletin banner with collapsible animation ✅
- Dashboard shows "Level 2 coming soon" placeholder
- WebSocket connected and polling fallback ready
- All 93 Python tests passing
- TypeScript verified, no compilation errors

---

## 📋 Phase 3 Level 2: Stock Grid (Your Task)

### Components to Port
1. **StockGridComponent** (~150 LOC)
   - 4-column responsive grid
   - `trackBy` for performance
   - Filters from sidebar
   - Click → select stock, open modal (Level 3)

2. **StockCardComponent** (~200 LOC)
   - Symbol, name, sector (text)
   - Latest price + change %
   - Verdict badge (BUY/ACCUMULATE/HOLD/SELL/PENDING)
   - 2–3 pattern badges
   - Event badge
   - Sparkline (mini chart)
   - Responsive hover

3. **SparklineComponent** (~100 LOC)
   - Canvas chart (port from legacy)
   - 25 last candles
   - Auto-scale
   - ResizeObserver for responsive

4. **SidebarComponent** (~200 LOC)
   - Search box (reactive, live filter)
   - Sector filter chips
   - Verdict tabs (BUY, ACCUMULATE, HOLD, REDUCE, SELL, PENDING with counts)
   - Stock list (flat view)
   - Collapse/expand (localStorage)
   - Mobile drawer

5. **PatternBadgesComponent** (~80 LOC)
   - Reusable badge list
   - Icons + colors per pattern

6. **EventBadgeComponent** (~60 LOC)
   - Expandable event indicator
   - Tooltip/popover

### CSS to Port
- `.stock-grid`, `.stock-card`
- `.sidebar`, `.sidebar-search`, `.sidebar-chips`, `.sidebar-item-*`
- `.verdict-tabs`
- `.sparkline`
- `.pattern-badge`, `.event-badge`
- All responsive breakpoints (1024px, 768px)

### Store Integration
Use `stocksStore` signals:
```typescript
stocksStore.filteredStocks  // computed filtered + sorted
stocksStore.verdictCounts   // computed verdict counts
stocksStore.sectors         // computed unique sectors
stocksStore.setSectorFilter(sector)
stocksStore.setSearchFilter(query)
stocksStore.setVerdictFilter(verdict)
```

### Live Data
- WebSocket broadcasts from backend
- `ws.on('quotes', (data) => stocksStore.setStocks(data))`
- `ws.on('analysis_done', (data) => refreshStocks())`
- Polling fallback every 20s

---

## 📖 Where to Start

### Step 1: Review Documentation
```bash
# Read detailed component checklist
cat PHASE_3_COMPONENTS.md | grep -A 100 "^### Level 2"

# Read API/WebSocket setup
cat frontend/README.md
```

### Step 2: Review Legacy Code
```bash
# See old HTML/CSS for Stock Grid
# Lines 1100-1400 in static/index.html (git history)
git show HEAD~100:static/index.html | head -1400 | tail -300

# Canvas sparkline drawing (port this)
# Lines 3900-4000 in static/index.html
```

### Step 3: Set Up Dev Environment
```bash
cd frontend
npm install
npm start
# http://localhost:4200 (should show placeholder)

# In separate terminal:
cd ..
python dashboard_server.py --port 8765
# Backend on localhost:8765
```

### Step 4: Start Porting
1. Create `StockGridComponent` (simple 4-column grid first)
2. Create `StockCardComponent` (just text first, no sparkline)
3. Add `SparklineComponent` (canvas chart)
4. Create `SidebarComponent` (filters)
5. Wire everything together
6. Test with `npm start` + `python dashboard_server.py`

### Step 5: Commit After Each Component
```bash
git add frontend/src/app/features/
git commit -m "Phase 3 Level 2: Port StockCardComponent"
```

---

## 🧪 Testing

### Unit Tests (Vitest)
- Grid ordering (by verdict bucket, symbol)
- Sidebar filtering (sector, verdict, search)
- Price formatting (fmtPrice, fmtChg)
- Verdict bucketing (verdictToBucket)

### E2E Tests (Playwright) — After All Components
```bash
# Side-by-side comparison with legacy UI
# Must match screenshot pixel-perfect
```

### Manual Testing
```bash
# While `ng serve` running:
# 1. Open http://localhost:4200
# 2. Check grid renders
# 3. Click card → select (prepare for Level 3 modal)
# 4. Search in sidebar → grid filters
# 5. Click verdict tab → grid filters
# 6. Watch price update (WebSocket)
# 7. Mobile view (F12, 375px width)
```

---

## 📝 Code Snippets to Use

### Stock Grid Loop
```typescript
<div class="stock-grid">
  @for (stock of stocksStore.filteredStocks(); track stock.symbol) {
    <app-stock-card [stock]="stock" (click)="selectStock(stock)"></app-stock-card>
  }
</div>
```

### Sidebar Verdict Filter
```typescript
@for (verdict of verdicts; let i = $index) {
  <button 
    [class.active]="stocksStore.filter().verdict === verdict"
    (click)="stocksStore.setVerdictFilter(verdict === stocksStore.filter().verdict ? null : verdict)">
    {{ verdict }} ({{ stocksStore.verdictCounts()[verdict] }})
  </button>
}
```

### Live Price Update
```typescript
constructor() {
  ws.on('quotes', (data) => {
    stocksStore.setStocks(data.quotes ? 
      Object.values(data.quotes) : []);
  });
}
```

---

## 📊 Progress Tracking

| Component | Status | Lines | Notes |
|-----------|--------|-------|-------|
| StockGridComponent | ⏳ TODO | ~150 | Simple grid loop first |
| StockCardComponent | ⏳ TODO | ~200 | Text + badges first |
| SparklineComponent | ⏳ TODO | ~100 | Port canvas logic |
| SidebarComponent | ⏳ TODO | ~200 | Search + filters |
| PatternBadgesComponent | ⏳ TODO | ~80 | Reusable list |
| EventBadgeComponent | ⏳ TODO | ~60 | Expandable badge |

**Total L2:** ~790 LOC expected

---

## 🚨 Common Pitfalls to Avoid

❌ Don't create new chart library — port existing canvas drawCandleChart  
❌ Don't use `*ngFor` — use new Angular `@for` syntax  
❌ Don't fetch data in component — use `stocksStore` signals  
❌ Don't forget `trackBy` in grid loops — causes performance issues  
❌ Don't hardcode colors — use CSS variables (--accent-green, etc.)  
❌ Don't forget responsive media queries (1024px, 768px)  
❌ Don't forget mobile drawer for sidebar  
❌ Don't skip TypeScript strict mode — `@property(required)` for inputs  

---

## ✅ Definition of Done (L2)

- [ ] StockGridComponent renders 4-column grid
- [ ] StockCardComponent shows all fields (price, verdict, patterns, events)
- [ ] SparklineComponent displays mini chart
- [ ] SidebarComponent with search + filters works
- [ ] Grid filters reactively on sidebar input
- [ ] Live price updates from WebSocket
- [ ] Polling fallback works (20s interval)
- [ ] Mobile responsive (test at 375px)
- [ ] All CSS migrated from legacy UI
- [ ] No visual regressions (screenshot matches)
- [ ] All 93 Python tests still passing
- [ ] Component committed with clear message

---

## 📚 Reference Files

**Documentation:**
- `INDEX.md` — Navigation hub
- `QUICK_START.md` — Setup
- `PHASE_3_COMPONENTS.md` — Full checklist (Level 2 section)
- `frontend/README.md` — Angular guide

**Code to Reference:**
- `frontend/src/app/core/stores/stocks.store.ts` — State management
- `frontend/src/app/core/services/ws.service.ts` — WebSocket
- `frontend/src/app/core/utils/price.ts` — Price utils
- `frontend/src/app/core/utils/verdict.ts` — Verdict utils
- `frontend/src/app/features/shell/header.component.ts` — Component pattern

**Legacy Code (for porting):**
- `static/index.html` lines 1100–1400 (grid + cards)
- `static/index.html` lines 1500–1800 (sidebar)
- `static/index.html` lines 3900–4000 (sparkline canvas)

---

## 🔗 Quick Links

- **Start here:** [`INDEX.md`](INDEX.md)
- **Level 2 checklist:** [`PHASE_3_COMPONENTS.md`](PHASE_3_COMPONENTS.md)
- **Angular guide:** [`frontend/README.md`](frontend/README.md)
- **Last commit:** `532fa59` (Session final status)
- **Test status:** 93/93 ✅

---

## 💡 Tips for Success

1. **Port incrementally** — Build grid → add cards → add sparkline → sidebar
2. **Test often** — `npm start` after each component
3. **Match legacy exactly** — CSS and layout must be identical
4. **Use trackBy** — Grid has 50+ cards, performance matters
5. **Mobile first** — Test 375px width early
6. **Screenshot comparison** — Playwright side-by-side after all L2
7. **Commit cleanly** — One component per commit, clear message
8. **Ask for help** — Reference this doc when stuck

---

## 🎯 Success Criteria

After Level 2 is done:
- ✅ App shows stock grid with live prices
- ✅ Sidebar filters work
- ✅ WebSocket updates visible
- ✅ Matches legacy UI (screenshot)
- ✅ All 93 tests passing
- ✅ Mobile responsive
- ✅ Ready for Level 3 (modals)

---

**You're all set! Start with INDEX.md and PHASE_3_COMPONENTS.md Level 2. Good luck! 🚀**
