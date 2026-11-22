/**
 * HTTP API client service.
 * Thin wrapper around fetch that adds CSRF headers and error handling.
 */

import { Injectable } from '@angular/core';
import {
  Stock,
  AccuracyReport,
  ChartData,
  QuotesResponse,
  SearchResult,
  QueueStatus,
  PatternPicksResponse,
  MacroRiskShieldResponse,
  MarketScannerResponse,
  PortfolioResponse,
  FinancialStatementRow
} from '../models/stock.model';

const API_BASE = '/api';
const CSRF_HEADER = 'X-Stox-Request';
const CSRF_VALUE = '1';

/**
 * Add CSRF headers to request options.
 */
function withCsrfHeaders(options: RequestInit = {}): RequestInit {
  const headers = new Headers(options.headers || {});
  headers.set(CSRF_HEADER, CSRF_VALUE);
  headers.set('Content-Type', 'application/json');
  return { ...options, headers };
}

/**
 * Generic fetch wrapper with error handling.
 */
async function fetchJson<T>(path: string, options?: RequestInit): Promise<T> {
  try {
    const response = await fetch(`${API_BASE}${path}`, options);
    if (!response.ok) {
      let detail = response.statusText;
      try {
        const body = await response.json();
        detail = body?.message || body?.error || detail;
      } catch {
        // Ignore parse failures on error responses
      }
      throw new Error(`HTTP ${response.status}: ${detail}`);
    }
    return await response.json();
  } catch (error) {
    console.error(`[API] Error fetching ${path}:`, error);
    throw error;
  }
}

@Injectable({
  providedIn: 'root' // <-- This makes it available globally
})
export class ApiService {
  /**
   * GET /api/ticker: Live ticker data.
   */
  static getTickerData(): Promise<any> {
    return fetchJson<any>('/ticker');
  }

  /**
   * GET /api/bulletin: Market bulletin text.
   */
  static getBulletin(): Promise<string> {
    return fetchJson<string>('/bulletin');
  }
  /**
   * GET /api/status: Server status, queue, macro.
   */
  getStatus(): Promise<any> {
    return fetchJson('/status');
  }

  /**
   * GET /api/stocks: All stocks with analysis and quotes. Supports ?universe=curated|midcap250|all_nse
   */
  static getStocks(universe: string = 'curated'): Promise<Stock[]> {
    const params = universe && universe !== 'curated' ? `?universe=${encodeURIComponent(universe)}` : '';
    const resp = fetchJson<any>(`/stocks${params}`);
    return resp.then((r: any) => r || []);
  }

  /**
   * GET /api/quotes: Current live quotes.
   */
  static getQuotes(): Promise<QuotesResponse> {
    return fetchJson<QuotesResponse>('/quotes');
  }

  /**
   * GET /api/accuracy: Prediction accuracy report.
   */
  static getAccuracy(): Promise<AccuracyReport> {
    return fetchJson<AccuracyReport>('/accuracy');
  }

  /**
   * GET /api/forensic-recommendation?symbol=XXX: Forensic analysis and due-diligence recommendation.
   */
  static getForensicRecommendation(symbol: string, price?: number): Promise<any> {
    const params = new URLSearchParams({ symbol });
    if (price) params.append('price', String(price));
    return fetchJson<any>(`/forensic-recommendation?${params}`);
  }

  /**
   * GET /api/history?symbol=XXX&days=90: Chart data for a stock.
   */
  static getHistory(symbol: string, days: number = 90): Promise<ChartData> {
    const params = new URLSearchParams({ symbol, days: String(days) });
    return fetchJson<ChartData>(`/history?${params}`);
  }

  /**
   * GET /api/chart?symbol=XXX: Get candlestick data for modal.
   */
  static getChartData(symbol: string): Promise<ChartData> {
    return this.getHistory(symbol, 100);
  }

