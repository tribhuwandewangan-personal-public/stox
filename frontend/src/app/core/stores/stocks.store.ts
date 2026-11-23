/**
 * Stocks store using Angular signals.
 * Provides reactive state management for stocks, quotes, and UI filters.
 */

import { Stock } from '../models/stock.model';
import { Company } from '../models/company.model';
import { signal, computed } from '@angular/core';
import { ApiService } from '../services/api.service';
import { verdictToBucket, VerdictBucket, getStockBucket } from '../utils/verdict';

export type HorizonStrategy = 'ALL' | 'SHORT' | 'LONG';
export type StockUniverse = 'curated' | 'midcap250' | 'all_nse';

interface StocksStoreState {
  stocks: Stock[];
  loading: boolean;
  error: string | null;
  lastUpdated: Date | null;
  selectedSymbol: string | null;
  adHocStock: Stock | null;
  horizonStrategy: HorizonStrategy;
  activeUniverse: StockUniverse;
  filter: {
    sector: string | null;
    verdict: VerdictBucket | null;
    search: string;
  };
}

const initialState: StocksStoreState = {
  stocks: [],
  loading: false,
  error: null,
  lastUpdated: null,
  selectedSymbol: null,
  adHocStock: null,
  horizonStrategy: 'ALL',
  activeUniverse: 'curated',
  filter: {
    sector: null,
    verdict: null,
    search: ''
  }
};

class StocksStore {
  private state = signal<StocksStoreState>(initialState);
  private loadSeq = 0;

  // Expose individual signals for fine-grained reactivity
  stocks = computed(() => this.state().stocks);
  loading = computed(() => this.state().loading);
  error = computed(() => this.state().error);
  selectedSymbol = computed(() => this.state().selectedSymbol);
  horizonStrategy = computed(() => this.state().horizonStrategy);
  activeUniverse = computed(() => this.state().activeUniverse);
  filter = computed(() => this.state().filter);

  // Derived count of stocks with live price (available)
  availableCount = computed(() =>
    this.state().stocks.filter(s => s?.price_info?.price != null).length);

  horizonCounts = computed(() => {
    const stocks = this.state().stocks;
    let shortCount = 0;
    let longCount = 0;

    for (const s of stocks) {
      const v = (s.synth_output?.structured_signal?.action_verdict || '').toUpperCase();
      if (v.includes('BUY') || v.includes('ACCUMULATE')) {
        shortCount++;
      }
      const lt = s.long_term_signal || s.synth_output?.structured_signal?.long_term_signal;
      if (lt?.is_top_wealth_pick) {
        longCount++;
      }
    }

    return {
      all: stocks.length,
      short: shortCount,
      long: longCount
    };
  });

  // Derived computations
  sectors = computed(() => {
    const sectors = new Set(this.state().stocks.map(s => s.sector).filter(Boolean));
    return Array.from(sectors).sort();
  });

  verdictCounts = computed(() => {
    const counts: { [key in VerdictBucket]: number } = {
      buy: 0,
      accumulate: 0,
      hold: 0,
      reduce: 0,
      sell: 0,
      pending: 0
    };

    for (const stock of this.state().stocks) {
      const bucket = getStockBucket(stock);
      counts[bucket]++;
    }

    return counts;
  });

  /**
   * Filtered and sorted stocks based on current filter state.
   */
  filteredStocks = computed(() => {
    const { filter, stocks, horizonStrategy } = this.state();
    let result = [...stocks];

    // Filter by Horizon Strategy (ALL, SHORT, LONG)
    if (horizonStrategy === 'SHORT') {
      result = result.filter(s => {
        const v = (s.synth_output?.structured_signal?.action_verdict || '').toUpperCase();
        return v.includes('BUY') || v.includes('ACCUMULATE');
      });
    } else if (horizonStrategy === 'LONG') {
      result = result.filter(s => {
        const lt = s.long_term_signal || s.synth_output?.structured_signal?.long_term_signal;
        return !!lt?.is_top_wealth_pick;
      });
    }

    // Filter by sector
    if (filter.sector) {
      result = result.filter(s => s.sector === filter.sector);
    }

    // Filter by verdict
    if (filter.verdict) {
      result = result.filter(s => getStockBucket(s) === filter.verdict);
    }

    // Filter by search (symbol or name)
    if (filter.search) {
      const q = filter.search.toLowerCase();
      result = result.filter(s =>
        s.symbol.toLowerCase().includes(q) ||
        s.name.toLowerCase().includes(q)
      );
    }

    // Sort: stale first (if analysis exists), then by verdict bucket, then by symbol
    result.sort((a, b) => {
      if (a.is_stale !== b.is_stale) {
        return a.is_stale ? 1 : -1; // Not stale first
      }

      const aBucket = getStockBucket(a);
      const bBucket = getStockBucket(b);
      const bucketOrder: VerdictBucket[] = ['buy', 'accumulate', 'hold', 'reduce', 'sell', 'pending'];
      const aIdx = bucketOrder.indexOf(aBucket);
      const bIdx = bucketOrder.indexOf(bBucket);

      if (aIdx !== bIdx) {
        return aIdx - bIdx;
      }

      return a.symbol.localeCompare(b.symbol);
    });

    return result;
  });

