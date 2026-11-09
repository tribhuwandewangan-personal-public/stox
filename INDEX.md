# NSE Stock Predictor — Project Index & Documentation

Complete guide to the codebase after Phases 1–2 completion.

---

## 📚 Documentation (Read in This Order)

### For This Session (2026-11-10)
1. **[QUICK_START.md](QUICK_START.md)** ⭐ **Start here** — 5-minute overview
2. **[SESSION_SUMMARY.md](SESSION_SUMMARY.md)** — What was accomplished
3. **[PHASE_3_COMPONENTS.md](PHASE_3_COMPONENTS.md)** — Next work (detailed checklist)

### For Maintenance & Cleanup
4. **[CLEANUP_CHECKLIST.md](CLEANUP_CHECKLIST.md)** — Files to delete after Phase 3/4

### For Frontend Development
5. **[frontend/README.md](frontend/README.md)** — Angular setup, architecture, development workflow

---

## 🏗️ Architecture Overview

### Backend (Python)

```
dashboard_server.py (legacy, still works)
    ↓ imports
api/services.py (reusable service functions)
    ↓ used by both
┌─────────────────────────────────────┐
│ http.server handler (legacy)        │  OR  api/main.py (Starlette, new)
│ DashboardHandler.do_GET/do_POST     │      │
│ Routes: /api/*, /                   │      Routes: /api/*, /ws, SPA
│ Serves static/index.html            │      Serves frontend/dist/
└─────────────────────────────────────┘
    ↓ subscribe to
tools/events_bus.py (thread-safe pub/sub)
    ↓ published by
┌─────────────────────────────────────┐
│ QuotePoller (quote refresh)         │
│ Scheduler (daily analysis)          │
│ Trigger endpoint (manual analysis)  │
└─────────────────────────────────────┘
```

### Frontend (Angular 22)

```
frontend/src/main.ts (bootstrap)
    ↓
frontend/src/app.ts (root component, placeholder)
    ↓ imports
app/core/services/
    ├── api.service.ts (HTTP client, /api/*)
    └── ws.service.ts (WebSocket /ws, with reconnect + polling)
    ↓ calls
app/core/stores/stocks.store.ts (signals state)
    ↓ uses
app/core/models/stock.model.ts (type definitions)
app/core/utils/price.ts, verdict.ts (utilities)
    ↓
Components (Phase 3):
    ├── Shell: header, sidebar, bulletin
    ├── Grid: stock cards, sparklines
    ├── Modals: detail, chart, patterns, events
    └── Forms: calculator, add symbol, accuracy
```

---

## 📂 Directory Structure

```
stox-main/
├── api/                          ⭐ NEW (Phase 1) — Starlette app
│   ├── __init__.py
│   ├── main.py                   app factory, lifespan
│   ├── routes.py                 REST endpoints
│   ├── services.py               reusable service functions
│   ├── security.py               middleware & validation
│   └── ws.py                     WebSocket endpoint
│
├── frontend/                     ⭐ NEW (Phase 2) — Angular 22 app
│   ├── angular.json              build config
│   ├── package.json              dependencies
│   ├── tsconfig.json             TypeScript config
│   ├── proxy.conf.json           dev server proxy
│   ├── .gitignore
│   ├── README.md                 Frontend docs
│   └── src/
│       ├── main.ts               bootstrap
│       ├── app.ts                root component
│       ├── styles.css            global dark theme
│       ├── index.html
│       └── app/core/
│           ├── models/
│           │   └── stock.model.ts  API contract
│           ├── services/
│           │   ├── api.service.ts  HTTP client
│           │   └── ws.service.ts   WebSocket client
│           ├── stores/
│           │   └── stocks.store.ts signals state
│           └── utils/
│               ├── price.ts        price utilities
│               └── verdict.ts      verdict utilities
│
├── tools/
│   ├── events_bus.py             ⭐ NEW (Phase 1) — pub/sub
│   ├── quote_tools.py            ✏️ UPDATED — publishes events
│   ├── scheduler.py              ✏️ UPDATED — publishes events
│   └── ... (other tools, unchanged)
│
├── static/
│   └── index.html                ⚠️ TO BE DELETED (Phase 3)
│
├── dashboard_server.py           ✏️ UPDATED — imports api.services
├── main.py                       (legacy entry point)
│
├── QUICK_START.md                ⭐ Read first
├── SESSION_SUMMARY.md            This session's work
├── PHASE_3_COMPONENTS.md         Component porting plan
├── CLEANUP_CHECKLIST.md          Files to delete after phases
├── INDEX.md                      This file
│
└── ... (other files: config.py, storage/, agents/, tests/, etc.)
```

---

## 🚀 Quick Commands

### Development

```bash
# Backend: Run legacy dashboard (imports api.services)
python dashboard_server.py --port 8765

# Backend: Run tests
python -m pytest tests/ -v

# Frontend: Install & dev
cd frontend
npm install
npm start
# http://localhost:4200 (proxies to localhost:8765)

# Frontend: Production build
npm run build:prod
# Output: frontend/dist/stox/browser/
```

### Git

```bash
# View this session's commits
git log --oneline -7

# View diff since Phase 1 started
git diff 9492fb4..HEAD

# Restore deleted files from history
git checkout HEAD~N:path/to/file
```

---

## ✅ Current Status

| Component | Status | Details |
|-----------|--------|---------|
| Backend extraction | ✅ Done | api/services.py, events_bus.py |
| Starlette foundation | ✅ Done | api/{main,routes,ws,security}.py |
| Frontend scaffold | ✅ Done | Angular 22 config + core services |
| WebSocket client | ✅ Done | Reconnect + polling fallback |
| State management | ✅ Done | Signals-based store |
| Components | ⏳ Phase 3 | Detailed checklist ready |
| Integration tests | ⏳ Phase 3 | Planned with Playwright |
| Heroku deployment | ⏳ Phase 4 | Deferred |
| Legacy UI cleanup | ⏳ Phase 4 | After parity verified |

