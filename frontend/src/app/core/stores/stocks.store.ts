/**
 * Stocks store using Angular signals.
 * Provides reactive state management for stocks, quotes, and UI filters.
 */

import { Stock } from '../models/stock.model';
import { signal, computed } from '@angular/core';
import { verdictToBucket, VerdictBucket, getStockBucket } from '../utils/verdict';

interface StocksStoreState {
  stocks: Stock[];
  loading: boolean;
  error: string | null;
  lastUpdated: Date | null;
  selectedSymbol: string | null;
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
  filter: {
    sector: null,
    verdict: null,
    search: ''
  }
};

class StocksStore {
  private state = signal<StocksStoreState>(initialState);

  // Expose individual signals for fine-grained reactivity
  stocks = computed(() => this.state().stocks);
  loading = computed(() => this.state().loading);
  error = computed(() => this.state().error);
  selectedSymbol = computed(() => this.state().selectedSymbol);
  filter = computed(() => this.state().filter);

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
    const { filter, stocks } = this.state();
    let result = [...stocks];

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
    return this.state().stocks.find(s => s.symbol === sym) || null;
  });

  // ---- Actions ----

  setStocks(stocks: Stock[]): void {
    this.updateState(s => ({
      ...s,
      stocks,
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
    this.updateState(s => ({ ...s, selectedSymbol: symbol }));
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