  selectedStock = computed(() => {
    const sym = this.state().selectedSymbol;
    if (!sym) return null;
    const found = this.state().stocks.find(s => s.symbol === sym);
    if (found) return found;
    const adHoc = this.state().adHocStock;
    return adHoc && adHoc.symbol === sym ? adHoc : null;
  });

  // ---- Actions ----

  setStocks(stocks: Stock[]): void {
    this.updateState(s => ({
      ...s,
      stocks: [...stocks],
      loading: false,
      lastUpdated: new Date(),
      error: null
    }));
  }

  updateStock(symbol: string, updates: Partial<Stock>): void {
    this.updateState(s => ({
      ...s,
      stocks: s.stocks.map(stock =>
        stock.symbol === symbol ? { ...stock, ...updates } : stock
      )
    }));
  }

  setLoading(loading: boolean): void {
    this.updateState(s => ({ ...s, loading }));
  }

  setError(error: string | null): void {
    this.updateState(s => ({ ...s, error }));
  }

  selectSymbol(symbol: string | null): void {
    this.updateState(s => ({
      ...s,
      selectedSymbol: symbol,
      adHocStock: symbol ? s.adHocStock : null,
    }));
  }

  selectStock(stock: Stock): void {
    this.updateState(s => ({
      ...s,
      selectedSymbol: stock.symbol,
      adHocStock: stock,
    }));
  }

  setHorizonStrategy(horizonStrategy: HorizonStrategy): void {
    this.updateState(s => ({ ...s, horizonStrategy }));
  }

  setActiveUniverse(activeUniverse: StockUniverse): void {
    this.updateState(s => ({ ...s, activeUniverse, filter: { sector: null, verdict: null, search: '' }, selectedSymbol: null }));
  }

  async loadUniverse(universe: StockUniverse): Promise<void> {
    const seq = ++this.loadSeq;
    this.updateState(s => ({
      ...s,
      activeUniverse: universe,
      horizonStrategy: 'ALL',
      filter: { sector: null, verdict: null, search: '' },
      selectedSymbol: null,
      loading: true,
      error: null
    }));
    try {
      const stocks = await ApiService.getStocks(universe);
      if (seq !== this.loadSeq) return;
      this.setStocks(Array.isArray(stocks) ? stocks : []);
    } catch (err: any) {
      if (seq !== this.loadSeq) return;
      this.updateState(s => ({
        ...s,
        error: err?.message || 'Failed to load stock universe',
        loading: false
      }));
    } finally {
      if (seq === this.loadSeq) {
        this.setLoading(false);
      }
    }
  }

  async refreshCurrentUniverse(): Promise<void> {
    const seq = ++this.loadSeq;
    const universe = this.state().activeUniverse;
    try {
      const stocks = await ApiService.getStocks(universe);
      if (seq !== this.loadSeq) return;
      this.setStocks(Array.isArray(stocks) ? stocks : []);
    } catch (err) {
      console.error('[StocksStore] Failed to refresh current universe:', err);
    }
  }

  setSectorFilter(sector: string | null): void {
    this.updateState(s => ({
      ...s,
      filter: { ...s.filter, sector }
    }));
  }

  setVerdictFilter(verdict: VerdictBucket | null): void {
    this.updateState(s => ({
      ...s,
      filter: { ...s.filter, verdict }
    }));
  }

  setSearchFilter(search: string): void {
    this.updateState(s => ({
      ...s,
      filter: { ...s.filter, search }
    }));
  }

  clearFilters(): void {
    this.updateState(s => ({
      ...s,
      filter: { sector: null, verdict: null, search: '' }
    }));
  }

  reset(): void {
    this.updateState(() => initialState);
  }

  // ---- private ----

  private updateState(updater: (state: StocksStoreState) => StocksStoreState): void {
    this.state.update(s => updater(s));
  }
}

// Export singleton store
export const stocksStore = new StocksStore();
