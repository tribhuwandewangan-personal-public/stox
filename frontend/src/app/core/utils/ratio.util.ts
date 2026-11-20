// src/app/core/utils/ratio.util.ts
/**
 * Utility functions for common financial ratios.
 * All inputs are numbers; callers must ensure they are not null/undefined.
 * Functions return `null` when a denominator is zero or missing.
 */

export function percent(value?: number): number | null {
  return value != null ? Number((value * 100).toFixed(2)) : null;
}

export function roe(netIncome: number, equity: number): number | null {
  return equity !== 0 ? percent(netIncome / equity) : null;
}

export function roce(ebit: number, capitalEmployed: number): number | null {
  return capitalEmployed !== 0 ? percent(ebit / capitalEmployed) : null;
}

export function roic(nopat: number, investedCapital: number): number | null {
  return investedCapital !== 0 ? percent(nopat / investedCapital) : null;
}

export function currentRatio(currentAssets: number, currentLiabilities: number): number | null {
  return currentLiabilities !== 0 ? Number((currentAssets / currentLiabilities).toFixed(2)) : null;
}

export function quickRatio(
  cashAndEquivalents: number,
  receivables: number,
  currentLiabilities: number
): number | null {
  const numerator = cashAndEquivalents + receivables;
  return currentLiabilities !== 0 ? Number((numerator / currentLiabilities).toFixed(2)) : null;
}

export function debtToEquity(totalDebt: number, equity: number): number | null {
  return equity !== 0 ? Number((totalDebt / equity).toFixed(2)) : null;
}

export function interestCoverage(ebit: number, interestPaid: number): number | null {
  return interestPaid !== 0 ? Number((ebit / interestPaid).toFixed(2)) : null;
}

export function assetTurnover(revenue: number, totalAssets: number): number | null {
  return totalAssets !== 0 ? Number((revenue / totalAssets).toFixed(2)) : null;
}

export function cfoPat(cfo: number, pat: number): number | null {
  return pat !== 0 ? percent(cfo / pat) : null;
}

export function fcfPat(fcf: number, pat: number): number | null {
  return pat !== 0 ? percent(fcf / pat) : null;
}
