/**
 * Verdict bucketing: unified place for verdict → bucket/class/color mapping.
 * Replaces ~8 copies in the legacy HTML.
 */

import { Stock } from '../models/stock.model';

export type VerdictBucket = 'buy' | 'accumulate' | 'hold' | 'reduce' | 'sell' | 'pending';

export interface VerdictInfo {
  bucket: VerdictBucket;
  label: string;
  icon: string;
  color: string;
  bgColor: string;
  confidence?: number;
}

/**
 * Map action_verdict to a display bucket.
 */
export function verdictToBucket(verdict: string | undefined): VerdictBucket {
  if (!verdict) return 'pending';
  const v = (verdict || '').toUpperCase().trim();
  switch (v) {
    case 'BUY':
      return 'buy';
    case 'ACCUMULATE':
      return 'accumulate';
    case 'HOLD':
      return 'hold';
    case 'REDUCE':
      return 'reduce';
    case 'SELL':
      return 'sell';
    default:
      return 'pending';
  }
}

/**
 * Get display info for a verdict bucket.
 */
export function verdictInfo(bucket: VerdictBucket, confidence?: number): VerdictInfo {
  const infoMap: { [key in VerdictBucket]: Omit<VerdictInfo, 'confidence'> } = {
    'buy': {
      bucket: 'buy',
      label: 'BUY',
      icon: '🚀',
      color: 'var(--accent-green)',
      bgColor: 'rgba(16, 185, 129, 0.15)'
    },
    'accumulate': {
      bucket: 'accumulate',
      label: 'ACCUMULATE',
      icon: '📈',
      color: 'var(--accent-green)',
      bgColor: 'rgba(16, 185, 129, 0.08)'
    },
    'hold': {
      bucket: 'hold',
      label: 'HOLD',
      icon: '⏸️',
      color: 'var(--accent-blue)',
      bgColor: 'rgba(56, 189, 248, 0.08)'
    },
    'reduce': {
      bucket: 'reduce',
      label: 'REDUCE',
      icon: '📉',
      color: 'var(--accent-red)',
      bgColor: 'rgba(239, 68, 68, 0.08)'
    },
    'sell': {
      bucket: 'sell',
      label: 'SELL',
      icon: '⛔',
      color: 'var(--accent-red)',
      bgColor: 'rgba(239, 68, 68, 0.15)'
    },
    'pending': {
      bucket: 'pending',
      label: 'PENDING',
      icon: '⏳',
      color: 'var(--text-muted)',
      bgColor: 'rgba(156, 163, 175, 0.08)'
    }
  };

  return { ...infoMap[bucket], confidence };
}

/**
 * Get the verdict bucket from a stock object.
 */
export function getStockBucket(stock: Stock): VerdictBucket {
  if (!stock.synth_output?.structured_signal) return 'pending';
  return verdictToBucket(stock.synth_output.structured_signal.action_verdict);
}

/**
 * Count stocks by verdict bucket.
 */
export function countByBucket(stocks: Stock[]): { [key in VerdictBucket]: number } {
  const counts: { [key in VerdictBucket]: number } = {
    buy: 0,
    accumulate: 0,
    hold: 0,
    reduce: 0,
    sell: 0,
    pending: 0
  };

  for (const stock of stocks) {
    const bucket = getStockBucket(stock);
    counts[bucket]++;
  }

  return counts;
}

/**
 * Filter stocks by verdict bucket.
 */
export function filterByBucket(stocks: Stock[], buckets: VerdictBucket[]): Stock[] {
  return stocks.filter(s => buckets.includes(getStockBucket(s)));
}
