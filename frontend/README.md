# NSE Stock Predictor — Angular 22 Frontend

Modern, reactive UI for the NSE stock analysis system. Built with Angular 22, signals-based state management, and WebSocket real-time updates with polling fallback.

## Architecture

### Core Layers

1. **Models** (`src/app/core/models/`)
   - TypeScript interfaces matching the Python backend API contract
   - Single source of truth for types (no duplication)

2. **Services** (`src/app/core/services/`)
   - **api.service.ts** — HTTP client with CSRF headers
   - **ws.service.ts** — WebSocket with reconnection + polling fallback

3. **State** (`src/app/core/stores/`)
   - **stocks.store.ts** — Angular signals-based reactive store
   - Computed properties, filtering, sorting
   - No Redux/NgRx boilerplate

4. **Utils** (`src/app/core/utils/`)
   - Pure functions for price formatting, verdict bucketing, calculations
   - Framework-agnostic, testable
   - Unified logic (no duplicates)

### Development Workflow

```bash
# Install dependencies (Angular 22, RxJS, CDK, etc.)
npm install

# Start dev server (proxy to :8765)
npm start
# Browse to http://localhost:4200

# Build for production
npm run build:prod
# Output: dist/stox/browser/

# Run tests
npm test
```

### Development Server Proxy

The `proxy.conf.json` forwards requests:
- `/api/*` → `http://localhost:8765/api/`
- `/ws` → `http://localhost:8765/ws` (WebSocket)
- `/news_reports/*` → `http://localhost:8765/news_reports/`
- `/reports/*` → `http://localhost:8765/reports/`

This allows the Angular dev server (port 4200) to talk to the Python backend (port 8765) without CORS issues.

### Production Build

The app builds to `dist/stox/browser/`. The Python backend (Starlette) will serve this as a static SPA with deep-link fallback.

Configuration in `api/main.py`:
```python
app.mount("/", StaticFiles(directory="frontend/dist/stox/browser", html=True), name="spa")
```

This ensures:
- `/` serves `index.html`
- `/stock/SYMBOL` fallback to `index.html` (Angular routing takes over)
- Long-lived cache for hashed assets
- No-cache for `index.html`

## Phases

### Phase 2 (Current) ✅
- [x] Models and type definitions
- [x] API and WebSocket services
- [x] Signals-based state store
- [x] Utility functions (unified price, verdict logic)
- [x] Angular configuration and bootstrap

### Phase 3 (Next)
- [ ] Shell components (header, sidebar, bulletin)
- [ ] Stock grid + cards with live prices
- [ ] Detail modal with candle chart
- [ ] Target/SL calculator (CDK drag)
- [ ] Add/remove symbol, accuracy, workflow modals
- [ ] End-to-end integration tests

### Phase 4 (Later)
- [ ] Starlette static file serving
- [ ] Production build optimization
- [ ] Heroku deployment
- [ ] Legacy `static/index.html` retirement (after sign-off)

## Styling

Global dark theme in `src/styles.css`:
- CSS custom properties for colors (--accent-blue, --accent-green, etc.)
- Matches legacy UI exactly (no visual diff for user)
- Responsive grid layouts, smooth transitions

Components will use scoped CSS (encapsulated, no naming conflicts).

## Testing

### Unit Tests (Vitest)
- Utility functions: price calcs, verdict bucketing
- Store actions and computed properties
- Service methods (mocked HTTP/WS)

### E2E Tests (Playwright)
- Side-by-side comparison with legacy UI
- Screenshot diffs for regressions
- Real stock data flow

Run tests:
```bash
npm test
```

## Key Technologies

- **Angular 22.2.6** — Latest major version, standalone components, signals
- **TypeScript 6.0** — Strict mode, ES2022 target
- **Vitest** — Fast, ESM-first test runner (no Karma)
- **RxJS** — Reactive utilities (minimal use, signals preferred)
- **CDK** — Drag-drop, text selection, portal for modals
- **Fontsource** — Self-hosted fonts (Inter, Outfit, JetBrains Mono)

No Redux, no Material Design (custom dark theme), no other heavy frameworks.

## Common Tasks

### Add a new stock detail component
```bash
ng generate component features/stock-detail
```

Then import it in the routing module and wire it to the store.

### Add a new API endpoint
1. Update `src/app/core/models/stock.model.ts` with the response type
2. Add the method to `ApiService` in `src/app/core/services/api.service.ts`
3. Call it from a component and store the result in `stocksStore`

### Debug WebSocket
Open browser DevTools Console:
```javascript
// Check connection status
ws.getState()

// Subscribe to a message type
ws.on('quotes', (data) => console.log('Quotes:', data))

// Send a ping
ws.send({type: 'ping'})
```

## Security Notes

- CSRF headers (`X-Stox-Request: 1`) added automatically by ApiService
- WebSocket Origin checks enforced by the backend
- All user input escaped by Angular bindings (no `innerHTML`)
- Loopback-only binding on localhost (no off-network access until auth is added)

## Deployment Checklist (Phase 4)

- [ ] Remove legacy `static/index.html` from git (after sign-off)
- [ ] Update `api/main.py` to serve the Angular build
- [ ] Optimize production build (tree-shaking, minification)
- [ ] Test with production build locally
- [ ] Set `TZ=Asia/Kolkata` in Heroku Procfile
- [ ] Update README with Heroku instructions

## Resources

- [Angular 22 Docs](https://angular.dev)
- [Angular Signals Guide](https://angular.dev/guide/signals)
- [CDK Documentation](https://material.angular.io/cdk)
- [Vitest Documentation](https://vitest.dev)
