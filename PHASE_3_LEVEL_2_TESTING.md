# Phase 3 Level 2: Testing & Validation Guide

**Commit:** d8b7806 (CSS vars) + d5cb8ee (Components)  
**Status:** Components written, ready for testing  
**Date:** 2026-11-10

---

## 🚀 Quick Start

### 1. Start the Frontend Dev Server

```bash
cd frontend
npm install --legacy-peer-deps  # Already done
npm start
# Server starts on http://localhost:4200
```

### 2. Start the Backend (in another terminal)

```bash
python dashboard_server.py --port 8765
# WebSocket on ws://localhost:8765
```

### 3. Open Browser

```
http://localhost:4200
```

You should see:
- Header with market badge ✅
- Bulletin banner ✅
- **Sidebar on left** (NEW: search, filters)
- **Stock grid on right** (NEW: 4-column grid with cards)

---

## ✅ Manual Testing Checklist

### Grid & Cards

- [ ] Grid displays 50+ stocks
- [ ] Cards show: symbol, name, sector, price, change %, verdict badge
- [ ] Cards show 2 pattern badges (if any)
- [ ] Cards show event badge (if events exist)
- [ ] Sparkline chart visible in each card (40px height)
- [ ] Cards are in 4-column layout on desktop
- [ ] No console errors

**Test:** Open DevTools → Console, check for TypeScript/runtime errors

### Sidebar Search

- [ ] Search box appears at top of sidebar
- [ ] Type "INFY" → grid filters to only INFY
- [ ] Type "info" → filters by company name
- [ ] Clear search → all stocks return
- [ ] Search is case-insensitive

**Test:** Sidebar → Search box → type "INFY"

### Sidebar Sector Filter

- [ ] Sector chips appear ("Technology", "Finance", etc.)
- [ ] Click a sector → grid filters to only that sector
- [ ] Click same sector again → filter clears
- [ ] Multiple sectors can't be selected (radio, not checkbox)

**Test:** Sidebar → Click "Technology" → verify grid shows only tech stocks

### Sidebar Verdict Tabs

- [ ] All 6 verdict tabs visible (BUY, ACCUMULATE, HOLD, REDUCE, SELL, PENDING)
- [ ] Each tab shows count (e.g., "BUY (24)")
- [ ] Click "BUY" → grid filters to BUY verdict stocks only
- [ ] Click same verdict again → filter clears
- [ ] Verdict + Sector filters work together

**Test:** Sidebar → Click "BUY" → verify grid shows only BUY stocks

### Sidebar Stock List

- [ ] First 10 filtered stocks displayed in list
- [ ] Each shows symbol + price
- [ ] If >10 stocks, shows "+N more"

**Test:** Sidebar → check stock list at bottom

### Grid Click Interaction