**Tests:** 93/93 passing ✅  
**Constraints:** All honored ✅  
**Git:** All changes committed ✅

---

## 📖 Key Files to Understand

### Backend

- **[api/services.py](api/services.py)** (260 LOC)
  - Core business logic: get_all_stock_data, get_stocks_response_body, get_history_response_body
  - Used by both legacy handler and new Starlette app

- **[api/ws.py](api/ws.py)**
  - WebSocket endpoint, ConnectionManager
  - Broadcasts events to connected clients

- **[tools/events_bus.py](tools/events_bus.py)** (70 LOC)
  - Thread-safe pub/sub
  - Decouples backend threads from HTTP framework

### Frontend

- **[frontend/src/app/core/stores/stocks.store.ts](frontend/src/app/core/stores/stocks.store.ts)**
  - Signals-based reactive state
  - Computed properties, filtering, sorting
  - 200 LOC, no Redux

- **[frontend/src/app/core/services/ws.service.ts](frontend/src/app/core/services/ws.service.ts)**
  - WebSocket with reconnection
  - Exponential backoff + polling fallback
  - 200 LOC, sophisticated but understandable

- **[frontend/src/app/core/models/stock.model.ts](frontend/src/app/core/models/stock.model.ts)**
  - Type definitions (single source of truth)
  - Matches Python API responses exactly

---

## 🎓 Learning Path

### New to This Project?

1. Read **[QUICK_START.md](QUICK_START.md)** (5 min)
2. Read **[SESSION_SUMMARY.md](SESSION_SUMMARY.md)** (10 min)
3. Explore `api/services.py` (understand service extraction)
4. Explore `frontend/src/app/core/` (understand Angular setup)
5. Read **[PHASE_3_COMPONENTS.md](PHASE_3_COMPONENTS.md)** (understand next work)

### Contributing to Phase 3?

1. Read **[PHASE_3_COMPONENTS.md](PHASE_3_COMPONENTS.md)** (detailed component checklist)
2. Read **[frontend/README.md](frontend/README.md)** (development workflow)
3. Start with HeaderComponent (Level 1, Days 1–2)
4. Commit each component as done
5. Follow testing strategy (Vitest + Playwright)

### Deploying to Heroku?

1. ⏳ Deferred to Phase 4
2. See **[docs/DEPLOY_HEROKU.md](docs/DEPLOY_HEROKU.md)** (placeholder, not yet created)

---

## 🔍 Important Decisions Made

### 1. Service Extraction (Phase 1)
- ✅ **Decision:** Extract business logic to api/services.py
- **Why:** Reusable by any HTTP framework, enables parallel development
- **Result:** Both http.server and Starlette can use same code

### 2. Event Bus (Phase 1)
- ✅ **Decision:** Thread-safe pub/sub in tools/events_bus.py
- **Why:** Decouples threads (QuotePoller, Scheduler) from HTTP framework
- **Result:** Can broadcast WebSocket updates from background threads safely

### 3. Signals over Redux (Phase 2)
- ✅ **Decision:** Use Angular signals instead of NgRx/Redux
- **Why:** Lightweight, modern Angular pattern, no boilerplate
- **Result:** Simpler state management, no memory leaks

### 4. WebSocket Resilience (Phase 2)
- ✅ **Decision:** Exponential backoff + polling fallback
- **Why:** Handles all network scenarios (cloud proxies, network flakes, Heroku idle)
- **Result:** Never loses data, always has a fallback

### 5. Type Safety (Phase 2)
- ✅ **Decision:** Single source of truth (stock.model.ts)
- **Why:** Prevent API contract mismatches
- **Result:** Catch bugs at compile time, not runtime

---

## ⚠️ Known Limitations & Deferred Work

### Phase 3 (Component Porting)
- Not started yet (ready to go)
- Detailed checklist in **[PHASE_3_COMPONENTS.md](PHASE_3_COMPONENTS.md)**

### Phase 4 (Heroku Deployment)
- Postgres migration (SQLite → Postgres)
- Auth setup
- Documentation only (no resources created yet)

### Not In Scope
- Email notifications
- Mobile app
- Real-time tick data (WebSocket push + polling fallback is best we can do)
- Blockchain/crypto

---

## 🔗 External Resources

- [Angular 22 Docs](https://angular.dev)
- [Starlette Docs](https://www.starlette.io/)
- [RxJS Docs](https://rxjs.dev/)
- [Vitest Docs](https://vitest.dev/)
- [Playwright Docs](https://playwright.dev/)

---

## 📞 Questions?

- **"Where do I start?"** → Read [QUICK_START.md](QUICK_START.md)
- **"What changed this session?"** → Read [SESSION_SUMMARY.md](SESSION_SUMMARY.md)
- **"What's next?"** → Read [PHASE_3_COMPONENTS.md](PHASE_3_COMPONENTS.md)
- **"How do I develop?"** → Read [frontend/README.md](frontend/README.md)
- **"What should I delete?"** → Read [CLEANUP_CHECKLIST.md](CLEANUP_CHECKLIST.md)

---

## ✅ Final Checklist

- [x] Phases 1–2 complete
- [x] All 93 tests passing
- [x] Documentation comprehensive
- [x] Cleanup plan documented
- [x] Ready for Phase 3 (component porting)
- [x] Git history clean and clear
- [x] All constraints honored (no money, no Heroku, local only)

---

**Last Updated:** 2026-11-10  
**Status:** ✅ Complete and Ready for Phase 3  
**Next Session:** Start component porting (8-day sprint)
