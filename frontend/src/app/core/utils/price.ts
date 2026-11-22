/**
 * Price formatting and calculation utilities.
 */

import { Stock, PriceInfo } from '../models/stock.model';

export interface BestPrice {
  price: number | null;
  change_pct: number | null;
  source: string;
}

/**
 * Get the best available price for a stock (quote > close > analysis).
 */
export function bestPrice(stock: Stock): BestPrice {
  const info = stock.price_info;
  return {
    price: info.price,
    change_pct: info.change_pct,
    source: info.kind || info.source || 'unknown'
  };
}

/**
 * Format a price as Indian currency (Rs. X,XXX.XX).
 */
export function fmtPrice(price: number | null): string {
  if (price === null || price === undefined) return 'N/A';
  return 'Rs. ' + Number(price).toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
}

/**
 * Format percentage change (±X.XX%).
 */
export function fmtChg(pct: number | null): string {
  if (pct === null || pct === undefined || !isFinite(pct)) return '–';
  const sign = pct > 0 ? '+' : '';
  const color = pct > 0 ? 'color:var(--accent-green)' : pct < 0 ? 'color:var(--accent-red)' : '';
  const value = pct.toFixed(2);
  return `<span style="${color}">${sign}${value}%</span>`;
}

/**
 * Get a human-readable label for the quote source.
 */
export function priceTag(info: PriceInfo): string {
  const sourceMap: { [key: string]: string } = {
    'quote': 'Live',
    'close': 'Close',
    'analysis': 'Analysis',
    'unknown': 'Stale'
  };
  const key = info.kind || info.source || 'unknown';
  return sourceMap[key] || 'Unknown';
}

/**
 * Calculate percentage from buy price.
 */
export function calcPct(price: number, buyPrice: number): number {
  if (buyPrice <= 0) return NaN;
  return ((price - buyPrice) / buyPrice) * 100;
}

/**
 * Calculate price from percentage and buy price.
 */
export function calcPrice(pct: number, buyPrice: number): number {
  if (buyPrice <= 0) return NaN;
  return buyPrice * (1 + pct / 100);
}

/**
 * Calculate risk:reward ratio (long or short setup).
 */
export function calcRiskReward(
  targetPct: number | null,
  stopPct: number | null
): number | null {
  if (targetPct === null || stopPct === null) return null;
  if (targetPct === 0 || stopPct === 0) return null;

  // Both must be on opposite sides (target profit, stop loss)
  // e.g., long: target +10%, stop -5% => ratio 10/5 = 2.0
  // or short: target -10%, stop +5% => ratio 10/5 = 2.0
  const same_side = (targetPct > 0) === (stopPct > 0);
  if (same_side) return null;

  return Math.abs(targetPct / stopPct);
}

/**
 * Format a signed number (e.g., +10.00, -5.00, 0.00).
 */
export function fmtSigned(value: number, digits: number = 2): string {
  if (!isFinite(value)) return '–';
  const sign = value > 0 ? '+' : value < 0 ? '-' : '';
  return sign + Math.abs(value).toFixed(digits);
}
