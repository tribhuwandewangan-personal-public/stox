# Quick Start Guide

## Overview

This project has been refactored to separate backend services from the HTTP framework and is being ported to Angular 22.

- **Phase 1:** Backend service extraction ✅ Complete
- **Phase 2:** Angular scaffold + core services ✅ Complete
- **Phase 3:** Component porting (next)
- **Phase 4:** Heroku deployment (later)

## Current Status

✅ **Backend:** Legacy `dashboard_server.py` still works, imports services from `api/services.py`  
✅ **Tests:** 93/93 passing  
✅ **Frontend:** TypeScript scaffold ready, services built  
⏳ **Components:** Ready to start porting (detailed checklist in PHASE_3_COMPONENTS.md)

## File Structure Overview

```
stox-main/
├── api/                           # NEW: Starlette app (Phase 1)
│   ├── __init__.py
│   ├── main.py                   # App factory, lifespan
│   ├── routes.py                 # REST endpoints
│   ├── services.py               # Reusable service functions
│   ├── security.py               # Middleware & validation
│   └── ws.py                     # WebSocket endpoint
├── frontend/                      # NEW: Angular 22 app (Phase 2)
│   ├── angular.json
│   ├── package.json
│   ├── tsconfig.json
│   ├── proxy.conf.json
│   ├── src/
│   │   ├── main.ts               # Bootstrap
│   │   ├── app.ts                # Root component (placeholder)
│   │   ├── styles.css            # Dark theme
│   │   ├── index.html
│   │   └── app/core/
│   │       ├── models/stock.model.ts
│   │       ├── services/api.service.ts, ws.service.ts
│   │       ├── stores/stocks.store.ts
│   │       └── utils/price.ts, verdict.ts
│   └── README.md
├── tools/
│   ├── events_bus.py             # NEW: Thread-safe pub/sub
│   ├── quote_tools.py            # UPDATED: publishes QUOTES events
│   ├── scheduler.py              # UPDATED: publishes ANALYSIS_DONE events
│   └── ... (other tools)
├── dashboard_server.py           # UPDATED: imports api.services
├── PHASE_3_COMPONENTS.md         # Component porting checklist
├── SESSION_SUMMARY.md            # This session's work
└── ... (other files)
```

## Key Commands

### Development

```bash
# Backend: Run legacy dashboard (uses api/services imports)
python dashboard_server.py --port 8765

# Backend: Run tests
python -m pytest tests/ -v

# Frontend: Install dependencies
cd frontend && npm install

# Frontend: Development server (proxy to localhost:8765)
npm start
# http://localhost:4200

# Frontend: Build for production
npm run build:prod
# Output: frontend/dist/stox/browser/
```

### Git

```bash
# View commit history (this session)
git log --oneline | head -10

# View changes since Phase 1
git diff 9492fb4..main

# See what files were added
git show --name-status b1c71b4
```

## Architecture

### Backend Flow

```
dashboard_server.py (legacy http.server)
    ↓
api/services.py (reusable functions)
    ↓
QuotePoller → events_bus.publish(QUOTES)
Scheduler → events_bus.publish(ANALYSIS_DONE)
    ↓
api/main.py (Starlette app) ← subscribes to events_bus
    ↓
/ws endpoint ← broadcasts to WebSocket clients
```

### Frontend Flow

```
app.ts (root component)
    ↓
api.service.ts (HTTP client) + ws.service.ts (WebSocket)
    ↓
stocks.store.ts (signals state) ← computed properties
    ↓
Components (shell, grid, modal - Phase 3)
    ↓
price.ts, verdict.ts (pure utils)
```

## Key Features

### Phase 1: Backend Extraction
- Services are framework-agnostic (work with http.server or Starlette)
- Event bus for pub/sub (threads can safely broadcast to async clients)
- Thread-safe event loop integration (asyncio.run_coroutine_threadsafe)

### Phase 2: Angular Frontend
- Signals-based state (modern Angular, lightweight)
- WebSocket with exponential backoff + polling fallback
- Type-safe API contract (stock.model.ts)
- Unified utility functions (no duplication)

### Phase 3: Component Porting (Next)
- 5 levels: Shell → Grid → Modals → Forms
- Detailed checklist in PHASE_3_COMPONENTS.md
- CSS migration strategy included
- E2E testing with Playwright (screenshot comparison)

## Testing

```bash
# All Python tests
python -m pytest tests/ -v

# Just the stock analysis tests
python -m pytest tests/test_deterministic_engine.py -v

# Just the live data tests
python -m pytest tests/test_live_data.py -v

# With coverage
python -m pytest tests/ --cov=.
```

**Expected:** 93/93 passing

## Common Questions

### Q: Is the legacy dashboard still working?
**A:** Yes! `dashboard_server.py` imports services from `api/services.py`. Zero downtime during migration.

### Q: Can I run both the old and new apps?
**A:** Yes, but on different ports:
- Old: `python dashboard_server.py --port 8765`
- New: `npm start` (Angular on :4200, proxies to :8765)

### Q: Where are the Angular components?
**A:** Phase 3 (next milestone). All foundation is ready in `frontend/src/app/core/`.

### Q: How do I port a component?
**A:** Read PHASE_3_COMPONENTS.md for step-by-step instructions per component level.

### Q: Will the new UI look different?
**A:** No. All CSS is preserved exactly (from `static/index.html`). Phase 3 will ensure pixel-perfect parity.

### Q: When does the app go to Heroku?
**A:** Phase 4. No money spent yet, no resources provisioned. See `docs/DEPLOY_HEROKU.md` (placeholder).

## Constraints (Still Honored)

✅ No money spent  
✅ No Heroku resources created  
✅ Local development only  
✅ Never touched real storage/cache.db  
✅ All original functionality preserved

## Documentation

- **SESSION_SUMMARY.md** — High-level overview of this session
- **PHASE_3_COMPONENTS.md** — Detailed component porting checklist
- **frontend/README.md** — Architecture, development workflow
- **QUICK_START.md** — This file

## Next Steps

1. Read PHASE_3_COMPONENTS.md (component checklist)
2. Start Phase 3: Begin porting HeaderComponent
3. Each component = 1 commit (tight feedback loop)
4. After all components: integration test + screenshot comparison
5. Once verified: retire static/index.html

## Getting Help

- Check SESSION_SUMMARY.md for context
- Read code comments in api/services.py, ws.service.ts, stocks.store.ts
- Reference PHASE_3_COMPONENTS.md for detailed component tasks
- All 93 tests are passing and provide documentation by example

## Summary

✅ **Phase 1 done:** Backend extraction, event bus, Starlette foundation  
✅ **Phase 2 done:** Angular scaffold, core services, utilities, state store  
✅ **Tests:** All 93 passing, no regressions  
✅ **Ready:** Phase 3 component porting  

The foundation is solid. Next session focuses purely on UI components.