- [ ] Click a stock card → card gets visual feedback (highlight, shadow)
- [ ] Stock is selected in store (sets `selectedSymbol`)
- [ ] (Level 3 modal will open here, but that's not done yet)

**Test:** Click any card → check store state (dev tools)

### Live Price Updates

- [ ] Backend broadcasts new prices via WebSocket
- [ ] Grid prices update in real-time (no page refresh)
- [ ] Change % color: green if +, red if -, gray if 0

**Test:** 
1. Run: `python -c "from storage import cache_manager; print(cache_manager.get_latest_quote('INFY'))"`
2. Manually update backend price
3. Watch grid update

### Responsive Layout

Test at these breakpoints:

#### Desktop (1280px)
- [ ] 4-column grid
- [ ] Sidebar on left (240px wide)
- [ ] Both visible side-by-side

#### Tablet (768px)
- [ ] 2-column grid
- [ ] Sidebar still left (narrower)
- [ ] Layout flexible

#### Mobile (375px)
- [ ] 1-column grid
- [ ] Sidebar above or as drawer
- [ ] Touch-friendly spacing

**Test:** DevTools → F12 → Responsive mode → test at 375px width

---

## 🧪 Automated Tests

### Unit Tests (Vitest)

```bash
npm test
```

Tests to verify:
- `verdictToBucket()` maps actions correctly
- `bestPrice()` returns best available price
- `fmtPrice()` formats Indian currency
- `fmtChg()` formats percentage change
- Grid `trackBy` uses symbol
- Sidebar filters update store correctly

**Create tests in:**
- `frontend/src/app/core/utils/verdict.spec.ts`
- `frontend/src/app/core/utils/price.spec.ts`
- `frontend/src/app/features/dashboard/stock-grid.spec.ts`

### E2E Tests (Playwright) — After Unit Tests Pass

```bash
npm run e2e
```

Test scenarios:
1. Search → grid updates
2. Verdict filter → grid updates
3. Sector filter → grid updates
4. WebSocket update → prices change
5. Click card → selection state updates

**Create tests in:**
- `frontend/e2e/dashboard.spec.ts`

---

## 🐛 Debugging

### Check Store State

In browser console:
```javascript
import { stocksStore } from './app/core/stores/stocks.store';
stocksStore.filter()  // Current filters
stocksStore.filteredStocks()  // Filtered list
stocksStore.verdictCounts()  // Counts per verdict
```

### Check WebSocket

In browser console:
```javascript
import { wsService } from './app/core/services/ws.service';
wsService.connected()  // true/false
wsService.on('quotes', (data) => console.log('Quotes:', data))
```

### Check Network Requests

DevTools → Network tab:
- Look for WebSocket connection: `ws://localhost:8765`
- Should show `quotes` messages

### Performance Check

DevTools → Performance tab:
1. Start recording
2. Scroll grid
3. Stop recording
4. Check FPS (should be 60, no drops)

---

## 🚨 Common Issues & Fixes

### Issue: Grid not rendering

**Check:**
1. DevTools → Console for errors
2. Check if `stocksStore.stocks()` is populated
3. Check if components imported in DashboardComponent

**Fix:**
```bash
npm run build  # Full rebuild
npm start       # Restart dev server
```

---

### Issue: Search/filters not working

**Check:**
1. `stocksStore.filter()` shows the filters being set
2. `stocksStore.filteredStocks()` returns correct count
3. Check sidebar bindings with `[(ngModel)]`

**Fix:**
- Ensure `FormsModule` imported in SidebarComponent
- Verify `stocksStore` is injected correctly

---

### Issue: Sparklines not visible

**Check:**
1. Check data: `stock.sparkline.length` > 0
2. Canvas rendered but blank: check ResizeObserver

**Fix:**
- Verify `SparklineComponent` imported in `StockCardComponent`
- Check canvas rendering logic in `draw()` method

---

### Issue: Sidebar collapsed on desktop

**Check:**
1. CSS media query breaking incorrectly
2. Flex direction set wrong

**Fix:**
Review `.sidebar` styles in `sidebar.component.ts`

---

## 📊 Performance Targets

| Metric | Target | Check |
|--------|--------|-------|
| Initial load | < 3s | DevTools Network |
| Grid render (50 cards) | < 500ms | DevTools Performance |
| Search response | < 100ms | Type → observe lag |
| Scroll (60 FPS) | No drops | DevTools Performance |
| Memory (50 cards) | < 20MB | DevTools Memory |

---

## 🎨 Visual Checklist

- [ ] Colors match theme (blue accents, green BUY, red SELL)
- [ ] Fonts consistent (Inter for body, Outfit for headings)
- [ ] Spacing consistent (16px gaps, 12px padding)
- [ ] Borders 1px with correct opacity
- [ ] Hover effects smooth (0.2s transitions)
- [ ] No flickering on updates

---

## 📱 Accessibility

- [ ] All buttons keyboard-accessible (Tab key)
- [ ] Search box has placeholder
- [ ] Colors have sufficient contrast (> 4.5:1)
- [ ] Verdict badges have text, not just color
- [ ] Event badge has emoji + text

---

## ✅ Sign-Off Criteria for Level 2 Complete

1. ✅ All manual tests pass (grid, search, filters, responsive)
2. ✅ Unit tests written and passing (> 80% coverage)
3. ✅ E2E tests pass (search, filter, select flows)
4. ✅ Performance targets met (grid renders in < 500ms)
5. ✅ No console errors or warnings
6. ✅ Mobile responsive (tested at 375px)
7. ✅ WebSocket integration working (prices update live)
8. ✅ All 93 Python tests still passing
9. ✅ Code reviewed for accessibility
10. ✅ Ready for Level 3 (modals)

---

## 🔗 Next Steps (Level 3)

When Level 2 is complete, Level 3 will add:
- Stock detail modal (opened on card click)
- Candlestick chart (full history)
- Pattern analysis panel
- Events panel
- Long-term analysis panel
- Re-analyze button

---

**Questions?** Check `NEXT_SESSION_HANDOFF.md` or reference files in `frontend/README.md`.
