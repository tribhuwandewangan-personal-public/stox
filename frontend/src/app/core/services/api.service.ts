/**
 * HTTP API client service.
 * Thin wrapper around fetch that adds CSRF headers and error handling.
 */

import {
  Stock,
  AccuracyReport,
  ChartData,
  QuotesResponse,
  SearchResult,
  QueueStatus
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
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    return await response.json();
  } catch (error) {
    console.error(`[API] Error fetching ${path}:`, error);
    throw error;
  }
}

export class ApiService {
  /**
   * GET /api/status: Server status, queue, macro.
   */
  static getStatus(): Promise<any> {
    return fetchJson('/status');
  }

  /**
   * GET /api/stocks: All stocks with analysis and quotes.
   */
  static getStocks(): Promise<Stock[]> {
    const resp = fetchJson<any>('/stocks');
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
}

export const apiService = ApiService;