  /**
   * GET /api/events?symbol=XXX: Events for a stock or macro catalysts.
   */
  static getEvents(symbol?: string): Promise<any> {
    if (symbol) {
      return fetchJson(`/events?symbol=${encodeURIComponent(symbol)}`);
    }
    return fetchJson('/events');
  }

  /**
   * GET /api/search-symbol?q=ABC: Search for symbols.
   */
  static searchSymbol(query: string): Promise<SearchResult[]> {
    const params = new URLSearchParams({ q: query });
    return fetchJson<any>(`/search-symbol?${params}`).then((resp: any) => resp.results || []);
  }

  /**
   * POST /api/trigger: Manually trigger analysis of a stock.
   */
  static triggerAnalysis(symbol: string): Promise<any> {
    return fetchJson('/trigger', withCsrfHeaders({
      method: 'POST',
      body: JSON.stringify({ symbol })
    }));
  }

  /**
   * POST /api/add-symbol: Add a symbol to the watchlist.
   */
  static addSymbol(symbol: string, name: string, sector: string, exchange: string = 'NSE'): Promise<any> {
    return fetchJson('/add-symbol', withCsrfHeaders({
      method: 'POST',
      body: JSON.stringify({ symbol, name, sector, exchange })
    }));
  }

  /**
   * POST /api/remove-symbol: Remove a symbol from the watchlist.
   */
  static removeSymbol(symbol: string): Promise<any> {
    return fetchJson('/remove-symbol', withCsrfHeaders({
      method: 'POST',
      body: JSON.stringify({ symbol })
    }));
  }

  /**
   * POST /api/re-analyze: Trigger re-analysis of a specific stock.
   */
  static reAnalyzeStock(symbol: string): Promise<any> {
    return this.triggerAnalysis(symbol);
  }

  /**
   * GET /api/patterns/top: Pattern screener — top stocks by chart pattern signals.
   * Queries all analyzed stocks (not just watchlist).
   */
  static getPatternPicks(minUpside: number = 0): Promise<PatternPicksResponse> {
    const params = minUpside > 0 ? `?min_upside=${minUpside}` : '';
    return fetchJson<PatternPicksResponse>(`/patterns/top${params}`);
  }

  /**
   * GET /api/fundamental-picks: Top 10 fundamental compounders scored on 8 dimensions.
   */
  static getFundamentalPicks(universe: string = 'curated'): Promise<any> {
    const params = universe && universe !== 'curated' ? `?universe=${encodeURIComponent(universe)}` : '';
    return fetchJson<any>(`/fundamental-picks${params}`);
  }

  /**
   * GET /api/macro-risk-shield: Macro risk tier, playbook, defensive sectors, and per-holding shields.
   */
  static getMacroRiskShield(): Promise<MacroRiskShieldResponse> {
    return fetchJson<MacroRiskShieldResponse>('/macro-risk-shield');
  }

  /**
   * GET /api/market-scanner: Latest outside-watchlist momentum & strength leaders.
   */
  static getMarketScanner(): Promise<MarketScannerResponse> {
    return fetchJson<MarketScannerResponse>('/market-scanner');
  }

  /**
   * POST /api/market-scanner/scan: Triggers a fresh background market scan.
   */
  static triggerMarketScan(): Promise<{ status: string; message?: string }> {
    return fetchJson<{ status: string; message?: string }>('/market-scanner/scan', withCsrfHeaders({
      method: 'POST',
      body: JSON.stringify({})
    }));
  }

  /**
   * GET /api/portfolio: Read-only portfolio diagnostics and holdings breakdown.
   */
  static getPortfolio(): Promise<PortfolioResponse> {
    return fetchJson<PortfolioResponse>('/portfolio');
  }

  /**
   * GET /api/financial/{ticker}/{type}: Audited financial statement rows.
   */
  static getFinancialStatement(ticker: string, type: 'income' | 'balance' | 'cashflow'): Promise<FinancialStatementRow[]> {
    return fetchJson<FinancialStatementRow[]>(`/financial/${encodeURIComponent(ticker)}/${type}`);
  }
}

export const apiService = ApiService;
