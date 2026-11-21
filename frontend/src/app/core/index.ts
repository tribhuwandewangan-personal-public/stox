/**
 * Barrel re-export for the entire core module.
 * Import from '@app/core' instead of individual deep paths.
 *
 * NOTE: earnings.model.ts also defines ExceptionalItem (a subset of company.model.ts).
 * We export only EarningsQualityResult from earnings.model to avoid a name collision.
 */

// Models
export * from './models/stock.model';
export * from './models/status.model';
export * from './models/company.model';
export { EarningsQualityResult } from './models/earnings.model';
export * from './models/financial.model';

// Services
export * from './services/api.service';
export * from './services/company.service';
export * from './services/earnings.service';
export * from './services/financial.service';
export * from './services/ws.service';

// Stores
export * from './stores/app.store';
export * from './stores/stocks.store';
export * from './stores/company.store';
export * from './stores/earnings.store';
